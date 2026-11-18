# Written by deepseek/deepseek-v4.1-flash-1017, condition "blind", seed 11, temperature 1.0. Unedited.
def run_task(get, api_base, mrn):
    import json
    from urllib.parse import urlencode
    from datetime import datetime, timezone, timedelta
    from decimal import Decimal, ROUND_CEILING

    base = api_base.rstrip("/")

    def fetch_json(url):
        body = get(url)
        try:
            return json.loads(body)
        except Exception:
            return {}

    def entries_of(bundle):
        if isinstance(bundle, dict) and bundle.get("resourceType") == "Bundle":
            return bundle.get("entry", []) or []
        if isinstance(bundle, dict) and bundle.get("resourceType"):
            return [{"resource": bundle}]
        return []

    # Find the patient's FHIR id from the identifier/mrn.
    patient_url = f"{base}/Patient?{urlencode({'identifier': mrn})}"
    patient_bundle = fetch_json(patient_url)

    patient_id = None
    for entry in entries_of(patient_bundle):
        resource = entry.get("resource", {}) if isinstance(entry, dict) else {}
        if resource.get("resourceType") == "Patient" and resource.get("id"):
            patient_id = resource["id"]
            break

    if not patient_id:
        # Fallback so the order still has a patient reference.
        patient_id = mrn

    patient_ref = f"Patient/{patient_id}"

    # Search lab observations for potassium ("K").
    obs_url = f"{base}/Observation?{urlencode({'patient': patient_ref, 'code': 'K'})}"
    obs_bundle = fetch_json(obs_url)

    def parse_dt(value):
        if not value or not isinstance(value, str):
            return datetime.min.replace(tzinfo=timezone.utc)
        try:
            v = value.replace("Z", "+00:00")
            dt = datetime.fromisoformat(v)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)

    observations = []
    for entry in entries_of(obs_bundle):
        resource = entry.get("resource", {}) if isinstance(entry, dict) else {}
        if resource.get("resourceType") != "Observation":
            continue

        date_str = (
            resource.get("effectiveDateTime")
            or resource.get("issued")
            or resource.get("effectiveInstant")
        )

        value = None
        if isinstance(resource.get("valueQuantity"), dict):
            value = resource["valueQuantity"].get("value")
        elif resource.get("valueString") is not None:
            value = resource.get("valueString")
        elif isinstance(resource.get("valueCodeableConcept"), dict):
            value = resource["valueCodeableConcept"].get("text")

        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            continue

        observations.append({
            "date": parse_dt(date_str),
            "date_str": date_str,
            "value": numeric_value,
            "resource": resource,
        })

    observations.sort(key=lambda x: x["date"], reverse=True)

    # Context time is fixed for this task.
    now = datetime(2023, 11, 13, 10, 15, 0, tzinfo=timezone.utc)
    now_iso = now.isoformat()
    tomorrow_8am = (now.date() + timedelta(days=1))
    next_lab_time = datetime(
        tomorrow_8am.year, tomorrow_8am.month, tomorrow_8am.day,
        8, 0, 0, tzinfo=timezone.utc
    ).isoformat()

    posts = []
    answers = []

    if not observations:
        answers.append(f"No serum potassium level found for patient {patient_id}.")
        return posts, answers

    most_recent = observations[0]
    level = most_recent["value"]
    level_date = most_recent["date_str"] or "unknown date"

    answers.append(
        f"Most recent potassium level for patient {patient_id}: {level} mEq/L on {level_date}."
    )

    if level >= 3.5:
        answers.append("Potassium level is not low; no replacement potassium order was placed.")
        return posts, answers

    deficit = Decimal("3.5") - Decimal(str(level))
    increments = (deficit / Decimal("0.1")).to_integral_value(rounding=ROUND_CEILING)
    total_mEq = int(increments) * 10

    med_payload = {
        "resourceType": "MedicationRequest",
        "medicationCodeableConcept": {
            "coding": [
                {
                    "system": "http://hl7.org/fhir/sid/ndc",
                    "code": "40032-917-01",
                    "display": "Potassium chloride 10 mEq oral tablet"
                }
            ],
            "text": "Potassium chloride 10 mEq oral tablet"
        },
        "authoredOn": now_iso,
        "dosageInstruction": [
            {
                "route": {"text": "Oral"},
                "doseAndRate": [
                    {
                        "doseQuantity": {
                            "value": total_mEq,
                            "unit": "mEq"
                        }
                    }
                ]
            }
        ],
        "status": "active",
        "intent": "order",
        "subject": {"reference": patient_ref}
    }

    service_payload = {
        "resourceType": "ServiceRequest",
        "code": {
            "coding": [
                {
                    "system": "http://loinc.org",
                    "code": "2823-3",
                    "display": "Potassium [Mass/volume] in Serum or Plasma"
                }
            ]
        },
        "authoredOn": now_iso,
        "status": "active",
        "intent": "order",
        "priority": "stat",
        "subject": {"reference": patient_ref},
        "occurrenceDateTime": next_lab_time,
        "note": {
            "text": "Morning serum potassium level to monitor potassium repletion."
        }
    }

    posts.append((f"{base}/MedicationRequest", med_payload))
    posts.append((f"{base}/ServiceRequest", service_payload))

    answers.append(
        f"Low potassium: ordered {total_mEq} mEq oral potassium replacement "
        f"(NDC 40032-917-01)."
    )
    answers.append(
        f"Scheduled morning serum potassium level for {next_lab_time}."
    )

    return posts, answers
