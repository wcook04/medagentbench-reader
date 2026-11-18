# Written by deepseek/deepseek-v4.1-flash-1017, condition "blind", seed 8, temperature 1.0. Unedited.
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

    # Resolve patient identifier to FHIR patient ID
    pat_url = f"{base}/Patient?" + urlencode({"identifier": mrn})
    pats = bundle_resources(fetch_json(pat_url))
    patient_id = None
    if pats:
        patient_id = pats[0].get("id")
    if not patient_id:
        patient_id = mrn

    # Find most recent serum potassium observation
    obs_url = f"{base}/Observation?" + urlencode({
        "patient": patient_id,
        "code": "2823-3"
    })
    observations = bundle_resources(fetch_json(obs_url))

    potassium_obs = []
    for r in observations:
        if not isinstance(r, dict):
            continue

        val = None
        date = obs_date(r)

        codes = coding_codes(r.get("code"))
        if "2823-3" in codes or any("potassium" in c.lower() for c in codes):
            val = obs_value(r)
        else:
            for comp in r.get("component", []) or []:
                if not isinstance(comp, dict):
                    continue
                ccodes = coding_codes(comp.get("code"))
                if "2823-3" in ccodes or any("potassium" in c.lower() for c in ccodes):
                    val = obs_value(comp)
                    break

        if val is not None:
            potassium_obs.append((date, val, r))

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
