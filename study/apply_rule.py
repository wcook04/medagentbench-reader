"""Apply the proved potassium program at every moment a potassium result was reported (with the
chart as it then stood) and at the benchmark clock, and summarise. Reads the private extract; writes aggregates only.

Usage: python3 study/apply_rule.py --records /private/records.json --out results/potassium_rule.json
"""
import argparse, collections, json, statistics, subprocess, os

HERE = os.path.dirname(os.path.abspath(__file__))
ORACLE = os.path.join(HERE, "..", "lean", ".lake", "build", "bin", "oracle")
CLOCK = 1699870500  # 2023-11-13T10:15:00+00:00


def oracle(decisions):
    """decisions: list of (now, [(t, tenths, final)]) -> list of outcome tuples from the proved program."""
    text = "".join(f"{now}|" + ";".join(f"{t},{k},{1 if f else 0}" for t, k, f in obs) + "\n" for now, obs in decisions)
    out = subprocess.run([ORACLE], input=text, capture_output=True, text=True, check=True).stdout.split("\n")
    res = []
    for line in out[: len(decisions)]:
        parts = line.split()
        res.append((parts[0],) + tuple(int(x) for x in parts[1:]))
    return res


def tenths(v):
    k = round(v * 10)
    assert abs(v * 10 - k) < 1e-6, v
    return k


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--records", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    pats = json.load(open(a.records))["patients"]

    # ---- the benchmark clock, all 100 patients and the 30 released cases
    dec = [(CLOCK, [(o["t"], tenths(o["v"]), o["status"] == "final") for o in pt["K"]]) for pt in pats]
    at_clock = oracle(dec)
    kinds_100 = collections.Counter(o[0] for o in at_clock)
    kinds_30 = collections.Counter(o[0] for o, pt in zip(at_clock, pats) if pt["task9"])
    doses_100 = sorted(o[3] for o in at_clock if o[0] == "replace")
    doses_30 = sorted(o[3] for o, pt in zip(at_clock, pats) if pt["task9"] and o[0] == "replace")

    # ---- the released grader's selection on the same rows in server order (first row at the latest time)
    def grader_value(rows):
        best = None
        for o in rows:
            if best is None or o["t"] > best["t"]:
                best = o
        return best

    grader_differs_30 = tied_30_all_high = 0
    for o, pt in zip(at_clock, pats):
        if not pt["task9"]:
            continue
        g = grader_value(pt["K"])
        g_low = g["v"] < 3.5
        ours_orders = o[0] == "replace"
        if o[0] == "conflict" or g_low != ours_orders:
            grader_differs_30 += 1
        if o[0] == "conflict":
            tied_30_all_high += min(tenths(r["v"]) for r in pt["K"] if r["t"] == o[1] and r["status"] == "final") >= 35

    # ---- every moment a potassium result was reported, with the chart as it then stood
    decisions, meta, charts = [], [], []
    for i, pt in enumerate(pats):
        for now in sorted({o["issued"] for o in pt["K"]}):
            chart = [o for o in pt["K"] if o["issued"] <= now]  # server order kept
            decisions.append((now, [(o["t"], tenths(o["v"]), o["status"] == "final") for o in chart]))
            meta.append((i, now))
            charts.append(chart)
    outs = oracle(decisions)

    # conflicts: does the disagreement change what the task requires?
    # and on how many of each kind the released grader, which takes the first tied row in server order, requires the orders
    conflict_kinds, grader_orders_on_conflict = collections.Counter(), collections.Counter()
    for chart, o in zip(charts, outs):
        if o[0] == "conflict":
            vals = {tenths(r["v"]) for r in chart if r["t"] == o[1] and r["status"] == "final"}
            kind = "all_at_or_above_3.5" if min(vals) >= 35 else "all_below_3.5_doses_differ" if max(vals) < 35 else "either_side_of_3.5"
            conflict_kinds[kind] += 1
            grader_orders_on_conflict[kind] += grader_value(chart)["v"] < 3.5

    # how many counted results share the latest time (what a short view of the chart must keep)
    group = collections.Counter()
    for chart in charts:
        top = max(r["t"] for r in chart if r["status"] == "final")
        group[sum(1 for r in chart if r["t"] == top and r["status"] == "final")] += 1

    # the released server's default search returns the 20 lowest-numbered results, not the latest 20
    def first_page_has_latest(chart):
        return max(r["t"] for r in chart) in {r["t"] for r in chart[:20]}
    page = collections.Counter()
    for chart, o in zip(charts, outs):
        page[(o[0], "over_20_rows" if len(chart) > 20 else "fits_one_page", first_page_has_latest(chart))] += 1
    page30 = collections.Counter(("over_20_rows" if len(pt["K"]) > 20 else "fits_one_page", first_page_has_latest(pt["K"])) for pt in pats if pt["task9"])
    kinds = collections.Counter(o[0] for o in outs)
    dose_hist = collections.Counter(o[3] for o in outs if o[0] == "replace")
    low_patients = len({m[0] for m, o in zip(meta, outs) if o[0] == "replace"})

    # ---- same-time results
    tie_times = tie_conflict = tie_issued_differs = 0
    for pt in pats:
        by_t = collections.defaultdict(list)
        for o in pt["K"]:
            by_t[o["t"]].append(o)
        for t, rows in by_t.items():
            if len(rows) > 1:
                tie_times += 1
                if len({r["v"] for r in rows}) > 1:
                    tie_conflict += 1
                    tie_issued_differs += len({r["issued"] for r in rows}) > 1

    # ---- availability: at the moment a result is issued, is it the most recent by specimen time?
    not_yet_reported = total_issue_points = 0
    for pt in pats:
        rows = pt["K"]
        for r in rows:
            total_issue_points += 1
            now = r["issued"]
            latest_taken = max(o["t"] for o in rows if o["t"] <= now)
            if any(o["t"] == latest_taken and o["issued"] > now for o in rows) and not any(
                o["t"] == latest_taken and o["issued"] <= now for o in rows
            ):
                not_yet_reported += 1

    # ---- what was ordered after a low result (descriptive)
    def kcl(o):
        t = o["text"].upper()
        return "CHLORIDE" in t and o["unit"] == "mEq" and o["t"] is not None

    after = collections.defaultdict(lambda: {"points": 0, "with_order_6h": 0, "ordered": []})
    for (i, now), o in zip(meta, outs):
        if o[0] != "replace":
            continue
        pt = pats[i]
        ords = [x for x in pt["orders"] if kcl(x) and now < x["t"] <= now + 6 * 3600]
        b = after[o[3]]
        b["points"] += 1
        if ords:
            b["with_order_6h"] += 1
            b["ordered"].append(sum(x["dose"] for x in ords))
    practice = []
    for dose in sorted(after):
        b = after[dose]
        practice.append({"rule_dose_mEq": dose, "decision_points": b["points"], "with_potassium_chloride_order_within_6h": b["with_order_6h"],
                         "median_ordered_mEq": statistics.median(b["ordered"]) if b["ordered"] else None,
                         "max_ordered_mEq": max(b["ordered"]) if b["ordered"] else None})
    all_real = [x["dose"] for pt in pats for x in pt["orders"] if kcl(x)]
    real_hist = collections.Counter(all_real)

    # ---- follow-up: is a potassium taken on the next calendar day
    fu = collections.Counter()
    for (i, now), o in zip(meta, outs):
        if o[0] != "replace":
            continue
        times = sorted({r["t"] for r in pats[i]["K"] if r["t"] > now})
        nxt_day = now // 86400 + 1
        fu["low_points"] += 1
        fu["next_calendar_day"] += any(t // 86400 == nxt_day for t in times)
        fu["next_day_06_to_10"] += any(t // 86400 == nxt_day and 6 * 3600 <= t % 86400 <= 10 * 3600 for t in times)
        fu["no_later_result"] += not times

    result = {
        "program": "Potassium.run (lean/Potassium.lean), executed through lean/Oracle.lean",
        "benchmark_clock": {
            "released_cases": {"n": sum(1 for pt in pats if pt["task9"]), "outcomes": dict(kinds_30), "doses_mEq": doses_30,
                               "cases_where_grader_requirement_depends_on_row_order_or_differs": grader_differs_30,
                               "conflict_cases_where_every_tied_value_is_at_or_above_3.5": tied_30_all_high},
            "all_patients": {"n": len(pats), "outcomes": dict(kinds_100), "doses_mEq": doses_100},
        },
        "every_report_moment": {
            "decision_points": len(outs), "patients": len(pats), "outcomes": dict(kinds),
            "patients_with_a_replacement_decision": low_patients,
            "dose_histogram_mEq": {str(k): v for k, v in sorted(dose_hist.items())},
            "decisions_over_20_mEq": sum(v for k, v in dose_hist.items() if k > 20),
            "decisions_over_40_mEq": sum(v for k, v in dose_hist.items() if k > 40),
            "decisions_over_60_mEq": sum(v for k, v in dose_hist.items() if k > 60),
            "conflicts": dict(conflict_kinds),
            "conflicts_where_the_released_grader_requires_orders": dict(grader_orders_on_conflict),
            "decisions_over_100_mEq": sum(v for k, v in dose_hist.items() if k > 100),
            "largest_dose_mEq": max(dose_hist),
        },
        "counted_results_at_the_latest_time": {str(k): v for k, v in sorted(group.items())},
        "default_search_first_page": {
            "note": "the released server answers a search with no _count and no _sort with its 20 lowest-numbered results",
            "released_cases": [{"chart": k[0], "first_page_holds_latest_result": k[1], "cases": v} for k, v in sorted(page30.items())],
            "report_moments": [{"outcome": k[0], "chart": k[1], "first_page_holds_latest_result": k[2], "moments": v} for k, v in sorted(page.items())],
        },
        "same_time_results": {"times_with_more_than_one_result": tie_times, "with_different_values": tie_conflict,
                              "of_those_with_different_issued_times": tie_issued_differs},
        "availability": {"result_issue_moments": total_issue_points,
                         "moments_when_a_more_recent_specimen_was_still_unreported": not_yet_reported},
        "orders_after_low_result": practice,
        "recorded_potassium_chloride_orders": {"n": len(all_real), "dose_histogram_mEq": {str(k): v for k, v in sorted(real_hist.items())}},
        "follow_up_after_low_result": dict(fu),
    }
    json.dump(result, open(a.out, "w"), indent=1)
    print(json.dumps(result)[:3500])


if __name__ == "__main__":
    main()
