"""Run MedAgentBench task 9 through the released text protocol on a hosted model, and grade each run two ways.

Protocol (as released, benchmark commit 99260117): the released prompt template, the nine-function text
catalog, the released task 9 instruction and context with only the patient identifier changed, at most 8
rounds, GET forwarded to the loopback FHIR server with `&_format=json` appended, POST parsed and
acknowledged with the released text but never sent, FINISH ends the run.

Grades, kept separate:
  stanford   Stanford's `task9`, executed verbatim against the loopback server (only `print` is silenced and
             `send_get_request` is bound to loopback). As in the released `calculate_overall`, a run with no
             FINISH result is not passed to the grader and counts as a fail.
  statement  Did the run place exactly the orders the proved statement requires (see `statement_grade`).

Full transcripts (identifiers, record text) go only to --out in the private folder.

Usage:
  python3 study/agent/run_task9.py --cases PRIVATE/agent/cases.json --set replace --limit 40 \
      --seed 42 --fhir http://127.0.0.1:18179/fhir/ --out PRIVATE/agent/runs/replace_pilot_s42.jsonl --cost-cap 0.20
"""
import argparse, ast, json, os, re, subprocess, sys, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener, HTTPRedirectHandler

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from balance import key as openrouter_key  # noqa: E402

sys.path.insert(0, os.path.join(HERE, ".."))
from local_paths import local  # noqa: E402

BENCH = local("medagentbench_repo") or "MEDAGENTBENCH_REPO-is-not-set"      # see study/local_paths.py
GRADER = local("medagentbench_grader") or "MEDAGENTBENCH_GRADER-is-not-set"
PIN = "99260117137b09f04837a8c18d18a1107efa55ae"
GRADER_SHA = "67d19da263ac92c1b7075b3218ace3a4bd19b206a06fc7aebcc897dc39625419"
MAX_ROUNDS = 8
MODEL = "deepseek/deepseek-v4.1-flash-1017"
ROUTE = {"only": ["wafer/us"], "data_collection": "deny", "zdr": True, "allow_fallbacks": False}
PROVIDER = "Wafer"
MAX_OUTPUT = 32000
REASONING = {"effort": "low"}
TIMEOUT = 180
API = "https://openrouter.ai/api/v1/chat/completions"
CLOCK = datetime.fromisoformat("2023-11-13T10:15:00+00:00")
LAB_AT = datetime.fromisoformat("2023-11-14T08:00:00+00:00")
NDC = "40032-917-01"
ACK = ("POST request accepted and executed successfully. Please call FINISH if you have got answers for all "
       "the questions and finished all the requested tasks")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


OPENER = build_opener(ProxyHandler({}), NoRedirect())


# ---------------------------------------------------------------- benchmark sources

def git_show(path):
    return subprocess.check_output(["git", "-C", BENCH, "show", f"{PIN}:{path}"])


def load_benchmark():
    src = git_show("src/server/tasks/medagentbench/__init__.py")
    prompt = next(ast.literal_eval(n.value) for n in ast.parse(src).body if isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == "MedAgentBench_prompt" for t in n.targets))
    funcs_raw = git_show("data/medagentbench/funcs_v1.json")
    data_raw = git_show("data/medagentbench/test_data_v2.json")
    task9 = [c for c in json.loads(data_raw) if c["id"].startswith("task9_")]
    assert len(task9) == 30 and len({c["context"] for c in task9}) == 1
    template = task9[0]
    instr = template["instruction"]
    assert instr.count(template["eval_MRN"]) == 1
    prov = {"benchmark_commit": PIN, "prompt_source_sha256": sha256(src).hexdigest(),
            "function_catalog_sha256": sha256(funcs_raw).hexdigest(), "case_source_sha256": sha256(data_raw).hexdigest(),
            "grader_sha256": GRADER_SHA}
    released = {c["eval_MRN"]: c for c in task9}
    return prompt, json.loads(funcs_raw), template, released, prov


def load_grader(fhir_get):
    src = open(GRADER, "rb").read()
    assert sha256(src).hexdigest() == GRADER_SHA
    tree = ast.parse(src)
    tree.body = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                 and n.name in {"task9", "extract_posts", "check_has_post"}]
    ns = {"json": json, "datetime": datetime, "timedelta": timedelta,
          "send_get_request": fhir_get, "print": lambda *a, **k: None}
    exec(compile(tree, GRADER, "exec"), ns)
    return ns["task9"], ns["extract_posts"]


# ---------------------------------------------------------------- loopback FHIR (released GET behaviour)

def make_fhir(base):
    host = urlsplit(base)

    def raw_get(url):
        u = urlsplit(url)
        if u.scheme != "http" or u.hostname not in ("127.0.0.1", "localhost") or u.port != host.port \
                or not u.path.startswith("/fhir"):
            return None, "URL is outside the local FHIR tool"
        target = f"http://127.0.0.1:{host.port}{u.path}" + (f"?{u.query}" if u.query else "")
        try:
            with OPENER.open(Request(target), timeout=60) as r:
                return (r.status, r.headers.get("Content-Type"), r.read().decode()), None
        except HTTPError as e:
            msg = f"{e.code} Client Error" if e.code < 500 else f"{e.code} Server Error"
            e.close()
            return None, f"{msg}: for url: {url}"
        except (URLError, OSError) as e:
            return None, str(e)

    def released_get(url):
        """utils.send_get_request: returns {'data': json-or-text} or {'error': str}."""
        res, err = raw_get(url)
        if err:
            return {"error": err}
        status, ctype, text = res
        return {"status_code": status, "data": json.loads(text) if ctype == "application/json" else text}

    def grader_get(url):
        res = released_get(url)
        if "data" not in res:
            raise RuntimeError("grader_transport_failed")
        return res

    return released_get, grader_get


# ---------------------------------------------------------------- model

class Router:
    def __init__(self, seed):
        self.headers = {"Authorization": "Bearer " + openrouter_key(), "Content-Type": "application/json"}
        self.seed = seed
        self.lock = threading.Lock()
        self.cost = 0.0
        self.halt = threading.Event()

    def completion(self, messages, meta):
        body = {"model": MODEL, "messages": messages, "stream": False, "provider": ROUTE, "transforms": [],
                "max_tokens": MAX_OUTPUT, "reasoning": REASONING, "temperature": 0, "seed": self.seed}
        req = Request(API, data=json.dumps(body).encode(), headers=self.headers)
        for attempt in range(1, 4):
            if self.halt.is_set():
                return None, "halted_cost_cap"
            try:
                with OPENER.open(req, timeout=TIMEOUT) as r:
                    reply = json.loads(r.read())
                break
            except HTTPError as e:
                code = e.code
                e.close()
                meta.setdefault("http_errors", []).append(code)
                if code in (429, 502, 503, 504) and attempt < 3:
                    time.sleep(2 ** attempt)
                    continue
                return None, f"provider_http_{code}"
            except (TimeoutError, URLError, OSError, ValueError) as e:
                meta.setdefault("transport_errors", []).append(type(e).__name__)
                if attempt < 3:
                    time.sleep(2 ** attempt)
                    continue
                return None, "provider_transport"
        usage = reply.get("usage") or {}
        meta["usage"] = {k: usage[k] for k in ("prompt_tokens", "completion_tokens", "total_tokens", "cost")
                         if isinstance(usage.get(k), (int, float))}
        details = usage.get("completion_tokens_details") or {}
        if isinstance(details.get("reasoning_tokens"), int):
            meta["usage"]["reasoning_tokens"] = details["reasoning_tokens"]
        with self.lock:
            self.cost += meta["usage"].get("cost", 0.0)
        meta["actual_model"], meta["actual_provider"] = reply.get("model"), reply.get("provider")
        if (reply.get("model") or "").split(":")[0] != MODEL.split(":")[0] and not (reply.get("model") or "").startswith(MODEL.split(":")[0]) or (PROVIDER and reply.get("provider") != PROVIDER):
            return None, "route_mismatch"
        ch = (reply.get("choices") or [{}])[0]
        meta["finish_reason"] = ch.get("finish_reason")
        content = (ch.get("message") or {}).get("content")
        if not isinstance(content, str):
            return None, "no_content"
        return content, None


# ---------------------------------------------------------------- statement grade

def _codes(concept):
    return [c.get("code") for c in (concept or {}).get("coding", []) if isinstance(c, dict)]


def _route_oral(route):
    if isinstance(route, str):
        return route.strip().lower() == "oral"
    if isinstance(route, dict) and isinstance(route.get("text"), str):
        return route["text"].strip().lower() == "oral"
    return False


def _instant(text):
    try:
        d = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (AttributeError, ValueError, TypeError):
        return None
    return d if d.tzinfo else None


def check_med(p, patient, dose):
    """Return list of failed checks for a MedicationRequest payload against the statement."""
    bad = []
    if p.get("resourceType") != "MedicationRequest":
        bad.append("resource_type")
    if NDC not in _codes(p.get("medicationCodeableConcept")):
        bad.append("ndc")
    if (p.get("subject") or {}).get("reference") != f"Patient/{patient}":
        bad.append("patient")
    try:
        di = p["dosageInstruction"][0]
        route_ok = _route_oral(di.get("route"))
        dq = di["doseAndRate"][0]["doseQuantity"]
        value, unit = dq.get("value"), dq.get("unit")
    except (KeyError, IndexError, TypeError):
        return bad + ["dosage_shape"]
    if not route_ok:
        bad.append("route")
    if not (isinstance(value, (int, float)) and not isinstance(value, bool) and value == dose):
        bad.append("dose")
    if not (isinstance(unit, str) and unit.strip().lower() == "meq"):
        bad.append("unit")
    return bad


def check_lab(p, patient):
    bad = []
    if p.get("resourceType") != "ServiceRequest":
        bad.append("resource_type")
    if "2823-3" not in _codes(p.get("code")):
        bad.append("loinc")
    if (p.get("subject") or {}).get("reference") != f"Patient/{patient}":
        bad.append("patient")
    when = _instant(p.get("occurrenceDateTime"))
    if when is None or when != LAB_AT:
        bad.append("lab_time")
    return bad


def statement_grade(kind, dose, patient, posts):
    """posts: list of (url, payload) for POSTs the broker accepted. kind: oracle outcome kind."""
    if kind in ("notLow", "noResult"):
        return {"meets": not posts, "failed": [] if not posts else ["unexpected_orders"]}
    if kind == "conflict":
        return {"meets": None, "failed": []}
    meds = [p for u, p in posts if isinstance(p, dict) and p.get("resourceType") == "MedicationRequest"]
    labs = [p for u, p in posts if isinstance(p, dict) and p.get("resourceType") == "ServiceRequest"]
    failed = []
    if len(posts) == 0:
        failed.append("no_orders")
    if len(meds) != 1 or len(labs) != 1 or len(posts) != 2:
        failed.append(f"order_count_med{len(meds)}_lab{len(labs)}_total{len(posts)}")
    if meds:
        failed += ["med_" + b for b in check_med(meds[0], patient, dose)]
    if labs:
        failed += ["lab_" + b for b in check_lab(labs[0], patient)]
    return {"meets": not failed, "failed": failed}


# ---------------------------------------------------------------- one run

def run_case(case, router, prompt, funcs, template, released, base, released_get, grader, extract_posts):
    patient = case["patient"]
    rc = released.get(patient)
    instruction = rc["instruction"] if rc else template["instruction"].replace(template["eval_MRN"], patient)
    first = prompt.format(api_base=base, functions=json.dumps(funcs), context=template["context"],
                          question=instruction)
    messages = [{"role": "user", "content": first}]
    history = [SimpleNamespace(role="user", content=first)]
    turns, status, result = [], None, None
    for n in range(1, MAX_ROUNDS + 1):
        meta = {"turn": n}
        turns.append(meta)
        content, fail = router.completion(messages, meta)
        if fail:
            status = "provider_failure:" + fail
            break
        messages.append({"role": "assistant", "content": content})
        history.append(SimpleNamespace(role="agent", content=content))
        meta["content"] = content
        r = content.strip().replace("```tool_code", "").replace("```", "").strip()
        if r.startswith("GET"):
            meta["action"] = "GET"
            url = r[3:].strip() + "&_format=json"
            meta["url"] = url
            g = released_get(url)
            reply = (f"Here is the response from the GET request:\n{g['data']}. Please call FINISH if you have got "
                     "answers for all the questions and finished all the requested tasks") if "data" in g else \
                f"Error in sending the GET request: {g['error']}"
            meta["get_ok"] = "data" in g
        elif r.startswith("POST"):
            meta["action"] = "POST"
            try:
                meta["payload"] = json.loads("\n".join(r.split("\n")[1:]))
                meta["post_url"] = r.split("\n")[0][4:].strip()
                reply = ACK
            except Exception:
                meta["post_invalid"] = True
                reply = "Invalid POST request"
        elif r.startswith("FINISH("):
            meta["action"] = "FINISH"
            status, result = "completed", r[len("FINISH("):-1]
            break
        else:
            meta["action"] = "INVALID"
            status = "invalid_action"
            break
        meta["reply"] = reply
        messages.append({"role": "user", "content": reply})
        history.append(SimpleNamespace(role="user", content=reply))
    else:
        status = "round_limit"

    run = SimpleNamespace(history=history, result=result)
    posts = extract_posts(run)
    accepted = [(t["post_url"], t["payload"]) for t in turns if t.get("action") == "POST" and "payload" in t]
    if status == "completed":
        try:
            stanford = grader({"id": "task9_" + case["label"], "eval_MRN": patient}, run, base) is True
        except Exception as e:  # grader raised outside its own try blocks
            stanford, case["grader_exception"] = False, type(e).__name__
    else:
        stanford = False
    kind = case["oracle"][0]
    st = statement_grade(kind, case.get("dose"), patient, accepted)
    return {"label": case["label"], "set": case["set"], "patient": patient, "kind": kind, "dose": case.get("dose"),
            "oracle": case["oracle"], "status": status, "result": result, "turns": turns,
            "grader_extract_posts": [[u, p] for u, p in posts], "accepted_posts": [[u, p] for u, p in accepted],
            "stanford_pass": stanford, "statement": st}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True)
    ap.add_argument("--set", required=True, choices=["control", "replace", "conflict", "notLow"])
    ap.add_argument("--limit", type=int)
    ap.add_argument("--skip", type=int, default=0)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--fhir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cost-cap", type=float, required=True, help="stop this batch when its reported cost reaches this")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    data = json.load(open(a.cases))
    cases = data["control"] if a.set == "control" else [c for c in data["cases"] if c["set"] == a.set]
    cases = sorted(cases, key=lambda c: c["label"])[a.skip:]
    if a.limit:
        cases = cases[: a.limit]
    done = set()
    if os.path.exists(a.out):
        done = {json.loads(l)["label"] for l in open(a.out) if l.strip()}
    cases = [c for c in cases if c["label"] not in done]
    prompt, funcs, template, released, prov = load_benchmark()
    released_get, grader_get = make_fhir(a.fhir)
    assert "data" in released_get(a.fhir + "metadata?x=1"), "FHIR server not answering"
    grader, extract_posts = load_grader(grader_get)
    router = Router(a.seed)
    print(f"{len(cases)} cases, seed {a.seed}, cap ${a.cost_cap}", flush=True)
    t0 = time.time()
    with open(a.out, "a") as out, ThreadPoolExecutor(a.workers) as pool:
        jobs = {pool.submit(run_case, c, router, prompt, funcs, template, released, a.fhir, released_get,
                            grader, extract_posts): c for c in cases}
        n = 0
        for j in as_completed(jobs):
            try:
                row = j.result()
            except Exception as e:
                c = jobs[j]
                row = {"label": c["label"], "set": c["set"], "status": "harness_error:" + type(e).__name__}
            row["seed"] = a.seed
            row["provenance"] = prov
            out.write(json.dumps(row) + "\n")
            out.flush()
            n += 1
            if n % 10 == 0 or n == len(cases):
                print(f"{n}/{len(cases)} cost ${router.cost:.4f} {time.time() - t0:.0f}s", flush=True)
            # stop when on track to exceed the cap
            if router.cost >= a.cost_cap or (n >= 10 and router.cost / n * len(cases) > a.cost_cap * 1.0 and
                                             router.cost + router.cost / n * 6 >= a.cost_cap):
                router.halt.set()
    print(json.dumps({"batch_cost": round(router.cost, 6), "runs": n}), flush=True)


if __name__ == "__main__":
    main()
