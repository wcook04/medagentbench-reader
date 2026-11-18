"""Grade the stored task 9 runs and write aggregates only to results/agent_runs.json.

Each run is graded three ways, kept apart:
  content        did it place exactly the orders the instruction requires (right product, dose, route,
                 test and time, for this patient) and nothing else; for a result that is not low or
                 cannot be decided, did it place no order
  stanford       Stanford's unmodified task 9 grader, as released
  stanford_orders  the same grader with the run's closing message replaced by the empty list, which
                 the grader always accepts, so that only the orders are judged; and again with the
                 route additionally rewritten from the declared object to the plain string

  python3 study/agent/analyse.py --runs PRIVATE/agent/runs --cases PRIVATE/agent/cases2.json --resources PRIVATE/agent/k_resources.json --out results/agent_runs.json
"""
import argparse, collections, copy, glob, json, os, re, sys
from datetime import datetime
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
import run_task9 as R  # noqa: E402
from run_standin import real_get, add_error_row, conflict_values  # noqa: E402
from standin import Standin, REAL, BENCH_BASE, CLOCK, epoch  # noqa: E402

LAB_AT = datetime.fromisoformat("2023-11-14T08:00:00+00:00")


def oral(route):
    if isinstance(route, str):
        return route.strip().lower() == "oral"
    if isinstance(route, dict):
        texts = [route.get("text")] + [c.get("display") for c in route.get("coding", []) if isinstance(c, dict)]
        return any(isinstance(t, str) and t.strip().lower() in ("oral", "oral route", "po", "by mouth") for t in texts)
    return False


def codes(c):
    return [x.get("code") for x in (c or {}).get("coding", []) if isinstance(x, dict)] if isinstance(c, dict) else []


def content(kind, dose, pid, posts):
    """Returns (correct, reason)."""
    posts = [p for _, p in posts if isinstance(p, dict)]
    if kind != "replace":
        return (not posts, "" if not posts else "placed_orders_when_none_required")
    if not posts:
        return False, "no_orders"
    meds = [p for p in posts if p.get("resourceType") == "MedicationRequest"]
    labs = [p for p in posts if p.get("resourceType") == "ServiceRequest"]
    if len(meds) != 1 or len(labs) != 1 or len(posts) != 2:
        return False, "wrong_set_of_orders"
    med, lab = meds[0], labs[0]
    try:
        di = med["dosageInstruction"][0]
        dq = di["doseAndRate"][0]["doseQuantity"]
    except (KeyError, IndexError, TypeError):
        return False, "dose_not_stated"
    if not (isinstance(dq.get("value"), (int, float)) and abs(dq["value"] - dose) < 1e-6):
        return False, "wrong_dose"
    if not str(dq.get("unit", "")).strip().lower() == "meq" or R.NDC not in codes(med.get("medicationCodeableConcept")) or not oral(di.get("route")):
        return False, "wrong_product_unit_or_route"
    when = R._instant(lab.get("occurrenceDateTime"))
    if "2823-3" not in codes(lab.get("code")) or when != LAB_AT:
        return False, "wrong_test_or_time"
    if not all(str((p.get("subject") or {}).get("reference", "")).split("/")[-1] == pid for p in (med, lab)):
        return False, "wrong_patient"
    return True, ""


def history(row, closing=None, plain_route=False):
    h = [SimpleNamespace(role="user", content="")]
    for t in row["turns"]:
        c = t.get("content", "")
        if plain_route and t.get("action") == "POST" and "payload" in t:
            p = copy.deepcopy(t["payload"])
            for di in p.get("dosageInstruction", []) if isinstance(p.get("dosageInstruction"), list) else []:
                if isinstance(di, dict) and oral(di.get("route")):
                    di["route"] = "oral"
            c = "POST " + t["post_url"] + "\n" + json.dumps(p)
        h.append(SimpleNamespace(role="agent", content=c))
        if "reply" in t:
            h.append(SimpleNamespace(role="user", content=t["reply"]))
    return SimpleNamespace(history=h, result=row.get("result") if closing is None else closing)


def searches(row):
    s = set()
    for t in row["turns"]:
        if t.get("action") != "GET":
            continue
        u = t["url"]
        if "_getpages" in u:
            s.add("followed_next_page")
        elif "code=K" in u or "%7CK" in u or "|K" in u:
            s.add("searched_K")
            if "_sort" in u:
                s.add("sorted")
            if "_count" in u:
                s.add("set_count")
            if "date=" in u:
                s.add("date_filter")
        else:
            s.add("other_search")
    return s


def stanford_for(rows, res, cases):
    """Stanford's unmodified task 9 grader for one batch of runs, reading records from the server those runs
    used. Returns (stanford, mock): stanford(run, closing=None, plain_route=False) is True when the grader
    accepts the run; closing="[]" replaces the run's final answer with the empty list, and plain_route=True
    rewrites an oral route written as an object to the plain string "oral", before the grader reads the run."""
    prov = rows[0]["provenance"]
    real = prov["records"].startswith("released server")
    s = None
    if not real:
        s = Standin(REAL if rows[0]["set"] == "control" else BENCH_BASE)
        for r in rows:
            if r["set"] == "control":
                s.add_chart(r["patient"], res[r["patient"]]["K"], res[r["patient"]]["patient"])
            else:
                c = cases[r["label"].rstrip("e")]
                s.add_chart(c["patient"], res[c["source"]]["K"], res[c["source"]]["patient"], upto=c["moment"], shift=CLOCK - c["moment"], first_id=100000)
                if prov.get("added_error_row"):
                    add_error_row(s, c["patient"], c["kind"])

    def gget(url):
        g = real_get(url) if real else s.get(url)[0]
        if "data" not in g:
            raise RuntimeError("grader_transport_failed")
        return g
    grader, _ = R.load_grader(gget)
    base = REAL if rows[0]["set"] == "control" else BENCH_BASE

    def stanford(r, **kw):
        try:
            return grader({"id": "task9_x", "eval_MRN": r["patient"]}, history(r, **kw), base) is True
        except Exception:
            return False
    return stanford, s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", required=True)
    ap.add_argument("--cases", required=True)
    ap.add_argument("--resources", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    res = json.load(open(a.resources))
    cases = {c["label"]: c for c in json.load(open(a.cases))["cases"]}
    out = {"model": R.MODEL, "grader_sha256": R.GRADER_SHA, "benchmark_commit": R.PIN, "batches": []}
    for path in sorted(glob.glob(os.path.join(a.runs, "*.jsonl"))):
        rows = [json.loads(l) for l in open(path) if l.strip()]
        rows = list({r["label"]: r for r in reversed(rows) if "turns" in r}.values())[::-1]  # one run per moment
        if not rows:
            continue
        prov = rows[0]["provenance"]
        stanford, s = stanford_for(rows, res, cases)
        b = {"file": os.path.basename(path)[:-6], "set": rows[0]["set"], "context": prov.get("view", "none"), "records": prov["records"],
             "reasoning_effort": prov.get("reasoning_effort", "low"), "model": prov.get("model", R.MODEL), "newest_first": bool(prov.get("newest_first")), "runs": len(rows), "patients": len({r.get("source") or r["patient"] for r in rows}),
             "completed": sum(r["status"] == "completed" for r in rows)}
        C = collections.Counter
        reasons, behaviour, page, flags = C(), C(), C(), C()
        tally = C()
        by_dose = collections.defaultdict(lambda: [0, 0])
        by_size = collections.defaultdict(lambda: [0, 0])
        picked = C()
        for r in rows:
            ok, why = content(r["kind"], r.get("dose"), r["patient"], r.get("accepted_posts", []))
            if r["status"] != "completed":
                ok, why = False, "did_not_finish"
            tally["content_correct"] += ok
            reasons[why or "correct"] += 1
            st = r["status"] == "completed" and stanford(r)
            so = r["status"] == "completed" and stanford(r, closing="[]")
            sr = r["status"] == "completed" and stanford(r, closing="[]", plain_route=True)
            tally["stanford_as_released"] += st
            tally["stanford_orders_only"] += so
            tally["stanford_orders_only_route_as_plain_string"] += sr
            tally["content_correct_and_stanford_as_released"] += ok and st
            tally["content_correct_and_stanford_orders_only"] += ok and so
            tally["content_correct_and_stanford_orders_only_plain_route"] += ok and sr
            tally["stanford_orders_only_plain_route_but_content_wrong"] += sr and not ok
            sch = searches(r)
            behaviour[", ".join(sorted(sch)) or "no_search"] += 1
            chart = s.charts[r["patient"]] if s else res[r["patient"]]["K"]
            size = len(chart)
            edge = next(e for e in (10, 20, 40, 80, 160, 10 ** 9) if size <= e)
            by_size[edge][0] += ok
            by_size[edge][1] += 1
            if r["kind"] == "conflict" and r["set"] != "control":
                said = bool(re.search(r"conflict|differ|discrepan|discordan|inconsisten|two (potassium )?(results|values|levels)|cannot be decided|can ?not be determined", str(r.get("result") or ""), re.I))
                picked["closing_message_mentions_the_disagreement"] += said
                vals = conflict_values(res[cases[r["label"].rstrip("e")]["source"]], cases[r["label"].rstrip("e")])
                doses = [p["dosageInstruction"][0]["doseAndRate"][0]["doseQuantity"].get("value") for _, p in r.get("accepted_posts", [])
                         if isinstance(p, dict) and p.get("resourceType") == "MedicationRequest" and isinstance(p.get("dosageInstruction"), list) and p["dosageInstruction"]
                         and isinstance(p["dosageInstruction"][0], dict) and p["dosageInstruction"][0].get("doseAndRate")]
                if not r.get("accepted_posts"):
                    picked["placed_no_order"] += 1
                elif doses and doses[0] == 10 * (35 - min(vals)):
                    picked["dosed_from_the_lower_value"] += 1
                elif doses and len(vals) > 1 and doses[0] == 10 * (35 - max(vals)):
                    picked["dosed_from_the_higher_value"] += 1
                else:
                    picked["placed_other_orders"] += 1
            if chart:
                top = max(epoch(x["effectiveDateTime"]) for x in chart)
                holds = any(epoch(x["effectiveDateTime"]) == top for x in chart[:20])
                page[("fits_one_page" if len(chart) <= 20 else "over_20_results", holds, ok)] += 1
            for f in r.get("standin_flags", []):
                flags[f.split(":")[0]] += 1
            if r["kind"] == "replace":
                by_dose[r["dose"]][0] += ok
                by_dose[r["dose"]][1] += 1
        b.update(tally)
        b["reasons"] = dict(reasons)
        b["searches"] = dict(behaviour)
        b["by_first_page"] = [{"chart": k[0], "first_page_holds_latest_result": k[1], "content_correct": k[2], "runs": v} for k, v in sorted(page.items())]
        b["by_required_dose_mEq"] = {str(k): {"correct": v[0], "runs": v[1]} for k, v in sorted(by_dose.items())} if by_dose else None
        names = {10: "1 to 10", 20: "11 to 20", 40: "21 to 40", 80: "41 to 80", 160: "81 to 160", 10 ** 9: "over 160"}
        b["by_results_in_chart"] = [{"results": names[k], "correct": v[0], "runs": v[1]} for k, v in sorted(by_size.items())]
        b["conflict_choice"] = dict(picked) or None
        b["added_error_row"] = bool(prov.get("added_error_row"))
        b["searches_outside_the_stand_in"] = dict(flags)
        b["cost_usd"] = round(sum(t.get("usage", {}).get("cost", 0) for r in rows for t in r["turns"]), 4)
        out["batches"].append(b)
        print(b["file"], b["runs"], "content", b["content_correct"], "stanford", b["stanford_as_released"], b["stanford_orders_only"], b["stanford_orders_only_route_as_plain_string"], dict(reasons))
    json.dump(out, open(a.out, "w"), indent=1)


if __name__ == "__main__":
    main()
