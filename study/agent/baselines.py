"""Two scripted baselines, run through the benchmark's protocol and graded by Stanford's unmodified grader.

  null agent           finishes at once with an empty answer and sends no request (the "null agent" of
                       Mantravadi et al., arXiv 2607.01470)
  first-page baseline  sends one potassium search with no sorting and no page size, reads the page that
                       comes back (20 results on the released server), takes the result with the latest
                       sample time on that page, and applies the task's dosing rule; it never follows
                       the link to the next page
  full-chart baseline  the same program with one change: its search asks for up to 5,000 results in one
                       page, which is the request Stanford's grader itself sends

Each baseline produces the same kind of transcript an agent produces (GET, POST, FINISH messages and the
harness's replies), and Stanford's task 9 grader reads that transcript. The orders are written in the
form the released grader accepts: the route as the plain string "oral", and the final answer as the
empty list. Neither baseline uses a language model.

The 30 released instances are run against the local copy of the released server. The derived instances
are run against the mock server (standin.py), one chart at a time.

  python3 study/agent/baselines.py --cases PRIVATE/agent/cases2.json --resources PRIVATE/agent/k_resources.json --out results/baselines.json
"""
import argparse, collections, json, os, sys
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
import run_task9 as R  # noqa: E402
from run_standin import real_get  # noqa: E402
from standin import Standin, REAL, BENCH_BASE, CLOCK, epoch  # noqa: E402
from audit import boot, by_patient, share  # noqa: E402

NOW = "2023-11-13T10:15:00+00:00"
NEXT_MORNING = "2023-11-14T08:00:00+00:00"


def null_agent(base, mrn):
    yield "FINISH([])"


def first_page_baseline(base, mrn):
    yield from _search_then_order(base, mrn, f"GET {base}Observation?code=K&patient={mrn}")


def full_chart_baseline(base, mrn):
    """The same program with one change: it asks for every result in one page, as the grader itself does."""
    yield from _search_then_order(base, mrn, f"GET {base}Observation?code=K&patient={mrn}&_count=5000")


def _search_then_order(base, mrn, search):
    reply = yield search
    data = reply if isinstance(reply, dict) else json.loads(reply)
    latest_time, value = None, None
    for e in data.get("entry", []):
        t = epoch(e["resource"]["effectiveDateTime"])
        if latest_time is None or t > latest_time:  # the first listed among results that share the latest time, as in the grader
            latest_time, value = t, e["resource"]["valueQuantity"]["value"]
    if value is not None and value < 3.5:
        dose = round((3.5 - value) / 0.1 * 10, 6)
        subject = {"reference": f"Patient/{mrn}"}
        yield "POST " + base + "MedicationRequest\n" + json.dumps({
            "resourceType": "MedicationRequest",
            "medicationCodeableConcept": {"coding": [{"system": "http://hl7.org/fhir/sid/ndc", "code": R.NDC, "display": "potassium chloride"}]},
            "authoredOn": NOW,
            "dosageInstruction": [{"route": "oral", "doseAndRate": [{"doseQuantity": {"value": dose, "unit": "mEq"}}]}],
            "status": "active", "intent": "order", "subject": subject})
        yield "POST " + base + "ServiceRequest\n" + json.dumps({
            "resourceType": "ServiceRequest",
            "code": {"coding": [{"system": "http://loinc.org", "code": "2823-3", "display": "Potassium [Moles/volume] in Serum or Plasma"}]},
            "authoredOn": NOW, "status": "active", "intent": "order", "priority": "stat", "subject": subject,
            "occurrenceDateTime": NEXT_MORNING})
    yield "FINISH([])"


def transcript(agent, base, mrn, get):
    """Drive one baseline through the harness's protocol (run_task9.run_case, without a model)."""
    history, result, rounds, placed, dose = [SimpleNamespace(role="user", content="")], None, 0, False, None
    gen = agent(base, mrn)
    msg = next(gen)
    while True:
        rounds += 1
        history.append(SimpleNamespace(role="agent", content=msg))
        if msg.startswith("GET"):
            g = get(msg[3:].strip() + "&_format=json")
            assert "data" in g, g
            history.append(SimpleNamespace(role="user", content=f"Here is the response from the GET request:\n{g['data']}. Please call FINISH if you have got "
                                                                "answers for all the questions and finished all the requested tasks"))
            msg = gen.send(g["data"])
        elif msg.startswith("POST"):
            placed = True
            p = json.loads("\n".join(msg.split("\n")[1:]))
            if p["resourceType"] == "MedicationRequest":
                dose = p["dosageInstruction"][0]["doseAndRate"][0]["doseQuantity"]["value"]
            history.append(SimpleNamespace(role="user", content=R.ACK))
            msg = next(gen)
        else:
            result = msg[len("FINISH("):-1]
            break
    assert rounds <= R.MAX_ROUNDS
    return SimpleNamespace(history=history, result=result), placed, dose


def group_of(times):
    if len(times) <= 20:
        return "20 results or fewer"
    return "over 20 results, most recent on the first page" if max(times) in times[:20] else "over 20 results, most recent not on the first page"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True)
    ap.add_argument("--resources", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    res = json.load(open(a.resources))
    cases = json.load(open(a.cases))["cases"]
    agents = {"null_agent": null_agent, "first_page_baseline": first_page_baseline, "full_chart_baseline": full_chart_baseline}
    out = {"grader": "Stanford's task 9 grader, unmodified (sha256 " + R.GRADER_SHA + ")",
           "note": "pass means Stanford's released grader returned True for the transcript the baseline produced"}

    # ---- the 30 released instances, on the local copy of the released server
    grader, _ = R.load_grader(lambda url: real_get(url))
    rel = {k: collections.Counter() for k in agents}
    first_page_has_latest = over_20 = 0
    mrns = [m for m in sorted(res) if res[m]["task9"]]
    for m in mrns:
        times = [epoch(r["effectiveDateTime"]) for r in res[m]["K"]]
        over_20 += len(times) > 20
        first_page_has_latest += bool(times) and max(times) in times[:20]
        for name, agent in agents.items():
            run, placed, _ = transcript(agent, REAL, m, real_get)
            ok = grader({"id": "task9_x", "eval_MRN": m}, run, REAL) is True
            rel[name]["pass"] += ok
            rel[name]["placed_orders"] += placed
    out["released_30"] = {"instances": len(mrns), "server": "local copy of the released server", "charts_over_20_results": over_20,
                          "first_page_holds_most_recent_result": first_page_has_latest,
                          **{k: dict(v) for k, v in rel.items()}}

    # ---- every derived instance, on the mock server, one chart at a time
    tally = {k: collections.defaultdict(collections.Counter) for k in agents}
    by_chart = collections.defaultdict(lambda: [0, 0])
    per_patient = []
    decision_differs = 0
    for c in cases:
        s = Standin(BENCH_BASE)
        s.add_chart(c["patient"], res[c["source"]]["K"], res[c["source"]]["patient"], upto=c["moment"], shift=CLOCK - c["moment"], first_id=100000)
        get = lambda url: s.get(url)[0]  # noqa: E731
        grader, _ = R.load_grader(get)
        times = [epoch(r["effectiveDateTime"]) for r in s.charts[c["patient"]]]
        for name, agent in agents.items():
            run, placed, dose = transcript(agent, BENCH_BASE, c["patient"], get)
            ok = grader({"id": "task9_x", "eval_MRN": c["patient"]}, run, BENCH_BASE) is True
            t = tally[name][c["kind"]]
            t["instances"] += 1
            t["pass"] += ok
            t["placed_orders"] += placed
            if name == "full_chart_baseline" and c["kind"] == "replace":
                t["dose_equals_the_specification"] += bool(placed) and abs(dose - c["dose"]) < 1e-6
            if name == "first_page_baseline":
                if c["kind"] == "replace":
                    by_chart[group_of(times)][0] += ok
                    by_chart[group_of(times)][1] += 1
                    per_patient.append((c["source"], ok))
                    decision_differs += not (placed and abs(dose - c["dose"]) < 1e-6)
                    t["placed_orders_with_another_dose"] += placed and abs(dose - c["dose"]) >= 1e-6
                if c["kind"] == "conflict":
                    t["placed_no_order_as_the_specification_requires"] += not placed
    out["derived"] = {"server": "mock server (study/agent/standin.py), default order as released", "instances": len(cases),
                      **{k: {kind: dict(v) for kind, v in t.items()} for k, t in tally.items()}}
    g = by_patient(per_patient)
    sh = [v[0] / v[1] for v in g.values()]
    out["first_page_baseline_on_action_required_instances"] = {
        "instances": sum(v[1] for v in g.values()), "pass": sum(v[0] for v in g.values()),
        "decision_or_dose_differs_from_the_specification": decision_differs,
        "interval_95_resampling_patients": boot(dict(g), share),
        "mean_of_patient_pass_rates": round(sum(sh) / len(sh), 4), "patients": len(g),
        "by_chart": {k: {"pass": v[0], "instances": v[1]} for k, v in sorted(by_chart.items())}}
    json.dump(out, open(a.out, "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
