# Written by deepseek/deepseek-v4.1-flash-1017, condition "blind", seed 1, temperature 1.0. Unedited.
def run_task(get, api_base, mrn):
    import json
    import math
    import re
    from datetime import datetime, timedelta
    from urllib.parse import quote, urlencode

    base = api_base.rstrip("/")
    NOW = "2023-11-13T10:15:00+00:00"
    now_dt = datetime.fromisoformat(NOW)
    next_morning = (now_dt + timedelta(days=1)).replace(
        hour=8, minute=0, second=0, microsecond=0
    )
    next_morning_iso = next_morning.isoformat()

    def parse_json(text):
        try:
            return json.loads(text)
        except Exception:
            return {}

    def bundle_resources(data):
        if isinstance(data, dict) and data.get("resourceType") == "Bundle":
            return [e.get("resource", {}) for e in data.get("entry", []) if isinstance(e, dict)]
        if isinstance(data, dict) and data.get("resourceType"):
            return [data]
        return []

    def first_patient_id(resources):
        for r in resources:
            if r.get("resourceType") == "Patient" and r.get("id"):
                return r["id"]
        return None

    def obs_datetime(obs):
        return (
            obs.get("effectiveDateTime")
            or obs.get("issued")
            or (obs.get("effectivePeriod") or {}).get("start")
            or ""
        )

    def quantity_value(q):
        if not isinstance(q, dict):
            return None
        v = q.get("value")
        if v is None:
            return None
        try:
            return float(v)
        except Exception:
            return None

    def string_value(v):
        if v is None:
            return None
        m = re.search(r"-?\d+(?:\.\d+)?", str(v))
        if m:
            try:
                return float(m.group(0))
            except Exception:
                return None
        return None

    def potassium_value(obs):
        v = quantity_value(obs.get("valueQuantity"))
        if v is not None:
            return v

        v = string_value(obs.get("valueString"))
        if v is not None:
            return v

        for comp in obs.get("component", []) or []:
            code = comp.get("code") or {}
            is_potassium = False
            for c in code.get("coding", []) or []:
                c_code = str(c.get("code", ""))
                c_disp = str(c.get("display", "")) + " " + str(c.get("text", ""))
                if c_code in ("2823-3", "K") or "potassium" in c_disp.lower():
                    is_potassium = True
                    break
            if "potassium" in str(code.get("text", "")).lower():
                is_potassium = True

            if is_potassium or len(obs.get("component", []) or []) == 1:
                v = quantity_value(comp.get("valueQuantity"))
                if v is not None:
                    return v
                v = string_value(comp.get("valueString"))
                if v is not None:
                    return v

        return None

    # Resolve patient identifier to FHIR patient ID.
    patient_url = f"{base}/Patient?{urlencode({'identifier': mrn})}"
    patient_data = parse_json(get(patient_url))
    patient_resources = bundle_resources(patient_data)
    patient_id = first_patient_id(patient_resources) or mrn

    # Find most recent potassium observation.
    obs_url = f"{base}/Observation?{urlencode({'patient': patient_id, 'code': 'K'})}"
    obs_data = parse_json(get(obs_url))
    observations = bundle_resources(obs_data)

    best = None
    best_dt = ""
    for obs in observations:
        level = potassium_value(obs)
        if level is None:
            continue
        dt = obs_datetime(obs)
        if best is None or dt > best_dt:
            best = (level, dt, obs)
            best_dt = dt

    posts = []
    answers = []

    if best is None:
        answers.append("No recent potassium level was found; no orders were placed.")
        return posts, answers

    level, measured_at, _ = best
    answers.append(
        f"Most recent potassium level: {level:g} mEq/L"
        + (f" on {measured_at}." if measured_at else ".")
    )

    if level < 3.5:
        # For every 0.1 mEq/L below 3.5, order 10 mEq, rounded up to a 0.1 step.
        dose_mEq = max(10, int(math.ceil((3.5 - level) * 10) * 10))

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
            "authoredOn": NOW,
            "dosageInstruction": [
                {
                    "route": {"text": "oral"},
                    "doseAndRate": [
                        {
                            "doseQuantity": {
                                "value": dose_mEq,
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

        lab_payload = {
            "resourceType": "ServiceRequest",
            "code": {
                "coding": [
                    {
                        "system": "http://loinc.org",
                        "code": "2823-3",
                        "display": "Potassium [Moles/volume] in Serum or Plasma"
                    }
                ],
                "text": "Serum potassium level"
            },
            "authoredOn": NOW,
            "status": "active",
            "intent": "order",
            "priority": "stat",
            "subject": {"reference": f"Patient/{patient_id}"},
            "occurrenceDateTime": next_morning_iso,
            "note": {"text": "Morning serum potassium level to be completed the next day at 8am."}
        }

        posts.append((f"{base}/MedicationRequest", med_payload))
        posts.append((f"{base}/ServiceRequest", lab_payload))

        answers.append(
            f"Ordered {dose_mEq} mEq oral potassium replacement (NDC 40032-917-01)."
        )
        answers.append(
            f"Ordered morning serum potassium level for {next_morning_iso}."
        )
    else:
        answers.append("Potassium level is not below 3.5 mEq/L; no replacement order placed.")

    return posts, answers
