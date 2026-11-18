"""Build derived task 9 cases on the LOCAL scratch FHIR server.

For each selected decision point (patient p, potassium result time t) a synthetic patient is created whose
potassium Observations are p's results taken at or before t, in server order, with the same values, units
and statuses, every time shifted by one constant so that the result taken at t lands at the benchmark clock
minus that result's own taken-to-issued lag. The proved program (lean oracle) is re-run on each clone's rows
as read back from the server at the benchmark clock; the build stops if any outcome differs.

Writes identifiers and the clone mapping only to the private folder.

Usage: python3 study/agent/build_cases.py --records PRIVATE/records.json --private PRIVATE/agent
"""
import argparse, collections, copy, json, os, random, sys
from datetime import datetime, timezone
from urllib.request import Request, urlopen

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from apply_rule import oracle, tenths, CLOCK  # noqa: E402

FHIR = "http://127.0.0.1:18179/fhir/"
PREFIX = "S99"          # synthetic patient ids: S99 + 5 digits (no released id starts with S99)
SEED = 20261117
N_CONFLICT, N_NOTLOW = 100, 200


def get(url):
    return json.load(urlopen(url, timeout=60))


def send(method, url, body):
    req = Request(url, data=json.dumps(body).encode(), method=method,
                  headers={"Content-Type": "application/fhir+json"})
    return json.load(urlopen(req, timeout=300))


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def ts(text):
    return int(datetime.fromisoformat(text).timestamp())


def k_rows(mrn):
    b = get(f"{FHIR}Observation?patient={mrn}&code=K&_count=5000&_format=json")
    assert "next" not in {l["relation"] for l in b.get("link", [])}
    return [e["resource"] for e in b.get("entry", [])]


def as_obs(res):
    return [(ts(r["effectiveDateTime"]), tenths(r["valueQuantity"]["value"]), r["status"] == "final") for r in res]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", required=True)
    ap.add_argument("--private", required=True)
    ap.add_argument("--map-only", type=int, default=None,
                    help="write the private case map for the first N clones already on the server; no server access")
    a = ap.parse_args()
    pats = json.load(open(a.records))["patients"]

    # every distinct result time of every patient as a decision time (same as study/apply_rule.py)
    dec, meta = [], []
    for i, p in enumerate(pats):
        obs = [(o["t"], tenths(o["v"]), o["status"] == "final") for o in p["K"]]
        for now in sorted({o["t"] for o in p["K"]}):
            dec.append((now, obs)); meta.append((i, now))
    outs = oracle(dec)
    by_kind = collections.defaultdict(list)
    for m, o in zip(meta, outs):
        by_kind[o[0]].append((m, o))
    rng = random.Random(SEED)
    chosen = [("replace", x) for x in by_kind["replace"]]
    chosen += [("conflict", x) for x in rng.sample(by_kind["conflict"], min(N_CONFLICT, len(by_kind["conflict"])))]
    chosen += [("notLow", x) for x in rng.sample(by_kind["notLow"], N_NOTLOW)]
    print({k: sum(1 for c in chosen if c[0] == k) for k in ("replace", "conflict", "notLow")}, flush=True)

    # opaque labels: shuffled order within each set
    order = list(range(len(chosen)))
    rng.shuffle(order)
    counters = collections.Counter()
    labels = {}
    for j in order:
        kind = chosen[j][0]
        counters[kind] += 1
        labels[j] = f"{ {'replace': 'rep', 'conflict': 'con', 'notLow': 'nlo'}[kind] }-{counters[kind]:03d}"

    if a.map_only is not None:
        cases = []
        for j, (kind, ((i, t), out)) in enumerate(chosen[: a.map_only]):
            p = pats[i]
            at_t = [r for r in p["K"] if r["t"] == t]
            lag = max(r["issued"] - t for r in at_t)
            cases.append({"label": labels[j], "set": kind, "patient": f"{PREFIX}{j + 1:05d}", "source_mrn": p["mrn"],
                          "source_t": t, "shift_seconds": (CLOCK - lag) - t, "lag_seconds": lag,
                          "rows": sum(1 for r in p["K"] if r["t"] <= t), "oracle_source": list(out),
                          "oracle": [out[0], out[1] + (CLOCK - lag) - t] + list(out[2:4]) +
                                    ([(CLOCK // 86400 + 1) * 86400 + 8 * 3600] if kind == "replace" else []),
                          "dose": out[3] if kind == "replace" else None})
        json.dump({"prefix": PREFIX, "seed": SEED, "clock": CLOCK, "built_on_server": a.map_only,
                   "observations_added_estimate": sum(c["rows"] for c in cases), "cases": cases, "control": []},
                  open(os.path.join(a.private, "cases.json"), "w"), indent=1)
        print("mapped", len(cases), collections.Counter(c["set"] for c in cases),
              "observations", sum(c["rows"] for c in cases), "lag0", sum(c["lag_seconds"] == 0 for c in cases),
              "lag>1d", sum(c["lag_seconds"] > 86400 for c in cases),
              "doses", sorted(collections.Counter(c["dose"] for c in cases).items()))
        return

    server_rows = {}
    patients = {}
    for p in pats:
        res = k_rows(p["mrn"])
        assert [(ts(r["effectiveDateTime"]), r["valueQuantity"]["value"]) for r in res] == [(o["t"], o["v"]) for o in p["K"]], p["mrn"]
        server_rows[p["mrn"]] = res
        pt = get(f"{FHIR}Patient/{p['mrn']}?_format=json")
        patients[p["mrn"]] = pt

    cases, n_obs = [], 0
    for j, (kind, ((i, t), out)) in enumerate(chosen):
        p = pats[i]
        cid = f"{PREFIX}{j + 1:05d}"
        rows = [r for r in server_rows[p["mrn"]] if ts(r["effectiveDateTime"]) <= t]
        at_t = [r for r in rows if ts(r["effectiveDateTime"]) == t]
        lag = max(ts(r["issued"]) - t for r in at_t)
        delta = (CLOCK - lag) - t
        existing = get(f"{FHIR}Patient?_id={cid}&_summary=count&_format=json").get("total", 0)
        if not existing:
            pt = copy.deepcopy(patients[p["mrn"]])
            pt.pop("meta", None)
            pt["id"] = cid
            for ident in pt.get("identifier", []):
                ident["value"] = cid
            entries = [{"resource": pt, "request": {"method": "PUT", "url": f"Patient/{cid}"}}]
            for r in rows:
                c = copy.deepcopy(r)
                for k in ("id", "meta"):
                    c.pop(k, None)
                c["subject"] = {"reference": f"Patient/{cid}",
                                "identifier": {**r["subject"].get("identifier", {}), "value": cid}}
                c["effectiveDateTime"] = iso(ts(r["effectiveDateTime"]) + delta)
                if "issued" in c:
                    c["issued"] = iso(ts(r["issued"]) + delta)
                entries.append({"resource": c, "request": {"method": "POST", "url": "Observation"}})
            send("POST", FHIR, {"resourceType": "Bundle", "type": "transaction", "entry": entries})
        back = k_rows(cid)
        # same values, units, statuses, order; times shifted by one constant
        assert [(r["valueQuantity"]["value"], r["valueQuantity"].get("unit"), r["status"]) for r in back] == \
               [(r["valueQuantity"]["value"], r["valueQuantity"].get("unit"), r["status"]) for r in rows], cid
        assert [ts(r["effectiveDateTime"]) - delta for r in back] == [ts(r["effectiveDateTime"]) for r in rows], cid
        n_obs += len(back)
        clone_out = oracle([(CLOCK, as_obs(back))])[0]
        expected = out if kind != "replace" else out
        # outcome kind and value must match; times differ by delta; repeatAt is the next morning after the clock
        same = clone_out[0] == out[0] and clone_out[1] == out[1] + delta and clone_out[2:3] == out[2:3]
        if kind == "replace":
            same = same and clone_out[3] == out[3] and clone_out[4] == (CLOCK // 86400 + 1) * 86400 + 8 * 3600
        if not same:
            print("MISMATCH", labels[j], kind, clone_out[0], flush=True)
            sys.exit(2)
        cases.append({"label": labels[j], "set": kind, "patient": cid, "source_mrn": p["mrn"], "source_t": t,
                      "shift_seconds": delta, "lag_seconds": lag, "rows": len(back),
                      "oracle": list(clone_out), "dose": clone_out[3] if kind == "replace" else None})
        if (j + 1) % 100 == 0:
            print(j + 1, "built", flush=True)

    control = []
    clock_out = oracle([(CLOCK, [(o["t"], tenths(o["v"]), o["status"] == "final") for o in p["K"]]) for p in pats])
    crng = random.Random(SEED + 1)
    corder = list(range(len(pats)))
    crng.shuffle(corder)
    for n, i in enumerate(corder, 1):
        p, o = pats[i], clock_out[i]
        control.append({"label": f"ctl-{n:03d}", "set": "control", "patient": p["mrn"], "released_case": p["task9"],
                        "oracle": list(o), "dose": o[3] if o[0] == "replace" else None, "rows": len(p["K"])})
    json.dump({"prefix": PREFIX, "seed": SEED, "clock": CLOCK, "observations_added": n_obs,
               "patients_added": len(cases), "cases": cases, "control": control},
              open(os.path.join(a.private, "cases.json"), "w"), indent=1)
    print("patients", len(cases), "observations", n_obs, flush=True)


if __name__ == "__main__":
    main()
