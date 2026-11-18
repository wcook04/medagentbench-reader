# Written by deepseek/deepseek-v4.1-flash-1017, condition "seen": blind_01.py after one look at the server's responses on a made-up chart, seed 1001, temperature 1.0. Unedited.
def run_task(get, api_base, mrn):
    import json
    import math
    from datetime import datetime, timedelta
    from urllib.parse import urlencode

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

    def potassium_value(obs):
        vq = obs.get("valueQuantity")
        if isinstance(vq, dict) and vq.get("value") is not None:
            try:
                return float(vq["value"])
            except Exception:
                pass
        return None

    def fetch_all_bundle_resources(url):
        """Fetch a Bundle and follow pagination via 'next' links."""
        all_resources = []
        seen_urls = set()
        current = url
        while current and current not in seen_urls:
            seen_urls.add(current)
            data = parse_json(get(current))
            all_resources.extend(bundle_resources(data))
            next_url = None
            if isinstance(data, dict):
                for link in data.get("link", []) or []:
                    if isinstance(link, dict) and link.get("relation") == "next":
                        next_url = link.get("url")
                        break
            current = next_url
        return all_resources

    # Resolve patient identifier to FHIR patient ID.
    patient_url = f"{base}/Patient?{urlencode({'identifier': mrn})}"
    patient_data = parse_json(get(patient_url))
    patient_resources = bundle_resources(patient_data)
    patient_id = first_patient_id(patient_resources) or mrn

    # Find most recent potassium observation (following pagination).
    obs_url = f"{base}/Observation?{urlencode({'patient': patient_id, 'code': 'K'})}"
    observations = fetch_all_bundle_resources(obs_url)

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
        # For every 0.1 mEq/L below 3.5, order 10 mEq, rounded up to 0.1 step.
        dose_mEq = int(math.ceil((3.5 - level) * 10) * 10)
        if dose_mEq < 10:
            dose_mEq = 10

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
        answers.append(
            "Potassium level is not below 3.5 mEq/L; no replacement order placed."
        )

    return posts, answers
