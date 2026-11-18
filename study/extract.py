"""Read potassium and creatinine results and potassium orders from a locally restored copy of the
MedAgentBench record server and write them to a PRIVATE file. Nothing here is published.

Usage: python3 study/extract.py --bench /path/to/MedAgentBench --out /private/dir/records.json
"""
import argparse, json, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

p = argparse.ArgumentParser()
p.add_argument("--base", default="http://127.0.0.1:18179/fhir/")
p.add_argument("--bench", required=True)
p.add_argument("--out", required=True)
a = p.parse_args()


def get(url):
    with urllib.request.urlopen(url, timeout=300) as r:
        return json.load(r)


def pages(url):
    while url:
        b = get(url)
        for e in b.get("entry", []):
            yield e["resource"]
        url = next((l["url"] for l in b.get("link", []) if l["relation"] == "next"), None)


def epoch(s):
    return int(datetime.fromisoformat(s).timestamp())


def labs(mrn, code):
    out = []
    for o in pages(a.base + f"Observation?patient={mrn}&code={code}&_count=5000&_format=json"):
        q = o.get("valueQuantity") or {}
        out.append({"t": epoch(o["effectiveDateTime"]), "issued": epoch(o["issued"]) if o.get("issued") else None,
                    "v": q.get("value"), "unit": q.get("unit"), "status": o.get("status")})
    return out  # server order kept: the released grader depends on it


def orders(mrn):
    out = []
    for r in pages(a.base + f"MedicationRequest?patient={mrn}&_count=5000&_format=json"):
        text = (r.get("medicationCodeableConcept") or {}).get("text") or ""
        if "potassium" not in text.lower():
            continue
        d = (r.get("dosageInstruction") or [{}])[0]
        dq = ((d.get("doseAndRate") or [{}])[0].get("doseQuantity")) or {}
        out.append({"t": epoch(r["authoredOn"]) if r.get("authoredOn") else None, "text": text,
                    "dose": dq.get("value"), "unit": dq.get("unit"),
                    "route": d.get("route"), "timing": d.get("timing")})
    return out


mrns = [x.get("identifier", [{}])[0].get("value") for x in pages(a.base + "Patient?_count=200&_format=json")]
tasks = json.load(open(a.bench + "/data/medagentbench/test_data_v2.json"))
t9 = {t["eval_MRN"]: t["id"] for t in tasks if t["id"].startswith("task9_")}


def one(m):
    k = labs(m, "K")
    if not k:
        return None
    return {"mrn": m, "task9": t9.get(m), "K": k, "CR": labs(m, "CR"), "orders": orders(m)}


with ThreadPoolExecutor(8) as ex:
    recs = [r for r in ex.map(one, mrns) if r]
json.dump({"patients": recs}, open(a.out, "w"))
print("patients", len(recs), "K", sum(len(r["K"]) for r in recs), "CR", sum(len(r["CR"]) for r in recs),
      "potassium orders", sum(len(r["orders"]) for r in recs))
