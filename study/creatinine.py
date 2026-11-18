"""Apply the proved creatinine-rise program (KDIGO 2012 criterion 1 only: a rise of at least
0.3 mg/dL within 48 hours) at every moment a creatinine result was reported, with the chart as it
then stood, and once per patient on the full record. Cross-check every decision point against an
independent brute-force check in plain Python. Reads the private extract; writes aggregates only.

This is not an acute kidney injury diagnosis: criterion 2 (1.5x baseline within 7 days) and
criterion 3 (urine output) are out of scope.

Usage: python3 study/creatinine.py --records /private/records.json --out results/creatinine.json
"""
import argparse, collections, json, os, statistics, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ORACLE = os.path.join(HERE, "..", "lean", ".lake", "build", "bin", "croracle")
WINDOW = 48 * 3600
MIN_RISE = 30  # hundredths of a mg/dL


def oracle(decisions):
    """decisions: list of (now, [(t, hundredths, final)]) -> outcome tuples from the proved program."""
    text = "".join(f"{now}|" + ";".join(f"{t},{v},{1 if f else 0}" for t, v, f in obs) + "\n" for now, obs in decisions)
    out = subprocess.run([ORACLE], input=text, capture_output=True, text=True, check=True).stdout.split("\n")
    res = []
    for line in out[: len(decisions)]:
        parts = line.split()
        assert parts and parts[0] in ("noRise", "rise"), "oracle error"
        res.append((parts[0],) + tuple(int(x) for x in parts[1:]))
    assert len(res) == len(decisions)
    return res


def brute(now, obs):
    """Independent check: (first rise time or None, set of qualifying (a, b) pairs)."""
    el = [o for o in obs if o[2] and o[0] <= now]
    qual = [(a, b) for a in el for b in el
            if a[0] < b[0] and b[0] - a[0] <= WINDOW and b[1] - a[1] >= MIN_RISE]
    return (min(b[0] for _, b in qual) if qual else None), qual


def hundredths(v):
    k = round(v * 100)
    assert abs(v * 100 - k) < 1e-6, "value with more than two decimals"
    return k


def quantiles(xs):
    xs = sorted(xs)
    if not xs:
        return None
    q = statistics.quantiles(xs, n=4, method="inclusive") if len(xs) > 1 else [xs[0]] * 3
    return {"n": len(xs), "min": xs[0], "q1": q[0], "median": q[1], "q3": q[2], "max": xs[-1]}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--records", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    pats = json.load(open(a.records))["patients"]

    # ---- which rows are used
    excluded = collections.Counter()
    total_rows = 0
    charts = []  # per patient: list of (t, issued, hundredths, final)
    for pt in pats:
        rows = []
        for r in pt["CR"]:
            total_rows += 1
            if r.get("unit") != "mg/dL":
                excluded["unit_missing" if r.get("unit") is None else f"unit_{r.get('unit')}"] += 1
                continue
            if not isinstance(r.get("v"), (int, float)) or isinstance(r.get("v"), bool):
                excluded["value_not_numeric"] += 1
                continue
            if not isinstance(r.get("t"), int) or not isinstance(r.get("issued"), int):
                excluded["time_or_issued_missing"] += 1
                continue
            rows.append((r["t"], r["issued"], hundredths(r["v"]), r.get("status") == "final"))
        charts.append(rows)
    used_rows = sum(len(c) for c in charts)
    status = collections.Counter(f for c in charts for _, _, _, f in c)

    # ---- decision points: each distinct report moment, chart as it then stood
    decisions, meta = [], []
    for i, rows in enumerate(charts):
        for now in sorted({iss for _, iss, _, _ in rows}):
            obs = [(t, v, f) for t, iss, v, f in rows if iss <= now]
            decisions.append((now, obs))
            meta.append((i, now))
    outs = oracle(decisions)

    # ---- full record, once per patient
    full_dec = []
    for rows in charts:
        end = max([max(t, iss) for t, iss, _, _ in rows], default=0) + 1
        full_dec.append((end, [(t, v, f) for t, _, v, f in rows]))
    full_outs = oracle(full_dec)

    # ---- independent cross-check on every decision point (and the full records)
    agree = disagree = 0
    for (now, obs), o in list(zip(decisions, outs)) + list(zip(full_dec, full_outs)):
        T, qual = brute(now, obs)
        if o[0] == "noRise":
            ok = T is None
        else:
            _, firstAt, ta, va, tb, vb = o
            pair_ok = any(x[0] == ta and x[1] == va and y[0] == tb and y[1] == vb for x, y in qual)
            ok = T == firstAt and tb == firstAt and pair_ok
        agree += ok
        disagree += not ok

    # ---- first establishment: outcome goes from noRise to rise at a report moment
    by_patient = collections.defaultdict(list)
    for (i, now), o, (_, obs) in zip(meta, outs, decisions):
        by_patient[i].append((now, o, obs))
    est_points = 0
    est_patients = set()
    delays_min, not_latest_witness, not_latest_report, rise_bins, gap_bins = [], 0, 0, collections.Counter(), collections.Counter()
    firstAt_moved_earlier = firstAt_moved_later = 0
    established_at_first_report_moment = 0
    for i, seq in by_patient.items():
        prev = None
        for k, (now, o, obs) in enumerate(seq):
            if o[0] == "rise" and (prev is None or prev[0] == "noRise"):
                est_points += 1
                est_patients.add(i)
                established_at_first_report_moment += k == 0
                _, T, ta, va, tb, vb = o
                delays_min.append((now - tb) / 60)
                latest_taken = max(t for t, _, f in obs if f and t <= now)
                not_latest_witness += tb != latest_taken
                new_rows = [t for t, iss, _, _ in charts[i] if iss == now]
                not_latest_report += latest_taken not in new_rows
                d = vb - va
                rise_bins["2.0+" if d >= 200 else f"{d // 10 / 10:.1f}-{d // 10 / 10 + 0.1:.1f}"] += 1
                h = (tb - ta) / 3600
                gap_bins[f"{int(h // 6) * 6}-{int(h // 6) * 6 + 6}h"] += 1
            elif o[0] == "rise" and prev is not None and prev[0] == "rise" and o[1] != prev[1]:
                firstAt_moved_earlier += o[1] < prev[1]
                firstAt_moved_later += o[1] > prev[1]
            prev = o

    def order_bins(c, keyf):
        return {k: c[k] for k in sorted(c, key=keyf)}

    result = {
        "program": "Creatinine.run (lean/Creatinine.lean), executed through lean/CrOracle.lean",
        "finding": "the record holds two final creatinine results, the later taken at most 48 h after the earlier, "
                   "with the later at least 0.30 mg/dL higher (KDIGO 2012 criterion 1 only; not an AKI diagnosis)",
        "rows": {"total": total_rows, "used": used_rows, "excluded_by_reason": dict(excluded),
                 "used_rows_by_final_status": {str(k): v for k, v in status.items()}},
        "patients": len(pats),
        "patients_with_any_used_row": sum(1 for c in charts if c),
        "decision_points": len(outs),
        "decision_point_outcomes": dict(collections.Counter(o[0] for o in outs)),
        "full_record": {"patients_with_a_rise": sum(1 for o in full_outs if o[0] == "rise"),
                        "patients_without": sum(1 for o in full_outs if o[0] == "noRise")},
        "first_establishment": {
            "patients": len(est_patients),
            "decision_points": est_points,
            "at_the_patients_first_report_moment": established_at_first_report_moment,
            "delay_from_later_specimen_taken_to_record_establishing_minutes": quantiles(delays_min),
            "later_specimen_of_witness_pair_not_the_most_recently_taken_specimen_in_chart": not_latest_witness,
            "no_result_reported_at_that_moment_was_the_most_recently_taken_specimen": not_latest_report,
            "rise_size_mg_dL_histogram": order_bins(rise_bins, lambda k: 99 if k == "2.0+" else float(k.split("-")[0])),
            "hours_between_specimens_histogram": order_bins(gap_bins, lambda k: int(k.split("-")[0])),
        },
        "after_establishment": {"report_moments_where_first_rise_time_moved_earlier": firstAt_moved_earlier,
                                "report_moments_where_first_rise_time_moved_later": firstAt_moved_later},
        "cross_check_brute_force_python": {"checked": agree + disagree, "agree": agree, "disagree": disagree,
                                           "covers": "every decision point plus every full record; first-rise time and witness pair validity"},
        "code_label_note": "local FHIR server, Observation?code=CR: code.coding = system http://loinc.org, code 'CR', "
                           "display 'CR', text 'CR'; category 'laboratory'; unit mg/dL; no specimen element. 'CR' is not a "
                           "LOINC code and nothing in the resource says serum or plasma.",
    }
    json.dump(result, open(a.out, "w"), indent=1)
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
