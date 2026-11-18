"""Audit the stored task 9 runs. Writes aggregates to results/audit.json and a few complete runs to
results/worked_examples.json.

analyse.py gives one total per batch. This script answers the questions those totals leave open:
which searches each run made and whether any reply it received held the patient's latest potassium
result; why each run that did not match the statement failed; how two conditions compare on the
same moments and the same patients; which of Stanford's checks reject a run whose orders match the
statement; and what two fixed programs (one that never orders, one that reads only the first page
the search returns) score on the released cases and at every report moment.

  python3 study/agent/audit.py --runs PRIVATE/agent/runs --cases PRIVATE/agent/cases2.json \
      --resources PRIVATE/agent/k_resources.json --out results/audit.json --examples results/worked_examples.json
"""
import argparse, collections, glob, json, os, random, re, statistics, sys
from urllib.parse import parse_qsl, urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
from analyse import content, oral, codes, stanford_for  # noqa: E402
from run_standin import conflict_values, table_view  # noqa: E402
from standin import CLOCK, epoch, iso  # noqa: E402
from apply_rule import oracle, tenths  # noqa: E402

C = collections.Counter
MAIN = ("replace", "replace_newest", "replace_hint", "replace_table")
ROUTE = "route is the plain string oral"
FIELD = {"test priority is stat": "the test order's priority is not stat", "exactly two accepted POSTs": "not exactly two orders",
         "first POST is the MedicationRequest": "the medication order is not first", "dose unit is exactly mEq": "the dose unit is not written mEq",
         "medication status active and intent order": "medication status or intent", "test status active and intent order": "test status or intent",
         "medication authoredOn contains 2023-11-13T10:15": "medication authoredOn", "test authoredOn is exactly 2023-11-13T10:15:00+00:00": "test authoredOn",
         "NDC system and code in coding[0]": "NDC not in the first coding", "LOINC system and code in coding[0]": "LOINC not in the first coding"}
SAID = re.compile(r"conflict|differ|discrepan|discordan|inconsisten|two (potassium )?(results|values|levels)|cannot be decided|can ?not be determined", re.I)  # as in analyse.py


# ---------------------------------------------------------------- reading one run

def bundle(reply):
    i, j = reply.find("{"), reply.rfind("}")
    if i < 0 or j < i:
        return None
    try:
        return json.loads(reply[i:j + 1])
    except ValueError:
        return None


def gets(row):
    """One record per GET the model issued: its search parameters and the potassium results in the reply."""
    out = []
    for t in row["turns"]:
        if t.get("action") != "GET":
            continue
        u = urlsplit(t["url"])
        q = parse_qsl(u.query, keep_blank_values=True)
        b = bundle(t.get("reply", "")) if t.get("get_ok") else None
        ent = [(epoch(e["resource"]["effectiveDateTime"]), (e["resource"].get("valueQuantity") or {}).get("value"), e["resource"].get("status"))
               for e in (b or {}).get("entry", []) if e.get("resource", {}).get("resourceType") == "Observation" and "effectiveDateTime" in e["resource"]]
        code = next((v for k, v in q if k == "code"), None)
        out.append({"url": t["url"], "names": {k for k, _ in q}, "code": code, "is_k": bool(code) and "K" in {c.split("|")[-1] for c in code.split(",")},
                    "loinc": bool(code) and "2823-3" in code, "paged": any(k == "_getpages" for k, _ in q), "entries": ent,
                    "total": (b or {}).get("total"), "next": any(l.get("relation") == "next" for l in (b or {}).get("link", [])), "ok": b is not None})
    return out


def search_kind(g):
    """Mutually exclusive. The first that applies, in this order."""
    if not g:
        return "made_no_search"
    k = [x for x in g if x["is_k"]]
    if not k:
        return "searched_only_by_2823-3" if any(x["loinc"] for x in g) else "searched_without_the_potassium_code"
    if any("_sort" in x["names"] for x in k):
        return "searched_K_and_asked_for_sorting"
    if any(x["paged"] for x in g):
        return "searched_K_and_followed_the_next_page_link"
    if any("date" in x["names"] for x in k):
        return "searched_K_with_a_date_filter"
    if any("_count" in x["names"] for x in k):
        return "searched_K_and_asked_for_a_larger_page"
    return "searched_K_and_read_the_first_page_only"


class Chart:
    """The potassium results a run could search, in the order the released search returns them."""

    def __init__(self, row, cases, res):
        if row["set"] == "control":
            self.rows, self.shift = res[row["patient"]]["K"], 0
            self.latest = row["oracle"][1]
            self.values = None
        else:
            c = cases[row["label"].rstrip("e")]
            self.shift = CLOCK - c["moment"]
            self.rows = [r for r in res[c["source"]]["K"] if epoch(r["issued"]) <= c["moment"]]
            self.latest = c["oracle"][1] + self.shift if c["oracle"][1] is not None else None
            self.values = conflict_values(res[c["source"]], c) if c["kind"] == "conflict" else None
        self.t = [epoch(r["effectiveDateTime"]) + self.shift for r in self.rows]
        self.first_page_holds_latest = self.latest in self.t[:20]
        self.group = ("20 results or fewer" if len(self.rows) <= 20 else
                      "over 20 results, latest on the first page" if self.first_page_holds_latest else "over 20 results, latest not on the first page")


def read(row, chart):
    g = gets(row)
    seen = [e for x in g for e in x["entries"]]
    newest = max(seen, key=lambda e: e[0]) if seen else None
    posts = [p for _, p in row.get("accepted_posts", []) if isinstance(p, dict)]
    dose = None
    for p in posts:
        try:
            if p.get("resourceType") == "MedicationRequest":
                dose = p["dosageInstruction"][0]["doseAndRate"][0]["doseQuantity"]["value"]
        except (KeyError, IndexError, TypeError):
            pass
    return {"gets": g, "kind": search_kind(g), "also_2823": any(x["loinc"] for x in g) and any(x["is_k"] for x in g),
            "retrieved_latest": any(e[0] == chart.latest for e in seen), "newest_seen": tenths(newest[1]) if newest and newest[1] is not None else None,
            "placed": bool(posts), "dose": dose}


def mode(row, info, ok, why, c_ok=None, checks=()):
    """What a run did. Mutually exclusive. ok is the reported score; c_ok is the content check (required
    dose, product, unit, route, test and time); checks are Stanford's conditions the run fails, other than
    the type of the route."""
    need = row["kind"] == "replace"
    if row["status"] != "completed":
        return "ended without a final answer (" + str(row["status"]) + ")"
    if not ok and c_ok:
        if need:
            return "required dose ordered; " + (FIELD.get(checks[0], checks[0]) if checks else "rejected by the grader for a reason not classified")
        return "no order placed; a message contains the text POST, which the grader counts as an order"
    if ok:
        if info["retrieved_latest"]:
            return "matched; a reply held the latest result"
        if need:
            old = info["newest_seen"]
            same = old is not None and old < 35 and row.get("dose") is not None and abs(10 * (35 - old) - row["dose"]) < 1e-6
            return ("matched; no reply held the latest result (an older result gave the same dose)" if same else
                    "matched; no reply held the latest result (the latest result received gives another dose)")
        return "matched (no order); no reply held the latest result"
    if not info["retrieved_latest"]:
        if info["kind"] in ("searched_only_by_2823-3", "searched_without_the_potassium_code", "made_no_search"):
            return "never searched by the code K; received no potassium result" + ("" if not info["placed"] else "; placed orders")
        old = info["newest_seen"]
        if need and not info["placed"]:
            return "latest result never returned; the newest result it received was not low; no order" if old is not None and old >= 35 else "latest result never returned; no order"
        if info["placed"] and old is not None and old < 35 and info["dose"] is not None and abs(info["dose"] - 10 * (35 - old)) < 1e-6:
            return "latest result never returned; dosed from the newest result it received"
        return "latest result never returned; " + ("placed other orders" if info["placed"] else "no order")
    return "latest result returned; " + {"no_orders": "placed no order", "wrong_dose": "ordered a different dose", "wrong_product_unit_or_route": "wrong product, unit or route",
                                           "wrong_test_or_time": "wrong repeat test or time", "wrong_set_of_orders": "not exactly the two orders", "dose_not_stated": "dose not stated",
                                           "wrong_patient": "wrong patient", "placed_orders_when_none_required": "placed orders when none was required"}.get(why, why)


# ---------------------------------------------------------------- Stanford's checks, one at a time

def stanford_checks(row, dose):
    """The conditions in Stanford's task 9 grader for a case that needs the orders, tested one by one on
    the posts the grader itself extracted. Used only to say which condition rejects a run; the verdicts
    reported elsewhere come from Stanford's file."""
    posts, mrn, bad = row.get("grader_extract_posts") or [], row["patient"], []

    def chk(name, f):
        try:
            if not f():
                bad.append(name)
        except Exception:
            bad.append(name)
    if len(posts) != 2:
        return ["exactly two accepted POSTs"]
    (u1, m), (u2, s) = posts
    chk("first POST is the MedicationRequest", lambda: u1.endswith("/MedicationRequest") and m["resourceType"] == "MedicationRequest")
    chk("NDC system and code in coding[0]", lambda: m["medicationCodeableConcept"]["coding"][0]["system"] == "http://hl7.org/fhir/sid/ndc" and m["medicationCodeableConcept"]["coding"][0]["code"] == "40032-917-01")
    chk("medication authoredOn contains 2023-11-13T10:15", lambda: "2023-11-13T10:15" in m["authoredOn"])
    chk("route is the plain string oral", lambda: m["dosageInstruction"][0]["route"].lower().strip() == "oral")
    chk("dose value", lambda: abs(m["dosageInstruction"][0]["doseAndRate"][0]["doseQuantity"]["value"] - dose) <= 0.1)
    chk("dose unit is exactly mEq", lambda: m["dosageInstruction"][0]["doseAndRate"][0]["doseQuantity"]["unit"] == "mEq")
    chk("medication status active and intent order", lambda: m["status"] == "active" and m["intent"] == "order")
    chk("medication subject", lambda: m["subject"] == {"reference": f"Patient/{mrn}"})
    chk("second POST is the ServiceRequest", lambda: u2.endswith("/ServiceRequest") and s["resourceType"] == "ServiceRequest")
    chk("LOINC system and code in coding[0]", lambda: s["code"]["coding"][0]["system"] == "http://loinc.org" and s["code"]["coding"][0]["code"] == "2823-3")
    chk("test authoredOn is exactly 2023-11-13T10:15:00+00:00", lambda: s["authoredOn"] == "2023-11-13T10:15:00+00:00")
    chk("test status active and intent order", lambda: s["status"] == "active" and s["intent"] == "order")
    chk("test priority is stat", lambda: s["priority"] == "stat")
    chk("test subject", lambda: s["subject"] == {"reference": f"Patient/{mrn}"})
    chk("test time contains 2023-11-14T08:", lambda: "2023-11-14T08:" in s["occurrenceDateTime"])
    return bad


def closing(row, latest_value):
    try:
        v = json.loads(row.get("result") or "")
    except ValueError:
        return "not a JSON list"
    if v == []:
        return "an empty list"
    if isinstance(v, list) and len(v) == 1 and isinstance(v[0], (int, float)):
        return "a list holding the latest value" if latest_value is not None and abs(v[0] - latest_value) < 1e-9 else "a list holding another number"
    if isinstance(v, list) and all(isinstance(x, str) for x in v):
        return "a list holding one or more sentences"
    return "another list"


# ---------------------------------------------------------------- statistics

def by_patient(pairs):
    d = collections.defaultdict(lambda: [0, 0])
    for src, ok in pairs:
        d[src][0] += ok
        d[src][1] += 1
    return d


def boot(groups, f, reps=4000, seed=11):
    """Percentile interval for f over patients resampled with replacement (moments from one patient stay together)."""
    rnd, keys, out = random.Random(seed), sorted(groups), []
    for _ in range(reps):
        pick = [groups[rnd.choice(keys)] for _ in keys]
        out.append(f(pick))
    out.sort()
    return [round(out[int(0.025 * reps)], 4), round(out[int(0.975 * reps) - 1], 4)]


def share(pick):
    a = sum(x[0] for x in pick)
    b = sum(x[1] for x in pick)
    return a / b if b else 0.0


# ---------------------------------------------------------------- main

def load(runs):
    out = {}
    for path in sorted(glob.glob(os.path.join(runs, "*.jsonl"))):
        rows = [json.loads(l) for l in open(path) if l.strip()]
        rows = list({r["label"]: r for r in reversed(rows) if "turns" in r}.values())[::-1]
        if rows:
            out[os.path.basename(path)[:-6]] = rows
    return out


def first_page_program(rows_t_v):
    """A fixed program: read the first page the released search returns (20 results), take the one taken
    most recently on that page, apply the dosing rule. rows_t_v is [(time, tenths)] in served order."""
    page = rows_t_v[:20]
    if not page:
        return ("none", None)
    t, v = max(page, key=lambda x: x[0])
    return ("replace", 10 * (35 - v)) if v < 35 else ("none", None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", required=True)
    ap.add_argument("--cases", required=True)
    ap.add_argument("--resources", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--examples", required=True)
    ap.add_argument("--table", help="write one row per run, with no patient values, to this CSV file")
    a = ap.parse_args()
    res = json.load(open(a.resources))
    case_list = json.load(open(a.cases))["cases"]
    cases = {c["label"]: c for c in case_list}
    batches = load(a.runs)
    out = {}

    # ---- the population of report moments
    per_patient = C(c["source"] for c in case_list if c["kind"] == "replace")
    low_specimens = {(c["source"], c["oracle"][1]) for c in case_list if c["kind"] == "replace"}
    conf = C()
    for c in case_list:
        if c["kind"] == "conflict":
            src = res[c["source"]]["K"]
            at = [r for r in src if epoch(r["issued"]) <= c["moment"] and epoch(r["effectiveDateTime"]) == c["oracle"][1] and r["status"] == "final"]
            conf[f"{len(at)} results, {len(conflict_values(res[c['source']], c))} different values"] += 1
    all_rows = [r for m in res for r in res[m]["K"]]
    no_unit = [r for r in all_rows if not (r.get("valueQuantity") or {}).get("unit")]
    units = C((r.get("valueQuantity") or {}).get("unit") or "(none)" for r in all_rows)
    out["population"] = {
        "patients": len(res), "potassium_results": len(all_rows),
        "report_moments": len({(m, r["issued"]) for m in res for r in res[m]["K"]}),
        "results_by_status": dict(C(r["status"] for r in all_rows)), "results_by_unit": dict(units),
        "results_with_no_unit": {"n": len(no_unit), "lowest_value": min((r["valueQuantity"]["value"] for r in no_unit), default=None),
                                 "highest_value": max((r["valueQuantity"]["value"] for r in no_unit), default=None)},
        "moments_by_required_outcome": dict(C(c["kind"] for c in case_list)),
        "replace_moments": {"moments": sum(per_patient.values()), "patients": len(per_patient), "distinct_low_results_behind_them": len(low_specimens), "distinct_patient_and_sample_time_pairs": len(low_specimens),
                            "moments_per_patient": {"min": min(per_patient.values()), "median": statistics.median(per_patient.values()), "max": max(per_patient.values())},
                            "moments_from_the_5_patients_with_most": sum(v for _, v in per_patient.most_common(5))},
        "conflict_moments_by_composition": dict(conf)}

    # ---- two fixed programs, on the released cases and at every report moment
    def group_of(rows):
        if len(rows) <= 20:
            return "20 results or fewer"
        latest = max(t for t, _ in rows)
        return "over 20 results, latest on the first page" if any(t == latest for t, _ in rows[:20]) else "over 20 results, latest not on the first page"

    def fixed(kind_dose_rows):
        t = {"never_orders": C(), "reads_first_page_only": C(), "n": C()}
        by_chart, cases_by_chart = collections.defaultdict(lambda: [0, 0]), C()
        for kind, dose, rows in kind_dose_rows:
            t["n"][kind] += 1
            t["never_orders"][kind] += kind != "replace"
            got = first_page_program(rows)
            ok = (got == ("replace", dose)) if kind == "replace" else got[0] == "none"
            t["reads_first_page_only"][kind] += ok
            cases_by_chart[f"{kind} | {group_of(rows)}"] += 1
            if kind == "replace":
                by_chart[group_of(rows)][0] += ok
                by_chart[group_of(rows)][1] += 1
        out = {k: dict(v) for k, v in t.items()}
        out["reads_first_page_only_where_orders_are_required_by_chart"] = {k: {"matched": v[0], "moments": v[1]} for k, v in by_chart.items()}
        out["cases_by_outcome_and_chart"] = dict(cases_by_chart)
        return out
    rel = []
    mrns = [m for m in sorted(res) if res[m]["task9"]]
    outs = oracle([(CLOCK, [(epoch(r["effectiveDateTime"]), tenths(r["valueQuantity"]["value"]), r["status"] == "final") for r in res[m]["K"]]) for m in mrns])
    for m, o in zip(mrns, outs):
        rel.append((o[0], o[3] if o[0] == "replace" else None, [(epoch(r["effectiveDateTime"]), tenths(r["valueQuantity"]["value"])) for r in res[m]["K"]]))
    every = []
    for c in case_list:
        rows = [(epoch(r["effectiveDateTime"]), tenths(r["valueQuantity"]["value"])) for r in res[c["source"]]["K"] if epoch(r["issued"]) <= c["moment"]]
        every.append((c["kind"], c["dose"], rows))
    fx_all = fixed(every)
    fp = by_patient((c["source"], first_page_program(rows) == ("replace", c["dose"])) for c, (_, _, rows) in zip(case_list, every) if c["kind"] == "replace")
    fx_all["reads_first_page_only_interval_95_resampling_patients"] = boot(dict(fp), share)
    out["fixed_programs"] = {"released_30_cases": fixed(rel), "every_report_moment": fx_all,
                             "note": "matched means the program's decision equals the statement's outcome; for a moment whose latest results disagree, matched means it placed no order"}

    # ---- every batch, run by run
    per, detail = {}, {}
    for name, rows in batches.items():
        t = {"runs": len(rows), "matched": 0, "patients": len({r.get("source") or r["patient"] for r in rows}), "set": rows[0]["set"]}
        kinds, modes, groups, close = collections.defaultdict(lambda: [0, 0]), C(), collections.defaultdict(lambda: [0, 0]), C()
        err = bool(rows[0]["provenance"].get("added_error_row"))
        stanford, _ = stanford_for(rows, res, cases)
        # Where the released grader and the specification require different things (results at the most recent
        # time that disagree, a result marked entered-in-error) a run is scored against the specification.
        spec_scored = name.startswith(("conflict", "err"))
        t["scored_by"] = "the specification (content check)" if spec_scored else "Stanford's grader with the route type and the final answer not examined"
        t.update({"content_ok": 0, "released_pass": 0, "relaxed_pass": 0})
        cross = C()
        d = {}
        for r in rows:
            ch = Chart(r, cases, res)
            c_ok, why = content(r["kind"], r.get("dose"), r["patient"], r.get("accepted_posts", []))
            done = r["status"] == "completed"
            if not done:
                c_ok, why = False, "did_not_finish"
            released = bool(done and stanford(r))
            relaxed = bool(done and stanford(r, closing="[]", plain_route=True))
            ok = c_ok if spec_scored else relaxed
            checks = [x for x in stanford_checks(r, r["dose"]) if x != ROUTE] if r["kind"] == "replace" and r.get("accepted_posts") else []
            info = read(r, ch)
            if err:  # one newer row marked entered-in-error was added; the reply tests below do not apply
                info["retrieved_latest"] = None
            md = mode(r, info, ok, why, c_ok, checks) if not err else ("matched" if ok else why)
            t["content_ok"] += c_ok
            t["released_pass"] += released
            t["relaxed_pass"] += relaxed
            cross[f"content {'ok' if c_ok else 'not ok'}, relaxed grader {'pass' if relaxed else 'fail'}"] += 1
            t["matched"] += ok
            kinds[info["kind"]][0] += ok
            kinds[info["kind"]][1] += 1
            modes[md] += 1
            groups[ch.group][0] += ok
            groups[ch.group][1] += 1
            latest_value = next((v for tt, v, _ in [e for x in info["gets"] for e in x["entries"]] if tt == ch.latest), None)
            close[closing(r, latest_value) if r["status"] == "completed" else "did not finish"] += 1
            d[r["label"]] = {"ok": ok, "why": why, "mode": md, "info": info, "chart": ch, "row": r, "c_ok": c_ok, "released": released, "relaxed": relaxed, "checks": checks}
        t["content_and_relaxed_grader"] = dict(cross)
        t["by_search"] = {k: {"matched": v[0], "runs": v[1]} for k, v in sorted(kinds.items(), key=lambda kv: -kv[1][1])}
        t["searched_by_both_codes"] = sum(x["info"]["also_2823"] for x in d.values())
        t["by_outcome"] = dict(modes.most_common())
        if not err and rows[0]["set"] != "control":
            t["by_chart"] = {k: {"matched": v[0], "runs": v[1]} for k, v in groups.items()}
        t["closing_message"] = dict(close)
        if rows[0]["set"] != "control":
            g = by_patient((x["row"]["source"], x["ok"]) for x in d.values())
            sh = [v[0] / v[1] for v in g.values()]
            t["by_patient"] = {"patients": len(g), "matched_at_every_moment": sum(v[0] == v[1] for v in g.values()), "matched_at_no_moment": sum(v[0] == 0 for v in g.values()),
                               "median_patient_share": round(statistics.median(sh), 4), "mean_of_patient_shares": round(statistics.mean(sh), 4)}
            t["share_matched"] = round(t["matched"] / t["runs"], 4)
            t["interval_95_resampling_patients"] = boot({k: v for k, v in g.items()}, share)
        per[name], detail[name] = t, d
    out["batches"] = per

    # ---- two conditions on the same moments
    def paired(a_name, b_name):
        if a_name not in detail or b_name not in detail:
            return None
        A, B = detail[a_name], detail[b_name]
        common = [k for k in A if k in B]
        if not common:
            return None
        t = C((A[k]["ok"], B[k]["ok"]) for k in common)
        g = collections.defaultdict(lambda: [0, 0, 0])
        for k in common:
            x = g[A[k]["row"].get("source") or k]
            x[0] += A[k]["ok"]
            x[1] += B[k]["ok"]
            x[2] += 1
        diff = lambda pick: (sum(x[1] for x in pick) - sum(x[0] for x in pick)) / sum(x[2] for x in pick)  # noqa: E731
        only = lambda D, k: D[k]["info"]["kind"] == "searched_only_by_2823-3"  # noqa: E731
        return {"first": a_name, "second": b_name, "moments_in_both": len(common), "patients": len(g),
                "first_searched_only_by_2823-3": sum(only(A, k) for k in common), "second_searched_only_by_2823-3": sum(only(B, k) for k in common),
                "both_searched_only_by_2823-3": sum(only(A, k) and only(B, k) for k in common),
                "first_matched": sum(A[k]["ok"] for k in common), "second_matched": sum(B[k]["ok"] for k in common),
                "both_matched": t[(True, True)], "only_first_matched": t[(True, False)], "only_second_matched": t[(False, True)], "neither_matched": t[(False, False)],
                "difference_in_share": round(diff(list(g.values())), 4), "interval_95_resampling_patients": boot(dict(g), diff),
                "first_mean_of_patient_shares": round(statistics.mean(x[0] / x[2] for x in g.values()), 4),
                "second_mean_of_patient_shares": round(statistics.mean(x[1] / x[2] for x in g.values()), 4),
                "mean_of_patient_differences": round(statistics.mean((x[1] - x[0]) / x[2] for x in g.values()), 4)}
    out["paired"] = {k: v for k, v in {
        "released_search_vs_newest_first": paired("replace", "replace_newest"),
        "released_search_vs_paging_sentence": paired("replace", "replace_hint"),
        "released_search_vs_table": paired("replace", "replace_table"),
        "low_vs_high_reasoning_effort": paired("replace", "replace_high"),
        "newest_first_vs_table": paired("replace_newest", "replace_table"),
        "not_low_released_search_vs_table": paired("notLow", "notLow_table"),
        "released_search_run_twice": paired("replace", "replace_repeat"),
        "released_cases_twice_on_the_released_server": paired("control_pilot", "control_repeat"),
        "released_cases_released_server_vs_stand_in": paired("control_pilot", "control_via_standin")}.items() if v}

    # ---- one row per moment that requires the orders, for the map on the page (no patient values)
    if "replace" in detail and "replace_newest" in detail:
        def code(md):
            return (0 if md.startswith("matched; a reply held") else 1 if md.startswith("matched; no reply held") else
                    2 if md.startswith("latest result never returned") and "dosed" not in md and "placed other" not in md else
                    3 if "dosed from the newest result" in md else 4 if md.startswith("never searched") else
                    6 if md.startswith("required dose ordered") else 5)
        A_, B_ = detail["replace"], detail["replace_newest"]
        common = [k for k in A_ if k in B_]
        per_src = C(A_[k]["row"]["source"] for k in common)
        rank = {src: i + 1 for i, (src, _) in enumerate(sorted(per_src.items(), key=lambda kv: (-kv[1], kv[0])))}
        groups = ["20 results or fewer", "over 20 results, latest on the first page", "over 20 results, latest not on the first page"]
        cells = sorted(({"p": rank[A_[k]["row"]["source"]], "of": per_src[A_[k]["row"]["source"]], "rows": len(A_[k]["chart"].rows), "g": groups.index(A_[k]["chart"].group),
                         "dose": A_[k]["row"]["dose"], "r": code(A_[k]["mode"]), "n": code(B_[k]["mode"]), "label": k, "_t": A_[k]["row"]["moment"]} for k in common),
                       key=lambda c_: (c_["g"], c_["p"], c_["_t"]))
        for c_ in cells:
            del c_["_t"]
        out["moments_that_require_the_orders"] = {
            "note": "one entry per report moment: p is the patient's rank by number of moments, of is that patient's number of moments, rows the potassium results in the chart, g the chart group, dose the required dose in mEq, r and n what the run did under the released and the newest-first search",
            "groups": groups, "codes": ["orders match; a reply held the latest result", "orders match; no reply held the latest result", "no order; the latest result was never returned",
                                        "dose from an older result", "no order; searched only by 2823-3", "the latest result was returned and the dose differs",
                                        "required dose ordered; a field the tool definitions specify is missing"],
            "cells": cells}

    # ---- in the table condition, did the model still search?
    for name in ("replace_table", "notLow_table"):
        if name in detail:
            per[name]["runs_that_also_searched_for_potassium"] = sum(any(x["is_k"] for x in v["info"]["gets"]) for v in detail[name].values())

    # ---- the same trajectory? (released cases)
    def traj(r):
        return [(t.get("action"), t.get("url") or (t.get("post_url"), json.dumps(t.get("payload"), sort_keys=True)) if t.get("action") != "FINISH" else None) for t in r["turns"]]
    tr = {}
    for a_name, b_name in (("control_pilot", "control_repeat"), ("control_pilot", "control_via_standin")):
        if a_name in batches and b_name in batches:
            A = {r["label"]: r for r in batches[a_name]}
            B = {r["label"]: r for r in batches[b_name]}
            tr[f"{a_name} vs {b_name}"] = {"cases": len(set(A) & set(B)), "same_requests_in_the_same_order": sum(traj(A[k]) == traj(B[k]) for k in A if k in B)}
    out["released_cases_same_requests"] = tr

    # ---- the released grader against the relaxed grader, on action-required runs in the four main batches
    gr = {"batches": [b for b in MAIN if b in detail], "runs": 0, "relaxed_pass": 0, "released_pass": 0, "relaxed_pass_route_written_as_object": 0,
          "relaxed_pass_final_answer": C(), "required_dose_but_relaxed_fail": C(), "relaxed_pass_but_content_check_fails": C()}
    for b in gr["batches"]:
        for v in detail[b].values():
            if v["row"]["kind"] != "replace":
                continue
            gr["runs"] += 1
            gr["released_pass"] += v["released"]
            if v["relaxed"]:
                gr["relaxed_pass"] += 1
                gr["relaxed_pass_route_written_as_object"] += ROUTE in stanford_checks(v["row"], v["row"]["dose"])
                latest_value = next((val for tt, val, _ in [e for x in v["info"]["gets"] for e in x["entries"]] if tt == v["chart"].latest), None)
                gr["relaxed_pass_final_answer"][closing(v["row"], latest_value)] += 1
                if not v["c_ok"]:
                    gr["relaxed_pass_but_content_check_fails"][v["why"]] += 1
            elif v["c_ok"]:
                gr["required_dose_but_relaxed_fail"][FIELD.get(v["checks"][0], v["checks"][0]) if v["checks"] else "not classified"] += 1
    for k in ("relaxed_pass_final_answer", "required_dose_but_relaxed_fail", "relaxed_pass_but_content_check_fails"):
        gr[k] = dict(gr[k].most_common())
    out["grader_comparison"] = gr
    # what the model wrote in two fields, over every order in the four main batches
    wrote = C()
    for b in gr["batches"]:
        for v in detail[b].values():
            for _, pl in v["row"].get("accepted_posts", []):
                if not isinstance(pl, dict):
                    continue
                if pl.get("resourceType") == "MedicationRequest":
                    try:
                        rt = pl["dosageInstruction"][0].get("route")
                    except (KeyError, IndexError, TypeError, AttributeError):
                        rt = None
                    wrote["medication_orders"] += 1
                    wrote["route_written_as_an_object" if isinstance(rt, dict) else "route_written_as_a_string" if isinstance(rt, str) else "route_absent"] += 1
                elif pl.get("resourceType") == "ServiceRequest":
                    wrote["test_orders"] += 1
                    wrote["priority_" + str(pl.get("priority"))] += 1
    out["fields_the_model_wrote"] = dict(wrote)

    # the instance whose most recent result is the 0.0 with no unit (the largest required dose)
    top = max((v["row"]["dose"] or 0) for v in detail["replace"].values()) if "replace" in detail else None
    if top:
        label = next(k for k, v in detail["replace"].items() if v["row"]["dose"] == top)
        flagged = re.compile(r"invalid|erroneous|not (a )?valid|implausible|cannot be 0", re.I)
        out["instance_with_the_largest_required_dose"] = {"required_dose_mEq": top, "runs": {
            b: {"placed_an_order": detail[b][label]["info"]["placed"], "dose_ordered_mEq": detail[b][label]["info"]["dose"], "relaxed_grader_pass": detail[b][label]["relaxed"],
                "a_reply_held_the_most_recent_result": detail[b][label]["info"]["retrieved_latest"],
                "final_answer_calls_the_value_invalid": bool(flagged.search(str(detail[b][label]["row"].get("result") or "")))}
            for b in MAIN if b in detail and label in detail[b]}}

    out["all_runs"] = {"runs": sum(len(v) for v in detail.values()), "released_grader_pass": sum(x["released"] for v in detail.values() for x in v.values()),
                       "final_answer": dict(C(closing(x["row"], None) if x["row"]["status"] == "completed" else "did not finish" for v in detail.values() for x in v.values()).most_common()),
                       "runs_that_did_not_finish": {"by_status": dict(C(str(x["row"]["status"]) for v in detail.values() for x in v.values() if x["row"]["status"] != "completed")),
                                                    "by_batch": dict(C(b for b, v in detail.items() for x in v.values() if x["row"]["status"] != "completed"))}}

    # ---- moments where the latest results disagree
    cf = {}
    for name in ("conflictHard_table", "conflictHard_contract", "conflict", "conflict_table"):
        if name not in detail:
            continue
        t = C()
        for v in detail[name].values():
            r = v["row"]
            said = bool(SAID.search(str(r.get("result") or "")))
            placed = v["info"]["placed"]
            t["runs"] += 1
            t["placed_no_order"] += not placed
            t["said_so"] += said
            t["placed_no_order_and_said_so"] += (not placed) and said
            vals = v["chart"].values or []
            if placed and v["info"]["dose"] is not None and vals:
                t["dosed_from_the_lowest_value"] += abs(v["info"]["dose"] - 10 * (35 - min(vals))) < 1e-6
                t["dosed_from_the_highest_value"] += len(vals) > 1 and max(vals) < 35 and abs(v["info"]["dose"] - 10 * (35 - max(vals))) < 1e-6
        cf[name] = dict(t)
    out["moments_where_latest_results_disagree"] = cf

    json.dump(out, open(a.out, "w"), indent=1)
    print(json.dumps({k: (v if k != "batches" else {b: {"runs": x["runs"], "matched": x["matched"]} for b, x in v.items()}) for k, v in out.items()}, indent=1)[:6000])

    # ---- one row per run, with no patient values, so that the classification counts can be recounted
    if a.table:
        import csv
        src_rank = {}
        with open(a.table, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["condition", "instance", "patient", "results_in_chart", "chart_group", "search", "most_recent_result_in_a_reply", "placed_an_order",
                        "relaxed_grader", "released_grader", "class"])
            names = {"control_pilot": "released instances, released server", "replace": "action-required, default order", "replace_newest": "action-required, most-recent-first order",
                     "notLow": "no-action sample, default order", "replace_hint": "action-required, two sentences on paging added", "replace_table": "action-required, table of eight results added"}
            for b, cond in names.items():
                for i, (label, v) in enumerate(detail.get(b, {}).items(), 1):
                    src = v["row"].get("source") or v["row"]["patient"]
                    pid = src_rank.setdefault(src, f"p{len(src_rank) + 1:03d}")
                    w.writerow([cond, f"released_{i:02d}" if b == "control_pilot" else label, pid, len(v["chart"].rows), v["chart"].group, v["info"]["kind"],
                                {True: "yes", False: "no", None: ""}[v["info"]["retrieved_latest"]], "yes" if v["info"]["placed"] else "no",
                                "pass" if v["relaxed"] else "fail", "pass" if v["released"] else "fail", v["mode"]])

    # ---- complete runs for the page
    def show(name, label, title, why):
        v = detail[name][label]
        r, ch = v["row"], v["chart"]
        chart = [{"n": i + 1, "taken": iso(t), "value": row["valueQuantity"]["value"], "unit": (row.get("valueQuantity") or {}).get("unit"), "status": row["status"],
                  "first_page": i < 20, "latest": t == ch.latest} for i, (row, t) in enumerate(zip(ch.rows, ch.t))]
        turns = []
        for t in r["turns"]:
            if t.get("action") == "GET":
                b = bundle(t.get("reply", "")) or {}
                turns.append({"action": "GET", "request": t["content"], "returned": len(b.get("entry", [])), "total_stated": b.get("total"),
                              "next_page_link": any(l.get("relation") == "next" for l in b.get("link", [])),
                              "rows": [{"taken": e["resource"]["effectiveDateTime"], "value": (e["resource"].get("valueQuantity") or {}).get("value")} for e in b.get("entry", []) if "effectiveDateTime" in e.get("resource", {})]})
            elif t.get("action") == "POST":
                turns.append({"action": "POST", "url": t.get("post_url"), "payload": t.get("payload")})
            else:
                turns.append({"action": t.get("action") or "other", "text": t.get("content", "")[:1200]})
        bad = stanford_checks(r, r["dose"]) if r["kind"] == "replace" and v["info"]["placed"] else []
        return {"batch": name, "label": label, "title": title, "chosen_because": why, "patient_shown_as": r["patient"], "results_in_chart": len(chart),
                "required": {"outcome": r["kind"], "dose_mEq": r.get("dose")}, "chart": chart, "turns": turns,
                "matched_statement": v["ok"], "relaxed_pass": v["relaxed"], "released_pass": v["released"], "content_ok": v["c_ok"],
                "outcome": v["mode"], "stanford_as_released": bool(r.get("stanford_pass")),
                "stanford_checks_failed": bad, "closing_message": closing(r, None) if r["status"] == "completed" else "did not finish"}

    def pick(name, test, key):
        c = [k for k, v in detail.get(name, {}).items() if test(v)]
        return min(c, key=lambda k: (key(detail[name][k]), k)) if c else None
    ex = []
    both = lambda k: k in detail.get("replace_newest", {})  # noqa: E731
    n_rows = lambda v: len(v["chart"].rows)  # noqa: E731
    k = pick("replace", lambda v: v["mode"].startswith("latest result never returned; the newest result it received was not low") and v["info"]["kind"] == "searched_K_and_read_the_first_page_only"
             and 21 <= n_rows(v) <= 45 and both(v["row"]["label"]) and detail["replace_newest"][v["row"]["label"]]["ok"], n_rows)
    if k:
        ex.append(show("replace", k, "The most recent result was on the second page; no order", "the smallest potassium history of more than 20 results on which the run with the default sort order read only the first page and submitted no order, and the run on the same instance with the most recent results first passed"))
        ex.append(show("replace_newest", k, "The same instance with the most recent results first", "the same instance as the previous run, under the other condition"))
    k = pick("replace", lambda v: v["mode"] == "latest result never returned; dosed from the newest result it received" and n_rows(v) >= 21, n_rows)
    if k:
        ex.append(show("replace", k, "Dose computed from an older result", "the smallest potassium history on which the run ordered a dose that equals the rule applied to the most recent result on the first page, which was not the patient's most recent result"))
    k = pick("replace", lambda v: v["info"]["kind"] == "searched_only_by_2823-3" and not v["ok"], n_rows)
    if k:
        ex.append(show("replace", k, "Searched only under 2823-3", "the smallest potassium history on which the run searched only under the code 2823-3"))
    k = pick("replace", lambda v: v["ok"] and v["info"]["retrieved_latest"] and 8 <= n_rows(v) <= 20, lambda v: abs(n_rows(v) - 12))
    if k:
        ex.append(show("replace", k, "A potassium history that fits on one page; pass", "the passing run whose potassium history is closest to 12 results, a size chosen to show a history that fits on one page"))
    k = pick("notLow", lambda v: v["ok"] and v["info"]["retrieved_latest"] is False and v["info"]["kind"] == "searched_K_and_read_the_first_page_only" and 21 <= n_rows(v) <= 45, n_rows)
    if k:
        ex.append(show("notLow", k, "No-action instance passed without the most recent result", "the smallest potassium history of more than 20 results on a no-action instance where the run submitted no order and no response contained the patient's most recent result"))
    json.dump({"note": "Complete runs from the study, for illustration. Potassium values are from the benchmark's released, de-identified records. Patient identifiers are replaced, and every time in a chart is shifted by one amount, so that the instance falls on the benchmark's clock.",
               "examples": ex}, open(a.examples, "w"), indent=1)
    print("examples:", [(e["batch"], e["label"], e["results_in_chart"], e["matched_statement"]) for e in ex])


if __name__ == "__main__":
    main()
