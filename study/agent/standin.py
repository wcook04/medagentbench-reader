"""Potassium charts "as they stood", served from memory through the record server's search interface.

Why this exists. The benchmark poses its potassium task at one clock time, where 1 of the 30 released
cases has a low result. The same records hold hundreds of earlier moments at which a potassium result
was reported. For each such moment this module rebuilds the chart as it then stood (results reported
by that moment), moves every time by one constant so that the moment falls on the benchmark's clock,
and answers the agent's searches over that chart. The benchmark's instruction, context and grader
then apply unchanged.

This is NOT Stanford's server software. It answers the potassium Observation search (patient, code,
date, _count, _sort, paging) and the Patient lookup in the form the released server uses, and
`conformance` below compares it with the released server on real patients. A run whose search falls
outside what is implemented is flagged and reported separately.

Private inputs and outputs only; nothing here is written into the repository.

  python3 study/agent/standin.py fetch --records PRIVATE/records.json --out PRIVATE/agent/k_resources.json
  python3 study/agent/standin.py conformance --resources PRIVATE/agent/k_resources.json
  python3 study/agent/standin.py cases --resources PRIVATE/agent/k_resources.json --out PRIVATE/agent/cases2.json
"""
import argparse, collections, copy, json, os, random, re, sys, threading, urllib.request, uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from apply_rule import oracle, tenths  # noqa: E402

REAL = "http://127.0.0.1:18179/fhir/"
BENCH_BASE = "http://localhost:8080/fhir/"  # the address the released prompt gives the agent
CLOCK = 1699870500  # 2023-11-13T10:15:00+00:00
OBS_PARAMS = {"patient", "subject", "code", "date", "category", "status", "_count", "_sort", "_format", "_pretty", "_total"}
PAT_PARAMS = {"identifier", "_id", "_format", "_pretty", "_count"}


def epoch(s):
    return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).isoformat()


def pretty(obj):
    """Close to the released server's pretty-printed JSON (arrays of objects open as `[ {`)."""
    s = json.dumps(obj, indent=2, ensure_ascii=False)
    s = re.sub(r"\[\n\s*\{", "[ {", s)
    s = re.sub(r"\},\n\s*\{", "}, {", s)
    return re.sub(r"\}\n\s*\]", "} ]", s)


def date_range(text):
    """A FHIR date or dateTime of any precision as [lo, hi) in epoch seconds (UTC where no offset)."""
    m = re.fullmatch(r"(\d{4})(?:-(\d{2})(?:-(\d{2})(?:T(\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?(Z|[+-]\d{2}:\d{2})?)?)?)?", text)
    if not m:
        raise ValueError(text)
    y, mo, d, h, mi, s, tz = m.groups()
    if d is None:
        raise KeyError("month_or_year_precision")  # the released server's bounds for these were not reproduced
    if h is not None:
        dt = datetime.fromisoformat(f"{y}-{mo}-{d}T{h}:{mi}:{s or '00'}{'+00:00' if tz in (None, 'Z') else tz}")
        lo = int(dt.timestamp())
        return lo, lo + (1 if s else 60)
    lo = datetime(int(y), int(mo or 1), int(d or 1), tzinfo=timezone.utc)
    if d:
        hi = lo + timedelta(days=1)
    elif mo:
        hi = datetime(int(y) + (int(mo) == 12), int(mo) % 12 + 1, 1, tzinfo=timezone.utc)
    else:
        hi = datetime(int(y) + 1, 1, 1, tzinfo=timezone.utc)
    return int(lo.timestamp()), int(hi.timestamp())


class Standin:
    def __init__(self, base=BENCH_BASE, newest_first=False):
        self.base = base
        self.newest_first = newest_first  # experiment: a search with no _sort returns the newest results first
        u = urlsplit(base)
        self.origin, self.netloc = f"{u.scheme}://{u.netloc}", u.netloc
        self.charts, self.patients, self.pages = {}, {}, {}
        self.lock = threading.Lock()

    def add_chart(self, pid, resources, patient_resource=None, upto=None, shift=0, first_id=None):
        """Load a chart under patient id `pid`. `upto`: keep results reported at or before this moment.
        `shift`: seconds added to every clinical time. Resources stay in the server's own order."""
        rows = []
        for i, r in enumerate(resources):
            if upto is not None and epoch(r["issued"]) > upto:
                continue
            r = copy.deepcopy(r)
            if shift:
                r["effectiveDateTime"] = iso(epoch(r["effectiveDateTime"]) + shift)
                r["issued"] = iso(epoch(r["issued"]) + shift)
            if first_id is not None:
                r["id"] = str(first_id + i)
            r["subject"] = {"reference": f"Patient/{pid}", "identifier": {"system": "http://terminology.hl7.org/CodeSystem/v2-0203", "value": pid}}
            rows.append(r)
        self.charts[pid] = rows
        if patient_resource is not None:
            p = copy.deepcopy(patient_resource)
            p["id"] = pid
            for ident in p.get("identifier", []):
                ident["value"] = pid
            self.patients[pid] = p

    # ---- bundles
    def _bundle(self, rtype, rows, count, self_url, offset=0, token=None):
        page = rows[offset: offset + count]
        links = [{"relation": "self", "url": self_url}]
        more = offset + count < len(rows)
        if more or offset:
            if token is None:
                token = str(uuid.uuid4())
                with self.lock:
                    self.pages[token] = (rtype, rows)
            tail = f"&_count={count}&_format=json&_pretty=true&_bundletype=searchset"
            if more:
                links.append({"relation": "next", "url": f"{self.origin}/fhir?_getpages={token}&_getpagesoffset={offset + count}{tail}"})
            if offset:
                links.append({"relation": "previous", "url": f"{self.origin}/fhir?_getpages={token}&_getpagesoffset={max(0, offset - count)}{tail}"})
        b = {"resourceType": "Bundle", "id": str(uuid.uuid4()), "meta": {"lastUpdated": datetime.now(timezone.utc).isoformat(timespec="milliseconds")}, "type": "searchset"}
        if len(rows) <= max(count, 13):  # observed on the released server: a total appears when the search finishes in its first fetch
            b["total"] = len(rows)
        b["link"] = links
        if page:
            b["entry"] = [{"fullUrl": f"{self.base}{rtype}/{r['id']}", "resource": r, "search": {"mode": "match"}} for r in page]
        return b

    def get(self, url):
        """Returns (released-style result, flag). flag is None when the search is one this module implements."""
        u = urlsplit(url)
        if u.scheme != "http" or u.netloc != self.netloc or not u.path.startswith("/fhir"):
            return {"error": "URL is outside the local FHIR tool"}, "outside_url"
        path = u.path[len("/fhir"):].strip("/")
        q = parse_qsl(u.query, keep_blank_values=True)
        names = {k for k, _ in q}
        first = lambda k, d=None: next((v for kk, v in q if kk == k), d)  # noqa: E731
        bad = lambda code, flag: ({"error": f"{code} Client Error: for url: {url}"}, flag)  # noqa: E731
        ok = lambda b: {"status_code": 200, "data": pretty(b)}  # noqa: E731
        self_url = f"{self.base}{path}?" + "&".join(f"{k}={v}" for k, v in sorted(q))
        try:
            if path == "" and "_getpages" in names:
                rtype, rows = self.pages[first("_getpages")]
                return ok(self._bundle(rtype, rows, int(first("_count", "20")), url, int(first("_getpagesoffset", "0")), first("_getpages"))), None
            if path == "Observation":
                if names - OBS_PARAMS:
                    return bad(400, "unsupported_param:" + ",".join(sorted(names - OBS_PARAMS)))
                pid = (first("patient") or first("subject") or "").split("/")[-1]
                if not pid:
                    return bad(400, "no_patient")
                flag = None
                rows = list(self.charts.get(pid, []))
                if "code" in names:
                    codes = {c.split("|")[-1] for c in first("code").split(",")}
                    if "K" not in codes:
                        rows = []
                else:
                    flag = "no_code"  # the real chart would also return every other observation
                if "category" in names and first("category").split("|")[-1] != "laboratory":
                    rows = []
                if "status" in names:
                    rows = [r for r in rows if r["status"] in first("status").split(",")]
                for k, v in q:
                    if k != "date":
                        continue
                    m = re.match(r"(eq|ne|ge|gt|le|lt|sa|eb)?(.+)", v)
                    op, (lo, hi) = m.group(1) or "eq", date_range(m.group(2))
                    keep = {"eq": lambda t: lo <= t < hi, "ne": lambda t: not lo <= t < hi, "ge": lambda t: t >= lo, "gt": lambda t: t >= hi,
                            "sa": lambda t: t >= hi, "le": lambda t: t < hi, "lt": lambda t: t < lo, "eb": lambda t: t < lo}[op]
                    rows = [r for r in rows if keep(epoch(r["effectiveDateTime"]))]
                count = int(first("_count", "20"))
                if self.newest_first and not first("_sort"):
                    rows.sort(key=lambda r: epoch(r["effectiveDateTime"]), reverse=True)
                if first("_sort") and len(rows) > count:
                    rows.reverse()  # observed: when a sorted search is paged, results with identical times come back in descending id order
                for key in reversed([s for s in first("_sort", "").split(",") if s]):
                    name = key.lstrip("-")
                    if name == "date":
                        rows.sort(key=lambda r: epoch(r["effectiveDateTime"]), reverse=key.startswith("-"))
                    elif name == "_id":
                        rows.sort(key=lambda r: int(r["id"]), reverse=key.startswith("-"))
                    else:
                        return bad(400, "unsupported_sort:" + name)
                return ok(self._bundle("Observation", rows, count, self_url)), flag
            if path == "Patient":
                if names - PAT_PARAMS:
                    return bad(400, "unsupported_param:" + ",".join(sorted(names - PAT_PARAMS)))
                pid = (first("identifier") or first("_id") or "").split("|")[-1]
                rows = [self.patients[pid]] if pid in self.patients else []
                return ok(self._bundle("Patient", rows, 20, self_url)), None
            if path in ("MedicationRequest", "ServiceRequest", "Condition", "Procedure", "Encounter"):
                return ok(self._bundle(path, [], 20, self_url)), "other_resource:" + path
            return bad(404, "unsupported_path:" + path[:40])
        except (ValueError, KeyError) as e:
            return bad(400, "unparsed:" + type(e).__name__)


# ---------------------------------------------------------------- private data

def _get(url):
    with urllib.request.urlopen(url, timeout=120) as r:
        return json.load(r)


def fetch(a):
    pats = json.load(open(a.records))["patients"]
    out = {}
    for pt in pats:
        mrn, rows = pt["mrn"], []
        url = REAL + f"Observation?patient={mrn}&code=K&_count=5000&_format=json"
        while url:
            b = _get(url)
            rows += [e["resource"] for e in b.get("entry", [])]
            url = next((l["url"] for l in b.get("link", []) if l["relation"] == "next"), None)
        prs = _get(REAL + f"Patient?identifier={mrn}&_format=json").get("entry", [])
        out[mrn] = {"task9": pt["task9"], "K": rows, "patient": prs[0]["resource"] if prs else None}
        assert len(rows) == len(pt["K"]), (len(rows), len(pt["K"]))
    json.dump(out, open(a.out, "w"))
    print(len(out), "patients", sum(len(v["K"]) for v in out.values()), "potassium resources")


def conformance(a):
    """Same searches against the released server and this module, on real patients. Compares what the
    agent can act on: success or error, the order of the returned results, total, and link relations."""
    res = json.load(open(a.resources))
    rng = random.Random(3)
    mrns = rng.sample(sorted(res), a.patients)
    s = Standin(REAL)
    for m in mrns:
        s.add_chart(m, res[m]["K"], res[m]["patient"])
    queries = ["Observation?code=K&patient={m}", "Observation?patient={m}&code=K&_count=5000", "Observation?code=K&patient={m}&_sort=-date&_count=1",
               "Observation?code=K&patient={m}&_sort=date&_count=50", "Observation?code=K&patient={m}&_sort=-date", "Observation?code=K&patient={m}&date=ge2023-11-01",
               "Observation?code=K&patient={m}&date=gt2023-11-10T00:00:00%2B00:00&date=le2023-11-13", "Observation?code=K&patient={m}&date=gt2023-11-11",
               "Observation?code=K&patient={m}&date=lt2023-11-11", "Observation?code=K&patient={m}&date=le2023-11-11T12:00:00Z&_sort=-date&_count=3",
               "Observation?code=K&patient={m}&date=2023-11-12", "Observation?code=K&patient={m}&date=ge2023-10-01&_count=200",
               "Observation?code=http://loinc.org|K&patient={m}", "Observation?category=laboratory&code=K&patient={m}&_count=100",
               "Observation?code=2823-3&patient={m}", "Observation?code=K&patient=Patient/{m}", "Observation?code=K&subject={m}",
               "Observation?code=K&patient={m}&_sort=-effectiveDateTime", "Observation?code=K&patient={m}&status=final&_count=40",
               "Observation?code=K&patient={m}&bogus=1", "Patient?identifier={m}", "Observation?code=K&patient={m}&_sort=-date&_count=5#next"]

    def shape(get):
        def f(url):
            follow = url.endswith("#next")
            url = url.replace("#next", "")
            try:
                b = get(url + "&_format=json")
                if follow:
                    b = get(next(l["url"] for l in b["link"] if l["relation"] == "next"))
            except Exception as e:
                return ("error", str(getattr(e, "code", type(e).__name__)))
            ids = [e["resource"]["id"] for e in b.get("entry", [])]
            times = [e["resource"].get("effectiveDateTime") for e in b.get("entry", [])]
            groups = [tuple(sorted(i for i, t2 in zip(ids, times) if t2 == t)) for t in dict.fromkeys(times)]  # order within identical times ignored
            return ("ok", groups if "_sort" in url else ids, b.get("total"), sorted(l["relation"] for l in b["link"]), ids, sorted(t for t in times if t))
        return f

    def mine(url):
        r, _ = s.get(url)
        if "error" in r:
            raise type("E", (Exception,), {"code": int(r["error"][:3])})()
        return json.loads(r["data"])

    table = collections.defaultdict(lambda: [0, 0])
    exact, again = [0], [0]
    kinds = collections.Counter()
    for m in mrns:
        for qt in queries:
            url = REAL + qt.format(m=m)
            x, y = shape(_get)(url.replace("|", "%7C")), shape(mine)(url)
            again[0] += shape(_get)(url.replace("|", "%7C"))[:4] == x[:4]  # the released server asked the same search a second time
            same = x[:4] == y[:4]
            table[qt][0] += same
            table[qt][1] += 1
            exact[0] += x[:5] == y[:5]
            if not same:
                sorted_search = "_sort" in qt
                if x[0] != y[0]:
                    k = "one server returned an error"
                elif sorted(x[4]) != sorted(y[4]):
                    k = ("different records on the page, with the same sample times: results that share one time are split across pages differently"
                         if x[5] == y[5] else "different records on the page, with different sample times")
                elif x[2] != y[2]:
                    k = "same records; only one server states a total"
                elif x[3] != y[3]:
                    k = "same records; different links"
                else:
                    k = "same records in a different order"
                kinds[("sorted search" if sorted_search else "unsorted search") + ": " + k] += 1
            if not same and a.verbose:
                print("DIFF", qt, [(len(v[1]) if v[0] == "ok" else v[1], v[2:] ) for v in (x, y)], (x[1][:4], y[1][:4]) if x[0] == y[0] == "ok" else "")
    out = {"patients": len(mrns), "searches": [{"search": q.replace("{m}", "PATIENT"), "same": v[0], "of": v[1]} for q, v in table.items()]}
    out["all_same"] = sum(v[0] for v in table.values())
    out["all"] = sum(v[1] for v in table.values())
    out["same_including_order_within_identical_times"] = exact[0]
    out["differences_by_kind"] = dict(kinds)
    out["released_server_same_as_itself_on_a_second_request"] = again[0]
    out["compared"] = "for each search: success or error, the ids of the returned results in order (order among results with the same sample time ignored for sorted searches), the stated total, and the relations of the links (self, next, previous)"
    print(json.dumps(out, indent=1))
    if a.out:
        json.dump(out, open(a.out, "w"), indent=1)


def decision_points(res):
    """Every moment a potassium result was reported, with the chart as it then stood, and the proved program's outcome."""
    decisions, meta = [], []
    for mrn in sorted(res):
        rows = res[mrn]["K"]
        for tau in sorted({epoch(r["issued"]) for r in rows}):
            chart = [r for r in rows if epoch(r["issued"]) <= tau]
            decisions.append((tau, [(epoch(r["effectiveDateTime"]), tenths(r["valueQuantity"]["value"]), r["status"] == "final") for r in chart]))
            meta.append((mrn, tau, len(chart)))
    return decisions, meta, oracle(decisions)


def cases(a):
    res = json.load(open(a.resources))
    decisions, meta, outs = decision_points(res)
    rng = random.Random(a.seed)
    order = list(range(len(meta)))
    rng.shuffle(order)
    out = []
    for n, i in enumerate(order):
        (mrn, tau, size), o = meta[i], outs[i]
        out.append({"label": f"m{n:05d}", "patient": f"S8{n:06d}", "source": mrn, "moment": tau, "rows": size, "set": o[0], "kind": o[0],
                    "oracle": list(o), "dose": o[3] if o[0] == "replace" else None})
    json.dump({"seed": a.seed, "clock": CLOCK, "cases": out}, open(a.out, "w"))
    print(len(out), "report moments", dict(collections.Counter(c["kind"] for c in out)), "patients", len(res))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch"); f.add_argument("--records", required=True); f.add_argument("--out", required=True)
    c = sub.add_parser("conformance"); c.add_argument("--resources", required=True); c.add_argument("--patients", type=int, default=12); c.add_argument("--out"); c.add_argument("--verbose", action="store_true")
    k = sub.add_parser("cases"); k.add_argument("--resources", required=True); k.add_argument("--out", required=True); k.add_argument("--seed", type=int, default=11)
    a = p.parse_args()
    {"fetch": fetch, "conformance": conformance, "cases": cases}[a.cmd](a)
