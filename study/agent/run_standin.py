"""Run the released task 9 protocol on a hosted model, either on the 30 released cases against the
released record server (--set control) or on charts as they stood at earlier report moments, served
by standin.py (--set replace | notLow | conflict). Each run is graded by Stanford's unmodified task 9
grader, which reads the same records the agent did. Transcripts go to the private folder only.

  python3 study/agent/run_standin.py --set control --resources PRIVATE/agent/k_resources.json --out PRIVATE/agent/runs/control.jsonl --cost-cap 0.3
  python3 study/agent/run_standin.py --set replace --limit 40 --cases PRIVATE/agent/cases2.json --resources PRIVATE/agent/k_resources.json --out PRIVATE/agent/runs/replace.jsonl --cost-cap 0.3
"""
import argparse, copy, json, os, sys, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
import run_task9 as R  # noqa: E402
from standin import Standin, REAL, BENCH_BASE, CLOCK, epoch, iso  # noqa: E402
from apply_rule import oracle, tenths  # noqa: E402


def real_get(url):
    """The released harness's GET (utils.send_get_request), on the local copy of the released server."""
    import requests
    if not url.startswith(REAL):
        return {"error": "URL is outside the local FHIR tool"}
    try:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        return {"status_code": r.status_code, "data": r.json() if r.headers.get("Content-Type") == "application/json" else r.text}
    except Exception as e:
        return {"error": str(e)}


HINT = ("Searches on this record server return 20 results per page, in no time order. "
        "Add &_sort=-date&_count=5 to a search to get the most recent results first.")


def add_error_row(s, pid, kind):
    """Add one newer potassium result marked entered-in-error, with a value on the other side of 3.5.
    The statement's outcome does not change, because the added result is not final."""
    chart = s.charts[pid]
    e = copy.deepcopy(max(chart, key=lambda r: epoch(r["effectiveDateTime"])))
    e["id"] = str(max(int(r["id"]) for r in chart) + 1)
    e["status"], e["effectiveDateTime"], e["issued"] = "entered-in-error", iso(CLOCK - 30), iso(CLOCK)
    e["valueQuantity"]["value"] = 4.5 if kind == "replace" else 3.0
    chart.append(e)


def conflict_values(src, c):
    return sorted({tenths(r["valueQuantity"]["value"]) for r in src["K"]
                   if epoch(r["issued"]) <= c["moment"] and epoch(r["effectiveDateTime"]) == c["oracle"][1] and r["status"] == "final"})


RULES = ("Rules for reading these results: a result counts only if its status is final. If the counted results taken at the "
         "most recent time have different values, the task cannot be decided from the record: place no order and say so when you finish.")


def table_view(rows, shown=8):
    """The potassium results as a short flowsheet, most recent first. Prepared by code, no judgement in it.
    It always holds every final result taken at the latest time (and anything newer), which is the
    condition of `Potassium.run_sufficient_view`; older rows are added up to `shown`."""
    rows = sorted(rows, key=lambda r: -epoch(r["effectiveDateTime"]))
    finals = [epoch(r["effectiveDateTime"]) for r in rows if r["status"] == "final"]
    if finals:
        shown = max(shown, sum(1 for r in rows if epoch(r["effectiveDateTime"]) >= max(finals)))
    lines = ["Potassium results in this patient's record, most recent first (code K):", "taken | reported | value | status"]
    for r in rows[:shown]:
        q = r.get("valueQuantity") or {}
        lines.append(f"{r['effectiveDateTime']} | {r['issued']} | {q.get('value')} {q.get('unit') or '(no unit)'} | {r['status']}")
    if len(rows) > shown:
        lines.append(f"({len(rows) - shown} earlier results not shown)")
    if not rows:
        lines.append("(none)")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", required=True, choices=["control", "replace", "notLow", "conflict", "conflictHard"])
    ap.add_argument("--cases")
    ap.add_argument("--via", default="auto", choices=["auto", "standin"], help="control only: serve the released cases' full charts from the stand-in")
    ap.add_argument("--resources", required=True)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--skip", type=int, default=0)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cost-cap", type=float, required=True)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--view", default="none", choices=["none", "hint", "table", "contract"],
                    help="what is added to the task context: nothing (as released), one sentence about paging, a time-ordered table of the potassium results, or the table plus the rule in two sentences")
    ap.add_argument("--newest-first", action="store_true", help="the record search returns the newest results first when the model asks for no sorting")
    ap.add_argument("--model", help="a hosted model other than the default")
    ap.add_argument("--add-error-row", action="store_true", help="add a newer result marked entered-in-error to each chart")
    ap.add_argument("--effort", default="low", choices=["low", "medium", "high"], help="the model's reasoning effort")
    a = ap.parse_args()
    res = json.load(open(a.resources))
    prompt, funcs, template, released, prov = R.load_benchmark()
    flags, lock = {}, threading.Lock()
    if a.set == "control":
        base, get = REAL, real_get
        mrns = [m for m in sorted(res) if res[m]["task9"]]
        outs = oracle([(CLOCK, [(epoch(r["effectiveDateTime"]), tenths(r["valueQuantity"]["value"]), r["status"] == "final") for r in res[m]["K"]]) for m in mrns])
        cases = [{"label": res[m]["task9"], "patient": m, "set": "control", "kind": o[0], "oracle": list(o), "dose": o[3] if o[0] == "replace" else None, "rows": len(res[m]["K"])}
                 for m, o in zip(mrns, outs)]
        prov["records"] = "released server, local copy"
        if a.via == "standin":
            s = Standin(REAL)
            for m in mrns:
                s.add_chart(m, res[m]["K"], res[m]["patient"])
            get = lambda url: s.get(url)[0]  # noqa: E731
            prov["records"] = "stand-in holding the released cases' full charts"
    else:
        base, s = BENCH_BASE, Standin(BENCH_BASE, newest_first=a.newest_first)
        cases = [c for c in json.load(open(a.cases))["cases"] if c["set"] == a.set.replace("Hard", "")]
        if a.set == "conflictHard":  # the disagreement changes what would be ordered
            cases = [c for c in cases if min(conflict_values(res[c["source"]], c)) < 35]
        cases = cases[a.skip:]
        if a.limit:
            cases = cases[: a.limit]
        for c in cases:
            src = res[c["source"]]
            s.add_chart(c["patient"], src["K"], src["patient"], upto=c["moment"], shift=CLOCK - c["moment"], first_id=100000)
            if a.add_error_row:
                add_error_row(s, c["patient"], c["kind"])
                c["label"] += "e"

        def get(url):
            r, flag = s.get(url)
            if flag:
                with lock:
                    flags.setdefault(next((c["patient"] for c in cases if c["patient"] in url), "?"), []).append(flag)
            return r
        prov["records"] = "stand-in (study/agent/standin.py)"
        for c in cases:
            shift = CLOCK - c["moment"]
            c["added_context"] = {"none": "", "hint": HINT, "table": table_view(s.charts[c["patient"]]), "contract": table_view(s.charts[c["patient"]]) + "\n" + RULES}[a.view]
    prov["view"] = a.view
    prov["added_error_row"] = bool(a.add_error_row)
    prov["newest_first"] = bool(a.newest_first)

    def grader_get(url):
        r = get(url)
        if "data" not in r:
            raise RuntimeError("grader_transport_failed")
        return r
    grader, extract_posts = R.load_grader(grader_get)
    done = {json.loads(l)["label"] for l in open(a.out) if l.strip()} if os.path.exists(a.out) else set()
    cases = [c for c in cases if c["label"] not in done]
    if a.model:  # a second model: any endpoint that keeps no data, no fixed provider
        R.MODEL, R.PROVIDER = a.model, None
        R.ROUTE = {"data_collection": "deny", "zdr": True}
    prov["model"] = R.MODEL
    R.REASONING = {"effort": a.effort}
    prov["reasoning_effort"] = a.effort
    router = R.Router(a.seed)
    print(f"{len(cases)} cases, set {a.set}, cap ${a.cost_cap}", flush=True)
    t0, n = time.time(), 0
    with open(a.out, "a") as out, ThreadPoolExecutor(a.workers) as pool:
        tmpl = lambda c: dict(template, context=template["context"] + ("\n" + c["added_context"] if c.get("added_context") else ""))  # noqa: E731
        jobs = {pool.submit(R.run_case, dict(c), router, prompt, funcs, tmpl(c), released, base, get, grader, extract_posts): c for c in cases}
        for j in as_completed(jobs):
            c = jobs[j]
            try:
                row = j.result()
            except Exception as e:
                row = {"label": c["label"], "set": c["set"], "status": "harness_error:" + type(e).__name__ + ":" + str(e)[:200]}
            row.update(seed=a.seed, provenance=prov, rows=c.get("rows"), source=c.get("source"), moment=c.get("moment"), standin_flags=flags.get(c["patient"], []))
            out.write(json.dumps(row) + "\n")
            out.flush()
            n += 1
            if n % 10 == 0 or n == len(cases):
                print(f"{n}/{len(cases)} cost ${router.cost:.4f} {time.time() - t0:.0f}s", flush=True)
            if router.cost >= a.cost_cap:
                router.halt.set()
    print(json.dumps({"batch_cost": round(router.cost, 6), "runs": n}), flush=True)


if __name__ == "__main__":
    main()
