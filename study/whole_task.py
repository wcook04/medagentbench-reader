"""The whole of task 9 as one program: the model writes ONE Python function that does what the agent does
(it issues the GET searches itself and returns the POST payloads and the FINISH answers), and each function
is scored at every chart with the same scores as the agent runs.

Why. In `programs.py` the function receives the potassium results already retrieved and returns four
fields, so it never searches the record server or builds an order. Here it does both, with the agent's tools.

Conditions (20 programs each, the agent's model and provider, temperature 1.0, low reasoning effort):
  blind  one completion. The prompt holds the benchmark's function list as the agent receives it, the task 9
         instruction and context as the agent receives them with the patient given as the parameter `mrn`,
         and the function's interface. No server response is shown; paging, sorting, page size, the round
         limit and the scoring are not mentioned (the agent is told none of these either).
  seen   each blind program is run once on one made-up chart served with the released server's behaviour
         (30 results over about 12 days, record ids not in time order, the most recent result low and
         not on the first page of 20). The model is sent its function, every GET it issued with the full
         response text, and what the function returned or raised, without being told whether that was right,
         and asked once to revise the function.

Scoring. Every program is run at each of the 7,590 report moments (charts as they stood, served by the
stand-in) and at the 30 released cases (their full charts, served by the stand-in), with `get` answering
exactly as the agent harness does (`&_format=json` appended; the response body text, or the harness's error
text). For each case: `content` from analyse.py (the study's score), Stanford's grader as released on a
history built from the program's POSTs (each acknowledged as the harness acknowledges an agent's POST) and
answers, and the same grader with the closing result replaced by `[]`. Each case is scored with the
benchmark's limit of 8 rounds (each GET, each POST and the FINISH count one) and without it (GETs capped at 60).
Model-written code runs in a separate `python3 -I` process per block of cases, with a time limit per case.

Private inputs are read only; results/whole_task.json holds aggregate counts only.

  python3 study/whole_task.py generate --cost-cap 0.37
  python3 study/whole_task.py describe
  python3 study/whole_task.py check --cases PRIVATE/agent/cases2.json --resources PRIVATE/agent/k_resources.json
"""
import argparse, collections, contextlib, glob, hashlib, io, json, os, pprint, re, shutil, signal, statistics, subprocess, sys
import tempfile, threading, time, traceback, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "agent"))
sys.path.insert(0, HERE)

PROGRAMS = os.path.join(ROOT, "results", "whole_task_programs")
OUT = os.path.join(ROOT, "results", "whole_task.json")
MODEL = "deepseek/deepseek-v4.1-flash-1017"
PROVIDER_ROUTE = {"only": ["wafer/us"], "data_collection": "deny", "zdr": True, "allow_fallbacks": False}
PROVIDER = "Wafer"
TEMPERATURE = 1.0
REASONING = {"effort": "low"}
MAX_TOKENS = 32000
N_PROGRAMS = 20
CONCURRENCY = 4
FLOOR_USD = 0.05  # stop if the account itself runs this low (the other runs' reserve is theirs to spend)
MAX_GETS = 200  # without the round limit; the largest released chart (1,261 results) needs 64 pages of 20. Was 60 (programs generated with 60).
MAX_ROUNDS = 8
CASE_SECONDS = 60  # was 10
ROUTE_CHECK = "route is the plain string oral"
TRUNCATE = 20000
CLOCK = 1699870500  # 2023-11-13T10:15:00+00:00

INTERFACE = '''def run_task(get, api_base, mrn):
    """get(url) sends one GET request and returns the response body as text, exactly as the agent in the benchmark receives it.
    Return (posts, answers): posts is a list of (url, payload_dict) in the order they are to be sent; answers is the list passed to FINISH."""'''

BLIND = """Below is a task exactly as it is given to an assistant working in a hospital's FHIR record system. The assistant carries it out with the functions listed below: it sends GET requests to read the record, POST requests to place orders, and calls FINISH with its answers. Write one Python function that carries out the whole task for the patient whose identifier is `mrn`.

Here is a list of functions in JSON format that the assistant can invoke. Use the parameter `api_base` as the api_base.
{functions}

Context: {context}
Question: {question}

Write this function:

```python
{interface}
```

`get` is the only way to reach the server. Only standard-library modules are available. Reply with the complete function in one Python code block."""

SEEN_ASK = ("This is what the server returned to your function on one made-up patient. Revise the function if you think "
            "it needs it, and reply with the complete function.")
SEEN = """Your function:

```python
{code}
```

It was called as run_task(get, api_base={base!r}, mrn={mrn!r}).

{calls}

{outcome}

""" + SEEN_ASK

MADE_UP_MRN = "S9900001"


# ---------------------------------------------------------------- the benchmark text, as the agent receives it

def prompt_parts():
    import run_task9 as R
    prompt, funcs, template, released, prov = R.load_benchmark()
    functions = json.dumps(funcs)  # as run_task9 formats it into the agent's prompt
    question = template["instruction"].replace(template["eval_MRN"], "`mrn`")
    return functions, template["context"], question, prov


def blind_prompt():
    functions, context, question, _ = prompt_parts()
    return BLIND.format(functions=functions, context=context, question=question, interface=INTERFACE)


# ---------------------------------------------------------------- the made-up chart (no patient data)

def made_up_chart():
    """30 made-up potassium results over about 12 days. Record ids ascend in list order (as the released
    server returns them) but are not in time order. The most recent result is 3.1 and sits at position 25,
    so the first page of 20 does not hold it; the most recent result on the first page is 4.0."""
    start = CLOCK - 12 * 86400
    times = [start + int(i * 12 * 86400 / 30) + (i * 3571) % 7200 for i in range(30)]  # ascending, about every 9.6 h
    times[-1] = CLOCK - 3 * 3600  # the most recent: three hours before the task's clock
    values = [4.1, 3.9, 4.3, 4.0, 3.8, 4.4, 4.2, 3.7, 4.0, 4.5, 3.9, 4.1, 4.6, 3.8, 4.2, 4.0, 3.9, 4.3, 4.1, 3.7,
              4.4, 3.8, 4.2, 4.0, 3.6, 3.9, 4.1, 3.8, 4.0, 3.1]
    # list (id) position of each time-ordered result: a fixed scramble with the most recent at position 25
    # and the most recent of the first 20 positions holding 4.0
    order = [3, 17, 8, 22, 0, 13, 27, 5, 19, 10, 1, 24, 15, 7, 29, 11, 21, 2, 16, 28, 6, 12, 23, 9, 26, 4, 18, 14, 20, 25]
    pos = [None] * 30
    for k, p in enumerate(order):
        pos[p] = k
    rows = []
    for p in range(30):
        k = pos[p]
        t = times[k]
        rows.append({"resourceType": "Observation", "id": str(731400 + p * 7 + (p * 13) % 5),
                     "meta": {"versionId": "1", "lastUpdated": "2023-11-13T10:00:00.000+00:00", "source": "#madeUpChart0001"},
                     "status": "final",
                     "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category", "code": "laboratory", "display": "Laboratory"}]}],
                     "code": {"coding": [{"system": "http://loinc.org", "code": "K", "display": "K"}], "text": "K"},
                     "subject": {"reference": f"Patient/{MADE_UP_MRN}"},
                     "effectiveDateTime": datetime.fromtimestamp(t, timezone.utc).isoformat(),
                     "issued": datetime.fromtimestamp(t + 2700, timezone.utc).isoformat(),
                     "valueQuantity": {"value": values[k], "unit": "mmol/L", "system": "http://unitsofmeasure.org", "code": "mmol/L"}})
    patient = {"resourceType": "Patient", "id": MADE_UP_MRN, "meta": {"versionId": "1", "lastUpdated": "2023-11-13T10:00:00.000+00:00"},
               "identifier": [{"use": "usual", "system": "urn:oid:1.2.840.114350.1.13.0.1.7.5.737384.0", "value": MADE_UP_MRN}],
               "name": [{"use": "official", "family": "Example", "given": ["Madeup"]}], "gender": "female", "birthDate": "1961-04-02"}
    latest = max(rows, key=lambda r: r["effectiveDateTime"])
    assert latest["valueQuantity"]["value"] == 3.1 and rows.index(latest) >= 20
    assert max(rows[:20], key=lambda r: r["effectiveDateTime"])["valueQuantity"]["value"] >= 3.5
    assert [int(r["id"]) for r in rows] == sorted(int(r["id"]) for r in rows)
    assert [r["effectiveDateTime"] for r in rows] != sorted(r["effectiveDateTime"] for r in rows)
    return rows, patient


# ---------------------------------------------------------------- model calls (as programs.py, with cost and route checks)

class Model:
    def __init__(self, cap):
        from balance import key, balance
        key()  # load the key once, before any thread starts (the loader is not thread-safe)
        self.key, self.balance = key, balance
        self.cap, self.cost, self.retries, self.lock = cap, 0.0, 0, threading.Lock()
        self.stopped = None

    def ok_to_call(self):
        with self.lock:
            if self.stopped:
                return False
            if self.cost + 0.03 > self.cap:
                self.stopped = f"cost cap: {self.cost:.4f} spent of {self.cap}"
                return False
        try:
            rem = self.balance()["remaining"]
        except Exception:
            rem = None
        if rem is not None and rem < FLOOR_USD + 0.03:
            with self.lock:
                self.stopped = f"account balance {rem} too close to the reserve"
            return False
        return True

    def call(self, messages, seed):
        """Returns (content or None, meta). Transport and provider errors are retried (counted); a reply is never
        retried for its content."""
        body = {"model": MODEL, "messages": messages, "temperature": TEMPERATURE, "seed": seed, "max_tokens": MAX_TOKENS,
                "reasoning": REASONING, "provider": PROVIDER_ROUTE, "usage": {"include": True}, "stream": False}
        req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Authorization": "Bearer " + self.key(), "Content-Type": "application/json"})
        meta = {"seed": seed, "transport_retries": 0}
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=600) as r:
                    d = json.load(r)
                break
            except (HTTPError, URLError, TimeoutError, OSError, ValueError) as e:
                meta.setdefault("errors", []).append(getattr(e, "code", type(e).__name__))
                if attempt == 4:
                    meta["failed"] = "transport"
                    return None, meta
                with self.lock:
                    self.retries += 1
                meta["transport_retries"] += 1
                time.sleep(4 * (attempt + 1))
        usage = d.get("usage") or {}
        meta["cost"] = usage.get("cost", 0) or 0
        meta["tokens"] = {k: usage.get(k) for k in ("prompt_tokens", "completion_tokens")}
        meta["provider"], meta["model"] = d.get("provider"), d.get("model")
        with self.lock:
            self.cost += meta["cost"]
        if d.get("provider") != PROVIDER or not str(d.get("model", "")).startswith(MODEL.split("-1017")[0]):
            meta["route_mismatch"] = True
        ch = (d.get("choices") or [{}])[0]
        meta["finish_reason"] = ch.get("finish_reason")
        return (ch.get("message") or {}).get("content"), meta


def extract(text):
    """The first Python code block holding `def run_task`, else the first code block, else the whole reply."""
    text = text or ""
    blocks = re.findall(r"```(?:python|py)?[ \t]*\n(.*?)```", text, re.S)
    for b in blocks:
        if "def run_task" in b:
            return b
    return blocks[0] if blocks else text


def usable(code):
    try:
        compile(code, "<program>", "exec")
    except Exception:
        return False
    return bool(re.search(r"^def run_task\s*\(", code, re.M))


def save(name, header, code):
    path = os.path.join(PROGRAMS, name)
    with open(path, "w") as f:
        f.write(header + "\n" + code)
    return path


def body_of(path):
    return "\n".join(l for l in open(path).read().split("\n")[1:])


# ---------------------------------------------------------------- isolated execution (worker process)

WORKER = r'''
import json, os, sys
sys.path.insert(0, sys.argv[1])
import whole_task
whole_task.worker(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], int(sys.argv[6]), int(sys.argv[7]))
'''


class CaseTimeout(BaseException):
    pass


class GetCap(BaseException):
    pass


def _alarm(*_):
    raise CaseTimeout()


def load_program(path):
    import types
    mod = types.ModuleType("candidate")
    mod.__file__ = path
    code = compile(open(path).read(), path, "exec")
    exec(code, mod.__dict__)
    return getattr(mod, "run_task")


def run_one(fn, s, base, pid, program_path):
    """Call the program once on chart `pid`. Returns a dict with the calls it made and its outcome."""
    calls, state = [], {"n": 0}

    def get(url):
        if state["n"] >= MAX_GETS:
            raise GetCap()
        state["n"] += 1
        url = str(url).strip()
        try:
            r, flag = s.get(url + "&_format=json")
        except Exception as e:  # a search the stand-in could not parse; the agent harness would have crashed
            r, flag = {"error": f"400 Client Error: for url: {url}&_format=json"}, "standin_exception:" + type(e).__name__
        text = r["data"] if "data" in r else f"Error in sending the GET request: {r['error']}"
        calls.append({"url": url, "text": text, "ok": "data" in r, "flag": flag})
        return text

    out = {"calls": calls}
    stage = "call"
    sink = io.StringIO()
    signal.signal(signal.SIGALRM, _alarm)
    signal.alarm(CASE_SECONDS)
    try:
        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            ret = fn(get, base, pid)
        signal.alarm(0)
        stage = "return"
        posts, answers = ret
        posts = list(posts)
        clean = []
        for p in posts:
            u, payload = p
            clean.append((str(u), payload))
        out["posts"], out["answers"], out["status"] = clean, answers, "completed"
    except BaseException as e:  # noqa: BLE001 (model-written code may raise anything, including SystemExit)
        signal.alarm(0)
        kind = {CaseTimeout: "time_limit", GetCap: "get_cap"}.get(type(e), "malformed_return" if stage == "return" else "exception")
        out["status"], out["error"] = kind, type(e).__name__
        tb = [f for f in traceback.extract_tb(e.__traceback__) if f.filename == program_path]
        out["traceback"] = "Traceback (most recent call last):\n" + "".join(
            traceback.format_list(tb)).replace(program_path, "your_function.py") + "".join(traceback.format_exception_only(type(e), e))
    finally:
        signal.alarm(0)
    return out


def features(calls, mrn):
    f = {"codes": set(), "sort": False, "count": False, "count_over_20": False, "date": False, "next": False, "observation": False}
    for c in calls:
        u = urlsplit(c["url"])
        q = parse_qsl(u.query, keep_blank_values=True)
        names = {k for k, _ in q}
        if "_getpages" in names:
            f["next"] = True
            continue
        if u.path.rstrip("/").endswith("Observation"):
            f["observation"] = True
        for k, v in q:
            if k == "code":
                for x in v.split(","):
                    f["codes"].add("<patient id>" if mrn in x else x)
            if k == "_sort":
                f["sort"] = True
            if k == "_count":
                f["count"] = True
                try:
                    f["count_over_20"] |= int(v) > 20
                except ValueError:
                    pass
            if k == "date":
                f["date"] = True
    f["codes"] = sorted(f["codes"])
    return f


def decision_of(accepted):
    """(order or no order, dose): ("none", None) with no accepted POST; else ("order", dose of the first
    MedicationRequest's dosageInstruction[0].doseAndRate[0].doseQuantity.value, or None)."""
    posts = [p for _, p in accepted if isinstance(p, dict)]
    if not posts:
        return ["none", None]
    for p in posts:
        if p.get("resourceType") == "MedicationRequest":
            try:
                v = p["dosageInstruction"][0]["doseAndRate"][0]["doseQuantity"]["value"]
                return ["order", v if isinstance(v, (int, float)) and not isinstance(v, bool) else None]
            except (KeyError, IndexError, TypeError):
                return ["order", None]
    return ["order", None]


def same_decision(a, b):
    if a is None or b is None or a[0] != b[0]:
        return False
    if a[0] == "none":
        return True
    return a[1] is not None and b[1] is not None and abs(a[1] - b[1]) < 1e-6


def failure_reason(status, error, rounds, limit8, req, dec, checks):
    """One reason from a fixed list for a case that does not pass `relaxed` (under the given limit)."""
    if limit8 and rounds > MAX_ROUNDS:
        return "exceeded_8_rounds"
    if status == "unusable":
        return "unusable_program:" + str(error)
    if status in ("worker_died", "worker_hung"):
        return status
    if status == "exception":
        return "exception:" + str(error)
    if status == "get_cap":
        return "exceeded_get_cap"
    if status == "time_limit":
        return "exceeded_time_limit"
    if status == "malformed_return":
        return "malformed_output:" + str(error)
    if req[0] == "order":
        if dec[0] == "none":
            return "no_order_where_required"
        if dec[1] is None:
            return "order_without_a_medication_dose"
        if abs(dec[1] - req[1]) >= 1e-6:
            return "wrong_dose"
        rest = [c for c in checks if c != ROUTE_CHECK]
        return "right_dose_but:" + rest[0] if rest else "right_dose_but_rejected_by_grader_otherwise"
    if dec[0] != "none":
        return "order_where_none_required"
    return "no_order_but_rejected_by_grader"


def failed_row(status, error, why=None):
    return {"m": False, "m8": False, "sa": False, "sa8": False, "so": False, "so8": False, "sr": False, "sr8": False, "d": False, "d8": False,
            "why": why or (status + ":" + str(error)), "rounds": 0, "gets": 0, "posts": 0, "status": status, "error": error, "odd_payload": 0,
            "f": features([], ""), "flags": [], "dec": None, "checks": [],
            "reason": failure_reason(status, error, 0, False, ["none", None], None, []),
            "reason8": failure_reason(status, error, 0, True, ["none", None], None, [])}


def score_case(fn, s, base, pid, kind, dose, grader, program_path, extract_posts=None):
    import run_task9 as R
    from analyse import content, history
    from audit import stanford_checks
    r = run_one(fn, s, base, pid, program_path)
    turns = []
    for c in r["calls"]:
        reply = (f"Here is the response from the GET request:\n{c['text']}. Please call FINISH if you have got answers for all the "
                 "questions and finished all the requested tasks") if c["ok"] else c["text"]
        turns.append({"action": "GET", "content": "GET " + c["url"], "url": c["url"], "reply": reply})
    accepted, n_posts, odd_payload = [], 0, 0
    if r["status"] == "completed":
        for u, p in r["posts"]:
            n_posts += 1
            try:
                if isinstance(p, str):
                    p = json.loads(p)
                    odd_payload += 1
                p = json.loads(json.dumps(p))
                turns.append({"action": "POST", "content": "POST " + u + "\n" + json.dumps(p), "payload": p, "post_url": u, "reply": R.ACK})
                accepted.append((u, p))
            except Exception:
                turns.append({"action": "POST", "content": "POST " + u + "\n" + str(p), "post_invalid": True, "reply": "Invalid POST request"})
    rounds = len(r["calls"]) + n_posts + 1
    row = {"turns": turns, "patient": pid}
    if r["status"] == "completed":
        try:
            row["result"] = json.dumps(r["answers"])
        except Exception:
            row["result"] = str(r["answers"])
        ok, why = content(kind, dose, pid, accepted)

        def stanford(**kw):
            try:
                return grader({"id": "task9_x", "eval_MRN": pid}, history(row, **kw), base) is True
            except Exception:
                return False
        # relaxed: Stanford's unmodified grader, after the route object that means oral is rewritten to "oral"
        # (analyse.history plain_route, analyse.oral) and the closing answer replaced by "[]"
        sa, so, sr = stanford(), stanford(closing="[]"), stanford(closing="[]", plain_route=True)
        dec = decision_of(accepted)
        checks = []
        if kind == "replace" and extract_posts is not None:
            try:
                ext = extract_posts(history(row, closing="[]", plain_route=True))
                checks = stanford_checks({"grader_extract_posts": [[u, p] for u, p in ext], "patient": pid}, dose)
            except Exception as e:  # noqa: BLE001
                checks = ["grader_extract_posts raised " + type(e).__name__]
    else:
        ok, why, sa, so, sr = False, r["status"] + ":" + r["error"], False, False, False
        dec, checks = None, []
    within = rounds <= MAX_ROUNDS
    req = ["order", dose] if kind == "replace" else ["none", None]
    d = same_decision(dec, req)
    out = {"m": ok, "m8": ok and within, "sa": sa, "sa8": sa and within, "so": so, "so8": so and within, "sr": sr, "sr8": sr and within,
           "d": d, "d8": d and within, "dec": dec, "req": req, "checks": checks,
           "why": why or "correct", "rounds": rounds, "gets": len(r["calls"]), "posts": n_posts, "status": r["status"],
           "error": r.get("error"), "odd_payload": odd_payload, "f": features(r["calls"], pid),
           "flags": sorted({c["flag"].split(":")[0] for c in r["calls"] if c["flag"]})}
    out["reason"] = None if sr else failure_reason(r["status"], r.get("error"), rounds, False, req, dec, checks)
    out["reason8"] = None if (sr and within) else failure_reason(r["status"], r.get("error"), rounds, True, req, dec, checks)
    return out


def worker(program_path, cases_path, resources_path, out_path, lo, hi):
    """Runs inside `python3 -I`. Scores cases[lo:hi] of the work list and appends one line per case to out_path."""
    os.chdir(os.path.dirname(out_path))
    import run_task9 as R
    from standin import Standin, BENCH_BASE, REAL
    work = json.load(open(cases_path))
    res = json.load(open(resources_path))
    servers = {BENCH_BASE: Standin(BENCH_BASE), REAL: Standin(REAL)}
    current = {"s": None}

    def gget(url):
        g = current["s"].get(url)[0]
        if "data" not in g:
            raise RuntimeError("grader_transport_failed")
        return g
    grader, extract_posts = R.load_grader(gget)
    from audit import first_page_program
    from apply_rule import tenths
    out = open(out_path, "a")
    fn, load_err = None, None
    sink = io.StringIO()
    signal.signal(signal.SIGALRM, _alarm)
    signal.alarm(CASE_SECONDS)
    try:
        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            fn = load_program(program_path)
    except BaseException as e:  # noqa: BLE001
        load_err = type(e).__name__
    finally:
        signal.alarm(0)
    for i in range(lo, hi):
        c = work[i]
        if fn is None:
            row = failed_row("unusable", load_err, why="no_usable_function:" + load_err)
        else:
            base = c["base"]
            s = servers[base]
            current["s"] = s
            src = res[c["source"]]
            if c["set"] == "released":
                s.add_chart(c["patient"], src["K"], src["patient"])
            else:
                s.add_chart(c["patient"], src["K"], src["patient"], upto=c["moment"], shift=CLOCK - c["moment"], first_id=100000)
            chart = s.charts[c["patient"]]
            row = score_case(fn, s, base, c["patient"], c["kind"], c["dose"], grader, program_path, extract_posts)
            from standin import epoch
            fp = first_page_program([(epoch(t["effectiveDateTime"]), tenths(t["valueQuantity"]["value"])) for t in chart])
            row["fp"] = ["order", fp[1]] if fp[0] == "replace" else ["none", None]
            row["same_as_fp"] = same_decision(row["dec"], row["fp"])
            row["chart_size"] = len(chart)
            if chart:
                topt = max(epoch(t["effectiveDateTime"]) for t in chart)
                holds = any(epoch(t["effectiveDateTime"]) == topt for t in chart[:20])
                row["group"] = "20_or_fewer" if len(chart) <= 20 else ("over_20_latest_on_first_page" if holds else "over_20_latest_not_on_first_page")
            s.charts.pop(c["patient"], None)
            s.patients.pop(c["patient"], None)
            s.pages.clear()
        row["i"] = i
        row["set"] = c["set"]
        out.write(json.dumps(row) + "\n")
        out.flush()


def probe(program_path, work_dir):
    """Run one program on the made-up chart in an isolated process; returns what it saw and did."""
    script = os.path.join(work_dir, "probe_runner.py")
    open(script, "w").write(
        "import json, sys\nsys.path.insert(0, sys.argv[1])\nimport whole_task\n"
        "print(json.dumps(whole_task.probe_inside(sys.argv[2]), default=repr))\n")
    try:
        p = subprocess.run([sys.executable, "-I", script, HERE, os.path.abspath(program_path)], capture_output=True, text=True,
                           timeout=120, cwd=work_dir)
        return json.loads(p.stdout.strip().splitlines()[-1])
    except Exception as e:
        return {"calls": [], "status": "exception", "error": "probe_failed:" + type(e).__name__, "traceback": ""}


def probe_inside(program_path):
    sys.path.insert(0, os.path.join(HERE, "agent"))
    from standin import Standin, BENCH_BASE
    rows, patient = made_up_chart()
    s = Standin(BENCH_BASE)
    s.add_chart(MADE_UP_MRN, rows, patient)
    sink = io.StringIO()
    try:
        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            fn = load_program(program_path)
    except BaseException as e:  # noqa: BLE001
        tb = traceback.format_exception_only(type(e), e)
        return {"calls": [], "status": "exception", "error": type(e).__name__, "traceback": "".join(tb).replace(program_path, "your_function.py")}
    r = run_one(fn, s, BENCH_BASE, MADE_UP_MRN, program_path)
    if r["status"] == "completed":
        r["shown_return"] = pprint.pformat((r["posts"], r["answers"]), width=110, sort_dicts=False)
    return r


def seen_message(code, r):
    from standin import BENCH_BASE
    parts = []
    for n, c in enumerate(r["calls"], 1):
        text = c["text"]
        if len(text) > TRUNCATE:
            text = text[:TRUNCATE] + f"\n[response truncated here: {len(c['text']) - TRUNCATE} more characters]"
        parts.append(f"GET request {n}: get({c['url']!r})\nResponse text:\n{text}")
    calls = "\n\n".join(parts) if parts else "The function issued no GET request."
    if r["status"] == "completed":
        outcome = "The function returned (posts, answers):\n" + r["shown_return"]
    else:
        outcome = "The function raised an exception:\n" + (r.get("traceback") or r.get("error", ""))
    return SEEN.format(code=code.strip("\n"), base=BENCH_BASE, mrn=MADE_UP_MRN, calls=calls, outcome=outcome)


# ---------------------------------------------------------------- generate

def generate(a):
    os.makedirs(PROGRAMS, exist_ok=True)
    os.makedirs(a.work, exist_ok=True)
    model = Model(a.cost_cap)
    prompt = blind_prompt()
    log_path = os.path.join(a.work, "generation_log.json")
    log = json.load(open(log_path)) if os.path.exists(log_path) else {"blind": {}, "seen": {}}
    lock = threading.Lock()
    model.cost = sum(m.get("cost", 0) for c in ("blind", "seen") for m in log[c].values())  # the cap covers earlier invocations too
    spent_before = model.cost

    def keep():
        with lock:
            json.dump(log, open(log_path, "w"), indent=1)

    def blind(n):
        name = f"blind_{n:02d}.py"
        if os.path.exists(os.path.join(PROGRAMS, name)) and name in log["blind"]:
            return
        if not model.ok_to_call():
            return
        text, meta = model.call([{"role": "user", "content": prompt}], seed=n)
        if text is None and meta.get("failed"):
            meta["usable"] = False
            with lock:
                log["blind"][name] = meta
            keep()
            return
        code = extract(text)
        meta["usable"] = usable(code)
        meta["raw_reply"] = text
        save(name, f"# Written by {MODEL}, condition \"blind\", seed {n}, temperature {TEMPERATURE}. Unedited.", code)
        with lock:
            log["blind"][name] = meta
        keep()
        print(name, "usable" if meta["usable"] else "NOT USABLE", f"cost {model.cost:.4f}", flush=True)

    def seen(n):
        src, name = f"blind_{n:02d}.py", f"seen_{n:02d}.py"
        if src not in log["blind"] or "raw_reply" not in log["blind"][src]:
            return
        if os.path.exists(os.path.join(PROGRAMS, name)) and name in log["seen"]:
            return
        if not model.ok_to_call():
            return
        code = body_of(os.path.join(PROGRAMS, src))
        r = probe(os.path.join(PROGRAMS, src), a.work)
        follow = seen_message(code, r)
        messages = [{"role": "user", "content": prompt}, {"role": "assistant", "content": log["blind"][src]["raw_reply"]},
                    {"role": "user", "content": follow}]
        text, meta = model.call(messages, seed=1000 + n)
        meta["probe"] = {"status": r["status"], "error": r.get("error"), "gets": len(r["calls"]),
                         "urls": [c["url"] for c in r["calls"]], "follow_up_chars": len(follow)}
        if text is None and meta.get("failed"):
            meta["usable"] = False
            with lock:
                log["seen"][name] = meta
            keep()
            return
        code2 = extract(text)
        meta["usable"] = usable(code2)
        meta["raw_reply"] = text
        save(name, f"# Written by {MODEL}, condition \"seen\": {src} after one look at the server's responses on a made-up chart, "
                   f"seed {1000 + n}, temperature {TEMPERATURE}. Unedited.", code2)
        with lock:
            log["seen"][name] = meta
        keep()
        print(name, "usable" if meta["usable"] else "NOT USABLE", "probe", r["status"], len(r["calls"]), "GETs", f"cost {model.cost:.4f}", flush=True)

    ns = range(1, a.n + 1)
    with ThreadPoolExecutor(CONCURRENCY) as pool:
        list(pool.map(blind, ns))
    if a.condition != "blind":
        with ThreadPoolExecutor(CONCURRENCY) as pool:
            list(pool.map(seen, ns))
    log["cost_usd_this_invocation"] = round(model.cost - spent_before, 6)
    log["cost_usd_total"] = round(sum(m.get("cost", 0) for c in ("blind", "seen") for m in log[c].values()), 6)
    log["transport_retries_total"] = sum(m.get("transport_retries", 0) for c in ("blind", "seen") for m in log[c].values())
    log["stopped"] = model.stopped
    keep()
    print(json.dumps({"cost_this_invocation": round(model.cost - spent_before, 5), "cost_total": log["cost_usd_total"], "stopped": model.stopped,
                      "transport_retries": log["transport_retries_total"]}), flush=True)


# ---------------------------------------------------------------- check

def build_work(a, work_dir):
    import run_task9 as R
    from standin import BENCH_BASE, REAL, epoch
    from apply_rule import oracle, tenths
    res = json.load(open(a.resources))
    cases = json.load(open(a.cases))["cases"]
    work = [{"set": c["set"], "kind": c["kind"], "dose": c.get("dose"), "patient": c["patient"], "source": c["source"],
             "moment": c["moment"], "base": BENCH_BASE} for c in cases]
    mrns = [m for m in sorted(res) if res[m]["task9"]]
    outs = oracle([(CLOCK, [(epoch(r["effectiveDateTime"]), tenths(r["valueQuantity"]["value"]), r["status"] == "final") for r in res[m]["K"]]) for m in mrns])
    work += [{"set": "released", "kind": o[0], "dose": o[3] if o[0] == "replace" else None, "patient": m, "source": m, "moment": None, "base": REAL}
             for m, o in zip(mrns, outs)]
    path = os.path.join(work_dir, "work.json")
    json.dump(work, open(path, "w"))
    return path, work


def run_program(program, work_path, n, a, work_dir):
    """Score one program on every case, in blocks, restarting after a process that died or hung."""
    out_path = os.path.join(work_dir, os.path.basename(program) + ".jsonl")
    if os.path.exists(out_path):
        os.remove(out_path)
    runner = os.path.join(work_dir, "worker_runner.py")
    blocks = [(lo, min(n, lo + a.block)) for lo in range(0, n, a.block)]

    def lines():
        return {json.loads(l)["i"]: json.loads(l) for l in open(out_path)} if os.path.exists(out_path) else {}

    def run_block(lo, hi):
        part = out_path + f".{lo}"
        while lo < hi:
            try:
                subprocess.run([sys.executable, "-I", runner, HERE, os.path.abspath(program), work_path, a.resources, part, str(lo), str(hi)],
                               capture_output=True, text=True, timeout=max(1800, (hi - lo) * 5), cwd=work_dir)
                died = "worker_died"
            except subprocess.TimeoutExpired:
                died = "worker_hung"
            done = {json.loads(l)["i"] for l in open(part)} if os.path.exists(part) else set()
            nxt = next((i for i in range(lo, hi) if i not in done), None)
            if nxt is None:
                break
            with open(part, "a") as f:  # the case at which the process stopped counts as a failure
                f.write(json.dumps(dict(failed_row(died, died, why=died), i=nxt)) + "\n")
            lo = nxt + 1
        return part
    return out_path, blocks, run_block


def aggregate(rows, work):
    S = collections.Counter
    sets = ("replace", "notLow", "conflict", "released")
    r = {"matched": {}, "exceptions": 0, "exception_types": S(), "replace_content_failures": S(), "replace_content_failures_with_8_round_limit": S()}
    for st in sets:
        rs = [x for x in rows if work[x["i"]]["set"] == st]
        r["matched"][st] = {"of": len(rs), "no_limit": sum(x["m"] for x in rs), "limit_8_rounds": sum(x["m8"] for x in rs)}
        if st in ("replace", "released"):
            r.setdefault("stanford_as_released", {})[st] = {"of": len(rs), "no_limit": sum(x["sa"] for x in rs), "limit_8_rounds": sum(x["sa8"] for x in rs)}
            r.setdefault("stanford_orders_only", {})[st] = {"of": len(rs), "no_limit": sum(x["so"] for x in rs), "limit_8_rounds": sum(x["so8"] for x in rs)}
    all7590 = [x for x in rows if work[x["i"]]["set"] != "released"]
    r["matched"]["all_7590"] = {"of": len(all7590), "no_limit": sum(x["m"] for x in all7590), "limit_8_rounds": sum(x["m8"] for x in all7590)}
    for x in rows:
        if x["status"] not in ("completed",):
            r["exceptions"] += 1
            r["exception_types"][f'{x["status"]}:{x["error"]}'] += 1
        if work[x["i"]]["set"] == "replace":
            r["replace_content_failures"][x["why"]] += 0 if x["m"] else 1
            r["replace_content_failures_with_8_round_limit"][("over_8_rounds" if x["m"] and not x["m8"] else x["why"])] += 0 if x["m8"] else 1
    for k in ("exception_types", "replace_content_failures", "replace_content_failures_with_8_round_limit"):
        r[k] = {w: v for w, v in sorted(r[k].items(), key=lambda kv: -kv[1]) if v}
    ran = [x for x in rows if x["status"] != "unusable"]
    codes = S()
    for x in ran:
        for c in x["f"]["codes"]:
            codes[c] += 1
    gets = [x["gets"] for x in ran]
    r["searches"] = {
        "cases_run": len(ran),
        "cases_searching_each_code_value": dict(codes),
        "cases_with_sort": sum(x["f"]["sort"] for x in ran),
        "cases_with_count": sum(x["f"]["count"] for x in ran),
        "cases_with_count_over_20": sum(x["f"]["count_over_20"] for x in ran),
        "cases_with_date_filter": sum(x["f"]["date"] for x in ran),
        "cases_following_next_link": sum(x["f"]["next"] for x in ran),
        "cases_reading_only_the_first_page_of_20_unsorted": sum(1 for x in ran if x["gets"] and not (x["f"]["sort"] or x["f"]["count_over_20"] or x["f"]["next"])),
        "cases_over_8_rounds": sum(1 for x in ran if x["rounds"] > MAX_ROUNDS),
        "gets_per_case": {"min": min(gets), "median": statistics.median(gets), "max": max(gets)} if gets else None,
        "cases_with_searches_outside_the_stand_in": dict(S(f for x in ran for f in x["flags"])),
        "cases_returning_payloads_as_json_text": sum(1 for x in ran if x["odd_payload"]),
    }
    by = collections.defaultdict(lambda: [0, 0, 0])
    for x in rows:
        if work[x["i"]]["set"] == "replace" and "group" in x:
            by[x["group"]][0] += 1
            by[x["group"]][1] += x["m"]
            by[x["group"]][2] += x["m8"]
    r["_by_first_page"] = by
    aggregate_scores(r, rows, work)
    return r


SCORE_SETS = ("replace", "notLow", "conflict", "released")


def aggregate_scores(r, rows, work):
    """The added scores: relaxed (Stanford's grader after the route and answer rewrites), decision, the reasons
    for each relaxed failure, the caps hit, and the case-by-case comparison with the first-page baseline."""
    S = collections.Counter
    by_set = {st: [x for x in rows if work[x["i"]]["set"] == st] for st in SCORE_SETS}
    by_set["replace_and_notLow"] = by_set["replace"] + by_set["notLow"]
    by_set["all_7590"] = by_set["replace"] + by_set["notLow"] + by_set["conflict"]

    def tally(k, k8, sets):
        return {st: {"of": len(by_set[st]), "no_limit": sum(bool(x.get(k)) for x in by_set[st]), "limit_8_rounds": sum(bool(x.get(k8)) for x in by_set[st])} for st in sets}
    r["relaxed"] = tally("sr", "sr8", ("replace", "notLow", "released", "replace_and_notLow", "conflict"))
    r["relaxed"]["note"] = "conflict is computed for completeness only; there Stanford's grader and the specification disagree"
    r["decision"] = tally("d", "d8", ("replace", "notLow", "conflict", "released", "replace_and_notLow", "all_7590"))
    for st in ("notLow",):
        r["stanford_as_released"][st] = tally("sa", "sa8", (st,))[st]
        r["stanford_orders_only"][st] = tally("so", "so8", (st,))[st]

    def placed(x, lim8):
        return x.get("dec") is not None and x["dec"][0] != "none" and (not lim8 or x["rounds"] <= MAX_ROUNDS)
    r["unnecessary_orders"] = {st: {"of": len(by_set[st]), "no_limit": sum(placed(x, False) for x in by_set[st]), "limit_8_rounds": sum(placed(x, True) for x in by_set[st])}
                               for st in ("notLow", "conflict")}
    rel_none = [x for x in by_set["released"] if work[x["i"]]["kind"] != "replace"]
    r["unnecessary_orders"]["released_no_order_required"] = {"of": len(rel_none), "no_limit": sum(placed(x, False) for x in rel_none),
                                                             "limit_8_rounds": sum(placed(x, True) for x in rel_none)}
    r["relaxed_failure_reasons"] = {st: {"no_limit": dict(S(x["reason"] for x in by_set[st] if x.get("reason")).most_common()),
                                         "limit_8_rounds": dict(S(x["reason8"] for x in by_set[st] if x.get("reason8")).most_common())}
                                    for st in ("replace", "notLow", "released", "conflict")}
    r["caps_hit_without_round_limit"] = {"get_cap": sum(x["status"] == "get_cap" for x in rows), "time_limit": sum(x["status"] == "time_limit" for x in rows),
                                         "by_set": {st: {"get_cap": sum(x["status"] == "get_cap" for x in by_set[st]), "time_limit": sum(x["status"] == "time_limit" for x in by_set[st])}
                                                    for st in SCORE_SETS}}
    r["same_decision_as_first_page_baseline"] = {st: {"of": len(by_set[st]), "same": sum(bool(x.get("same_as_fp")) for x in by_set[st])}
                                                 for st in ("replace", "notLow", "conflict", "all_7590", "released")}
    r["first_page_baseline_decision"] = {st: {"of": len(by_set[st]), "matches_required": sum(same_decision(x.get("fp"), x.get("req") or (["order", work[x["i"]]["dose"]] if work[x["i"]]["kind"] == "replace" else ["none", None])) for x in by_set[st])}
                                         for st in ("replace", "notLow", "conflict", "all_7590", "released")}


def behaviour(p):
    s = p["searches"]
    n = s["cases_run"] or 1
    half = lambda k: s[k] * 2 >= n  # noqa: E731
    codes = sorted(c for c, v in s["cases_searching_each_code_value"].items() if v * 2 >= n)
    return {"codes": codes, "sort": half("cases_with_sort"), "count_over_20": half("cases_with_count_over_20"), "date": half("cases_with_date_filter"),
            "next": half("cases_following_next_link"), "first_page_only": half("cases_reading_only_the_first_page_of_20_unsorted")}


CONDITIONS = {"blind": ("blind_", "no_limit"), "blind_limit_8_rounds": ("blind_", "limit_8_rounds"),
              "seen_raised_caps": ("seen_", "no_limit"), "seen_limit_8_rounds": ("seen_", "limit_8_rounds")}


def primary_summary(programs):
    out = {"note": "blind programs make at most a few GETs, so blind and blind_limit_8_rounds should agree; seen_raised_caps is without the round limit, with the caps in scoring.caps_without_round_limit"}
    for cond, (prefix, lim) in CONDITIONS.items():
        ps = {k: v for k, v in programs.items() if k.startswith(prefix)}
        c = {"programs": len(ps)}
        for score, key in (("relaxed", "relaxed"), ("decision", "decision"), ("released", "stanford_as_released")):
            def n(v, st):
                if st == "replace_and_notLow" and score == "released":
                    return v[key]["replace"][lim] + v[key]["notLow"][lim]
                return v[key][st][lim]
            rep = sorted(n(v, "replace") for v in ps.values())
            c[score] = {"programs_all_629_replace": sum(n(v, "replace") == 629 for v in ps.values()),
                        "programs_all_6705_notLow": sum(n(v, "notLow") == 6705 for v in ps.values()),
                        "programs_all_30_released": sum(n(v, "released") == 30 for v in ps.values()),
                        "programs_all_7334_replace_and_notLow": sum(n(v, "replace_and_notLow") == 7334 for v in ps.values()),
                        "replace_median": statistics.median(rep) if rep else None, "replace_lowest": rep[0] if rep else None, "replace_highest": rep[-1] if rep else None,
                        "unnecessary_orders_at_notLow_total": sum(v["unnecessary_orders"]["notLow"][lim] for v in ps.values())}
        c["relaxed"]["per_program_replace"] = {k: v["relaxed"]["replace"][lim] for k, v in sorted(ps.items())}
        c["relaxed_failure_reasons_summed"] = {st: dict(sum((collections.Counter(v["relaxed_failure_reasons"][st][lim]) for v in ps.values()), collections.Counter()).most_common())
                                               for st in ("replace", "notLow", "released")}
        c["all_629_replace_but_some_notLow_failures"] = {k: v["relaxed_failure_reasons"]["notLow"][lim] for k, v in sorted(ps.items())
                                                         if v["relaxed"]["replace"][lim] == 629 and v["relaxed"]["notLow"][lim] < 6705}
        c["caps_hit"] = {"get_cap": sum(v["caps_hit_without_round_limit"]["get_cap"] for v in ps.values()),
                         "time_limit": sum(v["caps_hit_without_round_limit"]["time_limit"] for v in ps.values())} if lim == "no_limit" else None
        out[cond] = c
    return out


def released_failures(all_rows, work):
    """Per released case (numbered 1 to 30 in the order of the work list), how many programs fail and why,
    under `matched` (analyse.content, the old score) and `relaxed`, for each condition."""
    idx = [i for i, w in enumerate(work) if w["set"] == "released"]
    out = {}
    for cond, (prefix, lim) in CONDITIONS.items():
        mk, rk, rsn = ("m", "sr", "reason") if lim == "no_limit" else ("m8", "sr8", "reason8")
        progs = {k: v for k, v in all_rows.items() if k.startswith(prefix)}
        cases = []
        for n, i in enumerate(idx, 1):
            fm, fr = collections.Counter(), collections.Counter()
            for rows in progs.values():
                x = rows[i]
                if not x.get(mk):
                    fm[x.get(rsn) or "relaxed_passes"] += 1
                if not x.get(rk):
                    fr[x.get(rsn)] += 1
            if fm or fr:
                cases.append({"released_case": n, "kind": work[i]["kind"], "programs_failing_matched": sum(fm.values()), "matched_failure_reasons": dict(fm.most_common()),
                              "programs_failing_relaxed": sum(fr.values()), "relaxed_failure_reasons": dict(fr.most_common())})
        out[cond] = {"programs_all_30_matched": sum(all(rows[i].get(mk) for i in idx) for rows in progs.values()),
                     "programs_all_30_relaxed": sum(all(rows[i].get(rk) for i in idx) for rows in progs.values()), "cases_with_a_failure": cases}
    return out


def baseline_comparison(programs):
    ps = {k: v["same_decision_as_first_page_baseline"] for k, v in sorted(programs.items()) if k.startswith("blind_")}
    tot = {"all_7590": 7590, "replace": 629, "notLow": 6705, "conflict": 256, "released": 30}
    return {"note": "case by case: the program's (decision, dose) without the round limit equals audit.first_page_program's at that case",
            "blind_programs_identical": {st: sum(v[st]["same"] == v[st]["of"] for v in ps.values()) for st in tot},
            "per_blind_program": {k: {st: v[st]["same"] for st in tot} for k, v in ps.items()},
            "of": tot}


def check(a):
    work_dir = tempfile.mkdtemp(prefix="whole_task_check_", dir=a.work_root)
    try:
        open(os.path.join(work_dir, "worker_runner.py"), "w").write(WORKER)
        work_path, work = build_work(a, work_dir)
        programs = sorted(glob.glob(os.path.join(a.programs, "*.py")))
        if a.only:
            programs = [p for p in programs if os.path.basename(p) in a.only]
        jobs, owners = [], {}
        for prog in programs:
            out_path, blocks, run_block = run_program(prog, work_path, len(work), a, work_dir)
            owners[prog] = (out_path, [])
            for lo, hi in blocks:
                jobs.append((prog, run_block, lo, hi))
        t0 = time.time()
        with ThreadPoolExecutor(a.processes) as pool:
            futs = [(prog, pool.submit(rb, lo, hi)) for prog, rb, lo, hi in jobs]
            for k, (prog, f) in enumerate(futs, 1):
                owners[prog][1].append(f.result())
                if k % 20 == 0 or k == len(futs):
                    print(f"{k}/{len(futs)} blocks {time.time() - t0:.0f}s", flush=True)
        report = json.load(open(a.out)) if os.path.exists(a.out) else {}
        gen = json.load(open(os.path.join(a.work_root, "generation_log.json"))) if os.path.exists(os.path.join(a.work_root, "generation_log.json")) else None
        report["programs"] = {}
        by_cond = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0, 0]))
        all_rows = {}
        priv_dir = a.private_out or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(a.cases))), "whole_task")
        os.makedirs(priv_dir, exist_ok=True)
        per_case = open(os.path.join(priv_dir, "per_case.jsonl"), "w")  # private: derived from patient records
        keep_keys = ("i", "set", "m", "m8", "sa", "sa8", "so", "so8", "sr", "sr8", "d", "d8", "dec", "req", "fp", "same_as_fp", "checks", "why",
                     "reason", "reason8", "status", "error", "rounds", "gets", "posts", "chart_size", "group")
        for prog in programs:
            rows = []
            for part in owners[prog][1]:
                rows += [json.loads(l) for l in open(part)]
            rows = sorted({x["i"]: x for x in rows}.values(), key=lambda x: x["i"])
            assert len(rows) == len(work), (prog, len(rows))
            for x in rows:
                per_case.write(json.dumps(dict({k: x.get(k) for k in keep_keys}, program=os.path.basename(prog), kind=work[x["i"]]["kind"])) + "\n")
            all_rows[os.path.basename(prog)] = rows
            agg = aggregate(rows, work)
            for g, v in agg.pop("_by_first_page").items():
                for j in range(3):
                    by_cond[os.path.basename(prog).split("_")[0]][g][j] += v[j]
            name = os.path.basename(prog)
            agg["usable"] = usable(body_of(prog))
            agg["behaviour"] = behaviour(agg)
            report["programs"][name] = agg
            print(name, "replace", agg["matched"]["replace"], "released", agg["matched"]["released"], "exceptions", agg["exceptions"], flush=True)
        report["summary"] = {}
        for cond in ("blind", "seen"):
            ps = {k: v for k, v in report["programs"].items() if k.startswith(cond + "_")}
            if not ps:
                continue
            rep = sorted(v["matched"]["replace"]["no_limit"] for v in ps.values())
            rep8 = sorted(v["matched"]["replace"]["limit_8_rounds"] for v in ps.values())
            summ = {"programs": len(ps), "unusable_completions": sum(not v["usable"] for v in ps.values())}
            for lim, key in (("no_limit", "no_limit"), ("limit_8_rounds", "limit_8_rounds")):
                vals = sorted(v["matched"]["replace"][key] for v in ps.values())
                summ[lim] = {"replace_matched_min": vals[0], "replace_matched_median": statistics.median(vals), "replace_matched_max": vals[-1],
                             "programs_matching_all_629_replace": sum(v["matched"]["replace"][key] == v["matched"]["replace"]["of"] for v in ps.values()),
                             "programs_matching_all_7590": sum(v["matched"]["all_7590"][key] == v["matched"]["all_7590"]["of"] for v in ps.values()),
                             "programs_matching_all_30_released": sum(v["matched"]["released"][key] == v["matched"]["released"]["of"] for v in ps.values()),
                             "programs_stanford_as_released_on_all_629_replace": sum(v["stanford_as_released"]["replace"][key] == 629 for v in ps.values()),
                             "programs_stanford_orders_only_on_all_629_replace": sum(v["stanford_orders_only"]["replace"][key] == 629 for v in ps.values())}
            beh = [v["behaviour"] for v in ps.values()]
            summ["programs_by_search_behaviour"] = {
                "sorted_most_cases": sum(b["sort"] for b in beh), "count_over_20_most_cases": sum(b["count_over_20"] for b in beh),
                "date_filter_most_cases": sum(b["date"] for b in beh), "followed_next_link_most_cases": sum(b["next"] for b in beh),
                "read_only_first_unsorted_page_most_cases": sum(b["first_page_only"] for b in beh),
                "main_code_values": dict(collections.Counter(",".join(b["codes"]) or "(none)" for b in beh))}
            summ["replace_by_first_page_summed_over_programs"] = [
                {"chart": g, "runs": v[0], "matched_no_limit": v[1], "matched_limit_8_rounds": v[2]} for g, v in sorted(by_cond[cond].items())]
            if cond == "seen":
                changes = collections.Counter()
                per = {}
                for k, v in ps.items():
                    b0 = report["programs"].get(k.replace("seen_", "blind_"), {}).get("behaviour")
                    if b0 is None:
                        continue
                    diff = [f"{f}: {b0[f]} -> {v['behaviour'][f]}" for f in ("codes", "sort", "count_over_20", "date", "next", "first_page_only") if b0[f] != v["behaviour"][f]]
                    per[k] = diff
                    for d in diff:
                        changes[d] += 1
                summ["programs_whose_search_changed"] = sum(bool(d) for d in per.values())
                summ["search_changes"] = dict(changes)
                summ["search_changes_per_program"] = per
            report["summary"][cond] = summ
        per_case.close()
        report["primary_summary"] = primary_summary(report["programs"])
        report["released_case_failures"] = released_failures(all_rows, work)
        report["first_page_baseline_comparison"] = baseline_comparison(report["programs"])
        report["check_wall_seconds"] = round(time.time() - t0)
        if gen:
            report.setdefault("generation", {})
            report["generation"]["unusable_completions"] = {c: sum(not m.get("usable") for m in gen[c].values()) for c in ("blind", "seen")}
            report["generation"]["transport_retries"] = gen.get("transport_retries_total")
            report["generation"]["cost_usd"] = gen.get("cost_usd_total")
        report["scoring"] = {"cases": dict(collections.Counter(w["set"] for w in work)), "max_rounds": MAX_ROUNDS, "get_cap_without_limit": MAX_GETS,
                             "seconds_per_case": CASE_SECONDS,
                             "content": "study/agent/analyse.py content(kind, dose, patient, posts)",
                             "stanford": "Stanford's task 9 grader as released (run_task9.load_grader) on a history of the program's GETs and POSTs, each POST acknowledged with the harness's text, closing result = json.dumps(answers); orders_only replaces the closing result with []",
                             "records": "stand-in (study/agent/standin.py), released behaviour, newest_first=False; released 30 with their full charts",
                             "caps_without_round_limit": {"gets_per_case": MAX_GETS, "seconds_per_case": CASE_SECONDS,
                                                          "previous": {"gets_per_case": 60, "seconds_per_case": 10},
                                                          "why": "the largest released chart has 1,261 potassium results, 64 pages of 20"},
                             "released_kinds": dict(collections.Counter(w["kind"] for w in work if w["set"] == "released")),
                             "relaxed": "primary score. Stanford's unmodified task 9 grader on the program's history after two input rewrites: a medication route that analyse.oral reads as oral is written as the plain string \"oral\" (analyse.history plain_route=True), and the closing answer is replaced by \"[]\". Reported for replace, notLow and the released 30; conflict computed but not reported, as there the grader and the specification disagree",
                             "decision": "order or no order, and the dose of the first MedicationRequest (dosageInstruction[0].doseAndRate[0].doseQuantity.value) if any order, against the specification's outcome; every other field ignored; for conflict the required decision is no order",
                             "failure_reasons": "one per (program, case, limit) that does not pass relaxed, first that applies: exceeded_8_rounds (8-round limit only), unusable_program, worker_died/worker_hung, exception:<type>, exceeded_get_cap, exceeded_time_limit, malformed_output:<type> (the return value could not be read as (posts, answers)), no_order_where_required, order_without_a_medication_dose, wrong_dose, right_dose_but:<first failing check in audit.stanford_checks other than the route check>, right_dose_but_rejected_by_grader_otherwise, order_where_none_required, no_order_but_rejected_by_grader",
                             "first_page_baseline": "audit.first_page_program on the chart in served order; compared case by case with the program's decision (no round limit); a program that did not complete never matches",
                             "per_case_results": "private, outside the repository"}
        json.dump(report, open(a.out, "w"), indent=1)
    finally:
        if not a.keep:
            shutil.rmtree(work_dir, ignore_errors=True)


def describe(a):
    """Write the prompt texts, model settings, generation counts and the made-up chart into results/whole_task.json."""
    functions, context, question, prov = prompt_parts()
    rows, patient = made_up_chart()
    gen = json.load(open(os.path.join(a.work_root, "generation_log.json")))
    blind = BLIND.format(functions="<the benchmark's function list, json.dumps(funcs) as in run_task9.py: " + str(len(functions)) + " characters, sha256 "
                         + hashlib.sha256(functions.encode()).hexdigest() + ">", context=context, question=question, interface=INTERFACE)
    report = json.load(open(OUT)) if os.path.exists(OUT) else {}
    report.update({
        "model": MODEL, "provider": PROVIDER, "provider_route": PROVIDER_ROUTE, "temperature": TEMPERATURE, "reasoning_effort": REASONING["effort"],
        "max_tokens": MAX_TOKENS, "benchmark": prov,
        "prompts": {"blind": blind,
                    "seen": {"messages": "[user: the blind prompt, assistant: the blind reply, user: the follow-up below]",
                             "follow_up_template": SEEN, "ask": SEEN_ASK,
                             "calls_format": "GET request {n}: get({url!r})\\nResponse text:\\n{text, truncated at 20,000 characters}",
                             "outcome_format": "The function returned (posts, answers):\\n{pprint of the return} | The function raised an exception:\\n{traceback restricted to the function's own lines}"}},
        "made_up_chart": {"mrn": MADE_UP_MRN, "results_in_record_id_order": [
            {"id": r["id"], "effectiveDateTime": r["effectiveDateTime"], "value_mmol_per_L": r["valueQuantity"]["value"], "status": r["status"]} for r in rows],
            "patient": patient, "served_by": "study/agent/standin.py, released behaviour (20 per page, ascending record id, a next link)"},
        "generation": {"cost_usd": gen.get("cost_usd_total"), "transport_retries": gen.get("transport_retries_total"),
                       "unusable_completions": {c: sum(not m.get("usable") for m in gen[c].values()) for c in ("blind", "seen")},
                       "completions": {c: len(gen[c]) for c in ("blind", "seen")}, "stopped_early": gen.get("stopped"),
                       "route_mismatches": sum(1 for c in ("blind", "seen") for m in gen[c].values() if m.get("route_mismatch")),
                       "finish_reasons": dict(collections.Counter(m.get("finish_reason") for c in ("blind", "seen") for m in gen[c].values())),
                       "seen_probe_on_made_up_chart": {k: {"status": m["probe"]["status"], "error": m["probe"]["error"], "gets": m["probe"]["gets"],
                                                           "urls": m["probe"]["urls"]} for k, m in sorted(gen["seen"].items())}},
    })
    json.dump(report, open(OUT, "w"), indent=1)
    print("prompts and generation written", flush=True)


if __name__ == "__main__":
    default_work = os.path.join(tempfile.gettempdir(), "whole_task_work")
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--n", type=int, default=N_PROGRAMS)
    g.add_argument("--condition", default="both", choices=["blind", "both"])
    g.add_argument("--cost-cap", type=float, default=0.37, help="this experiment's own spend; 0.37 = balance at start (1.38) less the 1.0 reserved for other runs")
    g.add_argument("--work", default=default_work, help="holds the raw replies between the blind and seen steps (model output only)")
    d = sub.add_parser("describe")
    d.add_argument("--work-root", default=default_work)
    c = sub.add_parser("check")
    c.add_argument("--cases", required=True)
    c.add_argument("--resources", required=True)
    c.add_argument("--processes", type=int, default=6)
    c.add_argument("--block", type=int, default=1000)
    c.add_argument("--only", nargs="*")
    c.add_argument("--work-root", default=default_work)
    c.add_argument("--keep", action="store_true")
    c.add_argument("--programs", default=PROGRAMS)
    c.add_argument("--out", default=OUT)
    c.add_argument("--private-out", default=None, help="directory for the private per-case file (default: <cases dir>/../whole_task)")
    a = p.parse_args()
    if a.cmd == "check":
        os.makedirs(a.work_root, exist_ok=True)
    {"generate": generate, "describe": describe, "check": check}[a.cmd](a)
