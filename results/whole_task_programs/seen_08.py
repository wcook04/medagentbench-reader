# Written by deepseek/deepseek-v4.1-flash-1017, condition "seen": blind_08.py after one look at the server's responses on a made-up chart, seed 1008, temperature 1.0. Unedited.
import json
import math
import re
from urllib.parse import urlencode

def run_task(get, api_base, mrn):
    base = api_base.rstrip("/")
    now = "2023-11-13T10:15:00+00:00"

    def fetch_json(url):
        txt = get(url)
        try:
            return json.loads(txt)
        except Exception:
            return None

    def bundle_resources(obj):
        if not isinstance(obj, dict):
            return []
        if obj.get("resourceType") == "Bundle":
            return [
                e.get("resource")
                for e in obj.get("entry", [])
                if isinstance(e, dict) and isinstance(e.get("resource"), dict)
            ]
        if obj.get("resourceType"):
            return [obj]
        return []

    def coding_codes(cc):
        codes = []
        if not isinstance(cc, dict):
            return codes
        for c in cc.get("coding", []) or []:
            if isinstance(c, dict) and c.get("code"):
                codes.append(str(c["code"]))
        if cc.get("text"):
            codes.append(str(cc["text"]))
        return codes

    def obs_value(res):
        vq = res.get("valueQuantity")
        if isinstance(vq, dict) and "value" in vq:
            try:
                return float(vq["value"])
            except Exception:
                pass
        if "valueString" in res:
            m = re.search(r"-?\d+(?:\.\d+)?", str(res["valueString"]))
            if m:
                try:
                    return float(m.group(0))
                except Exception:
                    pass
        return None

    def obs_date(res):
        for k in ("effectiveDateTime", "issued", "effectiveInstant"):
            if res.get(k):
                return str(res[k])
        ep = res.get("effectivePeriod")
        if isinstance(ep, dict) and ep.get("start"):
            return str(ep["start"])
        return ""

    def is_potassium_coding(cc):
        codes = coding_codes(cc)
        for c in codes:
            if c == "2823-3" or c == "K":
                return True
            lc = c.lower()
            if "potassium" in lc:
                return True
        return False

    def extract_potassium(res):
        """Return (value, date) if resource has potassium value, else None."""
        date = obs_date(res)
        if is_potassium_coding(res.get("code")):
            v = obs_value(res)
            if v is not None:
                return (date, v)
        for comp in res.get("component", []) or []:
            if not isinstance(comp, dict):
                continue
            if is_potassium_coding(comp.get("code")):
                v = obs_value(comp)
                if v is not None:
                    return (date, v)
        return None

    # Resolve patient identifier to FHIR patient ID
    pat_url = f"{base}/Patient?" + urlencode({"identifier": mrn})
    pats = bundle_resources(fetch_json(pat_url))
    patient_id = None
    if pats:
        patient_id = pats[0].get("id")
    if not patient_id:
        patient_id = mrn

    # Try several search strategies to find potassium observations
    search_urls = [
        f"{base}/Observation?" + urlencode({"patient": patient_id, "code": "2823-3"}),
        f"{base}/Observation?" + urlencode({"patient": patient_id, "code": "K"}),
        f"{base}/Observation?" + urlencode({"patient": patient_id, "category": "laboratory"}),
        f"{base}/Observation?" + urlencode({"patient": patient_id}),
    ]

    potassium_obs = []
    seen = set()
    for url in search_urls:
        resources = bundle_resources(fetch_json(url))
        for r in resources:
            if not isinstance(r, dict):
                continue
            rid = r.get("id")
            if rid and rid in seen:
                continue
            if rid:
                seen.add(rid)
            if r.get("resourceType") != "Observation":
                continue
            got = extract_potassium(r)
            if got is not None:
                potassium_obs.append((got[0], got[1], r))

    if not potassium_obs:
        return (
            [],
            [f"No serum potassium level found for patient identifier {mrn}."]
        )

    potassium_obs.sort(key=lambda x: x[0] or "")
    latest_date, level, latest = potassium_obs[-1]

    posts = []
    answers = [
        f"Most recent serum potassium level: {level} mmol/L (LOINC 2823-3) on {latest_date or 'unknown date'}."
    ]

    if level < 3.5:
        deficit = 3.5 - level
        dose = int(math.ceil((deficit / 0.1) - 1e-9) * 10)
        if dose < 10:
            dose = 10

        med_payload = {
            "resourceType": "MedicationRequest",
            "medicationCodeableConcept": {
                "coding": [
                    {
                        "system": "http://hl7.org/fhir/sid/ndc",
                        "code": "40032-917-01",
                        "display": "Potassium oral replacement"
                    }
                ],
                "text": "Potassium oral replacement"
            },
            "authoredOn": now,
            "dosageInstruction": [
                {
                    "route": {"text": "Oral"},
                    "doseAndRate": [
                        {
                            "doseQuantity": {
                                "value": dose,
                                "unit": "mEq"
                            }
                        }
                    ]
                }
            ],
            "status": "active",
            "intent": "order",
            "subject": {"reference": f"Patient/{patient_id}"}
        }
        posts.append((f"{base}/MedicationRequest", med_payload))
        answers.append(
            f"Ordered {dose} mEq oral potassium replacement (NDC 40032-917-01) for serum potassium {level} mmol/L."
        )

        service_payload = {
            "resourceType": "ServiceRequest",
            "code": {
                "coding": [
                    {
                        "system": "http://loinc.org",
                        "code": "2823-3",
                        "display": "Potassium [Mass/volume] in Serum or Plasma"
                    }
                ],
                "text": "Morning serum potassium level"
            },
            "authoredOn": now,
            "status": "active",
            "intent": "order",
            "priority": "stat",
            "subject": {"reference": f"Patient/{patient_id}"},
            "occurrenceDateTime": "2023-11-14T08:00:00+00:00",
            "note": {
                "text": "Morning serum potassium level to be completed the next day at 8am, paired with potassium replacement order."
            }
        }
        posts.append((f"{base}/ServiceRequest", service_payload))
        answers.append(
            "Ordered morning serum potassium level (LOINC 2823-3) for 2023-11-14T08:00:00+00:00."
        )
    else:
        answers.append(
            "Potassium level is not below the 3.5 mmol/L threshold; no replacement or follow-up potassium order was placed."
        )

    return (posts, answers)
