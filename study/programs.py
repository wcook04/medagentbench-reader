"""Ask a model to write the potassium task as one program, then check each program against the
proved program on every moment a potassium result was reported in the released records.

The model is sent the task text only. No patient record leaves this machine in this experiment.
Programs written by the model are tested, not proved.

Conditions:
  instruction  the task text and the function's interface
  contract     the same, plus the points the task text leaves open, decided in plain words
  repaired     an `instruction` program, sent back with one small made-up chart on which it differs
               from the proved program and the outcome required there, for up to 4 rounds

Usage:
  python3 study/programs.py generate --condition instruction --n 20 --out results/programs
  python3 study/programs.py repair --programs results/programs --rounds 4
  python3 study/programs.py check --records /private/records.json --programs results/programs --out results/programs.json
"""
import argparse, collections, glob, itertools, json, os, random, re, shutil, subprocess, sys, tempfile, urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from apply_rule import oracle, tenths, CLOCK  # noqa: E402

MODEL = "deepseek/deepseek-v4.1-flash-1017"
INSTRUCTION = ("Check patient {patient}'s most recent potassium level. If low, then order replacement potassium according "
               "to dosing instructions. Also pair this order with a morning serum potassium level to be completed the next day at 8am. ")
CONTEXT = ("It's {now} now. The code for potassium is \"K\".The NDC for replacement potassium is 40032-917-01. Dosing instructions: "
           "for every 0.1 mEq/L (or mmol/L) below threshold, order 10 mEq potassium oral repletion) to reach a goal of 3.5 serum level. "
           "The LOINC code for serum potassium level is 2823-3.")

INTERFACE = """Write `def plan(observations, now):`

- `observations` is the patient's potassium Observation search result from the record server: a list of dicts, in the order the server returned them, each with `effectiveDateTime` (ISO 8601 with offset; when the specimen was taken), `value` (number), `unit` (string or None) and `status` (FHIR Observation status).
- `now` is the task's current time, an ISO 8601 string with offset.

Return a dict with exactly these keys:
- `order_replacement`: True or False
- `dose_mEq`: a number, or None when nothing is ordered
- `repeat_potassium_at`: an ISO 8601 string with offset for the paired potassium level, or None when nothing is ordered
- `cannot_apply`: None, or a short string saying why the task cannot be decided from these observations

Use only the Python standard library. Reply with one Python code block and nothing else."""

HEAD = """Below is a task exactly as it is given to an assistant working in a hospital record system, with the patient and the time left as placeholders. Write one Python function that carries it out for any patient at any time.

Task: \"""" + INSTRUCTION + """\"
Context: \"""" + CONTEXT + """\"

"""
PROMPTS = {
    "instruction": HEAD + INTERFACE,
    "contract": HEAD + """The task text leaves some points open. Decide them this way:
1. A result counts only if its status is `final` and its specimen was taken at or before `now`. Values are in mmol/L; read a result with no unit as mmol/L.
2. "Most recent" is by specimen time. If the most recent time has several counted results with different values, order nothing and set `cannot_apply`. If they all have the same value, use it. If no result counts, order nothing.
3. "Low" is below 3.5 mmol/L. The dose is 10 mEq for each 0.1 mmol/L below 3.5, with no rounding and no upper limit. When the most recent result is 3.5 or above, order nothing and leave `cannot_apply` as None.
4. "The next day at 8am" is 08:00:00 on the calendar day after `now`, in the same UTC offset as `now`.

""" + INTERFACE,
}
REPAIR = """Below is a task as it is given to an assistant working in a hospital record system, the interface of a Python function that carries it out, and a function written for it.

Task: \"""" + INSTRUCTION + """\"
Context: \"""" + CONTEXT + """\"

""" + INTERFACE.replace("Write `def plan", "The function is `def plan").replace("\n\nUse only the Python standard library. Reply with one Python code block and nothing else.", "") + """

The function:
```python
{code}
```

On the call below the function does not return what the task requires.
plan(observations={obs}, now={now!r})
It returned: {got}
The task requires: {want}

Correct the function so that it is right for every patient and time, not only for this call. Use only the Python standard library. Reply with the whole corrected function in one Python code block and nothing else."""


def call(prompt, seed):
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent"))
    from balance import key
    key()  # loads OPENROUTER_API_KEY if it is not already set
    body = {"model": MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 1.0, "seed": seed, "max_tokens": 32000,
            "reasoning": {"effort": "low"},
            "provider": {"data_collection": "deny", "zdr": True, "allow_fallbacks": False, "only": ["wafer/us"]},
            "usage": {"include": True}}
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"], "Content-Type": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=240) as r:
                d = json.load(r)
            text = d["choices"][0]["message"]["content"] or ""
            m = re.search(r"```(?:python)?\n(.*?)```", text, re.S)
            code = m.group(1) if m else text
            if "def plan" in code:
                return code, (d.get("usage") or {}).get("cost", 0) or 0
        except Exception as e:  # network or provider error: try again
            print("retry", type(e).__name__)
    return None, 0


def generate(a):
    os.makedirs(a.out, exist_ok=True)
    cost = 0.0
    for seed in range(1, a.n + 1):
        path = os.path.join(a.out, f"{a.condition}_{seed:02d}.py")
        if os.path.exists(path):
            continue
        code, c = call(PROMPTS[a.condition], seed)
        cost += c
        if code is None:
            print("no program returned for seed", seed)
            continue
        open(path, "w").write(f"# Written by {MODEL}, condition \"{a.condition}\", seed {seed}. Unedited.\n" + code)
    print("cost", round(cost, 5))


# ---------------------------------------------------------------- test charts

def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).isoformat()


def fhir_rows(rows):
    return [{"effectiveDateTime": iso(r[0]), "value": r[1] / 10, "unit": r[3] if len(r) > 3 else "mmol/L", "status": "final" if r[2] else "entered-in-error"} for r in rows]


BASE = 1699870500
CONSTRUCTED = [
    (BASE, []),
    (BASE, [(BASE - 7200, 35, True)]),
    (BASE, [(BASE - 7200, 34, True)]),
    (BASE, [(BASE - 7200, 30, True), (BASE - 3600, 41, True)]),
    (BASE, [(BASE - 3600, 41, True), (BASE - 7200, 30, True)]),
    (BASE, [(BASE, 31, True)]),
    (BASE + 13 * 3600 + 44 * 60, [(BASE, 33, True)]),  # 23:59, the next day's 8am is 8 hours away
    (BASE - 10 * 3600 - 14 * 60, [(BASE - 12 * 3600, 33, True)]),  # 00:01
    (BASE, [(BASE - 7200, 10, True)]),
    (BASE, [(BASE - 7200, 29, True), (BASE - 7200, 29, True)]),
    (BASE, [(BASE - 7200, 31, True, None)]),  # no unit
]


def small_charts():
    """Every chart of up to three results drawn from 18 made-up results: two past times and one future
    time, three values (3.0, 3.3, 3.6), final or entered-in-error. No patient data."""
    pool = [(BASE + dt, v, f) for dt in (-7200, -3600, 3600) for v in (30, 33, 36) for f in (True, False)]
    return [(BASE, list(c)) for n in range(0, 4) for c in itertools.product(pool, repeat=n)]


def suites(records):
    pats = json.load(open(records))["patients"]
    rng = random.Random(7)
    S = collections.defaultdict(list)  # name -> list of (now, rows[(taken, tenths, final, unit)])
    for pt in pats:
        K = pt["K"]
        row = lambda o: (o["t"], tenths(o["v"]), o["status"] == "final", o["unit"])  # noqa: E731
        for now in sorted({o["issued"] for o in K}):
            chart = [row(o) for o in K if o["issued"] <= now]
            S["as_reported"].append((now, chart))
            if any(o["t"] > now for o in K) and rng.random() < 0.15:
                S["later_results_present"].append((now, [row(o) for o in K]))
            if rng.random() < 0.12:
                top = max(r[0] for r in chart)
                latest = max(r[1] for r in chart if r[0] == top)
                S["newer_result_not_final"].append((now, chart + [(now, 30 if latest >= 35 else 45, False, "mmol/L")]))
        if pt["task9"]:
            S["released_30"].append((CLOCK, [row(o) for o in K]))
    S["constructed"] = CONSTRUCTED
    S["small_charts"] = small_charts()
    return S


def expect(tests):
    return oracle([(now, [r[:3] for r in rows]) for now, rows in tests])


def stanford_reference(rows):
    """What the released grader requires from these rows: the first row holding the strictly latest time."""
    best = None
    for r in rows:
        if best is None or r[0] > best[0]:
            best = r
    return None if best is None or best[1] >= 35 else 10 * (35 - best[1])


RUNNER = r'''
import json, sys, importlib.util
spec = importlib.util.spec_from_file_location("cand", sys.argv[1]); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
for line in open(sys.argv[2]):
    t = json.loads(line)
    try:
        r = m.plan(t["observations"], t["now"])
        print(json.dumps({"order": r.get("order_replacement"), "dose": r.get("dose_mEq"), "repeat": r.get("repeat_potassium_at"), "cannot": r.get("cannot_apply")}, default=str))
    except Exception as e:
        print(json.dumps({"error": type(e).__name__}))
'''


def agree(out, exp):
    """Compare a program's whole answer with the proved program's outcome. Returns (ok, reason)."""
    if "error" in out:
        return False, "raised_an_error"
    kind = exp[0]
    if kind != "replace":
        if out["order"] is not False:
            return False, {"noResult": "ordered_with_no_counted_result", "notLow": "ordered_when_not_low", "conflict": "ordered_on_conflicting_results"}[kind]
        if out["dose"] is not None or out["repeat"] is not None:
            return False, "order_fields_filled_without_an_order"
        if kind == "notLow" and out["cannot"]:
            return False, "said_cannot_apply_on_a_normal_result"
        if kind == "conflict" and not out["cannot"]:
            return False, "conflicting_results_not_reported"
        return True, ""
    _, _, v, dose, rep = exp
    if out["order"] is not True:
        return False, "no_order_when_required"
    try:
        if isinstance(out["dose"], bool) or abs(float(out["dose"]) - dose) > 1e-6:
            return False, "dose"
    except (TypeError, ValueError):
        return False, "dose"
    try:
        d = datetime.fromisoformat(str(out["repeat"]))
        if d.tzinfo is None or int(d.timestamp()) != rep:
            return False, "repeat_time"
    except ValueError:
        return False, "repeat_time"
    return True, ""


class Bench:
    def __init__(self, S):
        self.S, self.tmp = S, tempfile.mkdtemp()
        self.expected = {n: expect(t) for n, t in S.items()}
        self.files = {}
        for name, tests in S.items():
            self.files[name] = os.path.join(self.tmp, name + ".jsonl")
            with open(self.files[name], "w") as f:
                for now, rows in tests:
                    f.write(json.dumps({"now": iso(now), "observations": fhir_rows(rows)}) + "\n")
        self.runner = os.path.join(self.tmp, "runner.py")
        open(self.runner, "w").write(RUNNER)

    def run(self, path, name):
        try:
            p = subprocess.run([sys.executable, "-I", self.runner, os.path.abspath(path), self.files[name]], capture_output=True, text=True, timeout=600, cwd=self.tmp)
            outs = [json.loads(l) for l in p.stdout.splitlines() if l.strip()]
        except subprocess.TimeoutExpired:
            outs = []
        return outs if len(outs) == len(self.S[name]) else None

    def close(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


def words(exp):
    if exp[0] == "replace":
        return json.dumps({"order_replacement": True, "dose_mEq": exp[3], "repeat_potassium_at": iso(exp[4]), "cannot_apply": None})
    if exp[0] == "conflict":
        return '{"order_replacement": false, "dose_mEq": null, "repeat_potassium_at": null, "cannot_apply": "<a short reason>"}'
    return '{"order_replacement": false, "dose_mEq": null, "repeat_potassium_at": null, "cannot_apply": null}'


def repair(a):
    """Counterexample feedback. The counterexamples are made-up charts, so no patient data is sent."""
    made_up = {"constructed": CONSTRUCTED, "small_charts": small_charts()}
    b = Bench(made_up)
    cost, log = 0.0, []
    for src in sorted(glob.glob(os.path.join(a.programs, "instruction_*.py")), reverse=a.reverse):
        seed = int(re.search(r"_(\d+)\.py$", src).group(1))
        dst = os.path.join(a.programs, f"repaired_{seed:02d}.py")
        if a.only and seed not in a.only:
            continue
        if os.path.exists(dst):
            continue
        code = "\n".join(l for l in open(src).read().split("\n") if not l.startswith("# Written by"))
        rounds, work = 0, os.path.join(b.tmp, "work.py")
        while True:
            open(work, "w").write(code)
            worst = None
            for name in made_up:
                outs = b.run(work, name)
                for i, e in enumerate(b.expected[name]):
                    o = outs[i] if outs else {"error": "did not run"}
                    if not agree(o, e)[0] and (worst is None or len(made_up[name][i][1]) < len(worst[0][1])):
                        worst = (made_up[name][i], o, e)
            if worst is None or rounds == a.rounds:
                break
            (now, rows), got, want = worst
            new, c = call(REPAIR.format(patient="{patient}", now=iso(now), code=code, obs=json.dumps(fhir_rows(rows)), got=json.dumps(got), want=words(want)), 1000 * rounds + seed)
            cost += c
            rounds += 1
            if new is None:
                break
            code = new
        open(dst, "w").write(f"# Written by {MODEL}: \"instruction\" seed {seed}, then {rounds} round(s) of counterexample feedback. Unedited.\n" + code)
        log.append((seed, rounds, worst is None))
        print(dst, "rounds", rounds, "agrees on made-up charts:", worst is None, flush=True)
    b.close()
    print("cost", round(cost, 5))


def check(a):
    S = suites(a.records)
    b = Bench(S)
    ref30 = [stanford_reference(rows) for _, rows in S["released_30"]]
    report = {"model": MODEL, "suites": {n: {"tests": len(t), "required": dict(collections.Counter(e[0] for e in b.expected[n]))} for n, t in S.items()}, "programs": []}
    for path in sorted(glob.glob(os.path.join(os.path.abspath(a.programs), "*.py"))):
        row = {"file": os.path.basename(path), "condition": os.path.basename(path).split("_")[0], "suites": {}}
        head = open(path).readline()
        m = re.search(r"then (\d+) round", head)
        if m:
            row["feedback_rounds"] = int(m.group(1))
        for name in S:
            outs = b.run(path, name)
            if outs is None:
                row["suites"][name] = {"ran": False}
                continue
            fails = collections.Counter(agree(o, e)[1] for o, e in zip(outs, b.expected[name]) if not agree(o, e)[0])
            row["suites"][name] = {"ran": True, "agree": len(outs) - sum(fails.values()), "of": len(outs), "disagreements": dict(fails)}
            # moments where the instruction is silent (two results at the latest time that differ) set apart
            row["suites"][name]["disagree_where_instruction_is_unambiguous"] = sum(
                1 for o, e in zip(outs, b.expected[name]) if e[0] != "conflict" and not agree(o, e)[0])
            if name == "released_30":
                def dose(o):
                    try:
                        return float(o["dose"]) if o.get("order") is True else None
                    except (TypeError, ValueError, KeyError):
                        return "?"
                same = lambda d, r: d == r if (d is None or r is None or d == "?") else abs(d - r) < 1e-6  # noqa: E731
                row["matches_stanford_reference_on_released_30"] = sum(same(dose(o), r) for o, r in zip(outs, ref30))
        row["agrees_everywhere"] = all(s.get("ran") and s["agree"] == s["of"] for s in row["suites"].values())
        report["programs"].append(row)
        print(row["file"], {n: (f'{s["agree"]}/{s["of"]}' if s.get("ran") else "did not run") for n, s in row["suites"].items()}, flush=True)
    for cond in sorted({r["condition"] for r in report["programs"]}):
        rs = [r for r in report["programs"] if r["condition"] == cond]
        summ = {"programs": len(rs), "agree_everywhere": sum(r["agrees_everywhere"] for r in rs),
                "match_stanford_reference_on_all_released_30": sum(r.get("matches_stanford_reference_on_released_30") == 30 for r in rs)}
        summ["right_at_every_unambiguous_report_moment"] = sum(
            1 for r in rs if r["suites"]["as_reported"].get("ran") and r["suites"]["as_reported"]["disagree_where_instruction_is_unambiguous"] == 0)
        summ["unambiguous_report_moments_wrong_per_program"] = sorted(
            r["suites"]["as_reported"]["disagree_where_instruction_is_unambiguous"] for r in rs if r["suites"]["as_reported"].get("ran"))
        for name in S:
            summ[name] = sum(1 for r in rs if r["suites"][name].get("ran") and r["suites"][name]["agree"] == r["suites"][name]["of"])
        reasons = collections.Counter()
        for r in rs:
            for why in {w for s in r["suites"].values() for w in (s.get("disagreements") or {})}:
                reasons[why] += 1
        summ["programs_with_each_disagreement"] = dict(reasons)
        if cond == "repaired":
            summ["feedback_rounds"] = dict(collections.Counter(r.get("feedback_rounds") for r in rs))
        report.setdefault("summary", {})[cond] = summ
        print(cond, summ)
    json.dump(report, open(a.out, "w"), indent=1)
    b.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate"); g.add_argument("--condition", required=True); g.add_argument("--n", type=int, default=20); g.add_argument("--out", required=True)
    r = sub.add_parser("repair"); r.add_argument("--programs", required=True); r.add_argument("--rounds", type=int, default=4); r.add_argument("--reverse", action="store_true"); r.add_argument("--only", type=lambda t: {int(x) for x in t.split(",")})
    c = sub.add_parser("check"); c.add_argument("--records", required=True); c.add_argument("--programs", required=True); c.add_argument("--out", required=True)
    a = p.parse_args()
    {"generate": generate, "repair": repair, "check": check}[a.cmd](a)
