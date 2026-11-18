# Written by deepseek/deepseek-v4.1-flash-1017, condition "blind", seed 17, temperature 1.0. Unedited.
import json
from urllib.parse import urlencode
from datetime import datetime, timezone


def run_task(get, api_base, mrn):
    base = api_base.rstrip("/")

    def url(path, params=None):
        u = f"{base}/{path}"
        if params:
            u += "?" + urlencode(params)
        return u

    def parse_json(text):
        try:
            return json.loads(text)
        except Exception:
            return None

    # Resolve patient identifier to FHIR Patient id if possible.
    patient_id = mrn
    patient_resp = parse_json(get(url("Patient", {"identifier": mrn})))
    if patient_resp and isinstance(patient_resp.get("entry"), list) and patient_resp["entry"]:
        resource = patient_resp["entry"][0].get("resource", {})
        if resource.get("id"):
            patient_id = resource["id"]

    subject_ref = patient_id if str(patient_id).startswith("Patient/") else f"Patient/{patient_id}"

    # Search for potassium observations, trying LOINC first and then the base name code.
    observations = []
    for code in ("2823-3", "K"):
        obs_resp = parse_json(get(url("Observation", {"code": code, "patient": patient_id})))
        if not obs_resp or not isinstance(obs_resp.get("entry"), list):
            continue

        for entry in obs_resp["entry"]:
            resource = entry.get("resource") if isinstance(entry, dict) else None
            if not resource:
                continue

            value = None
            if isinstance(resource.get("valueQuantity"), dict):
                value = resource["valueQuantity"].get("value")
            elif "valueString" in resource:
                try:
                    value = float(resource["valueString"])
                except Exception:
                    value = None

            if value is None:
                continue

            effective = resource.get("effectiveDateTime")
            if not effective and isinstance(resource.get("effectivePeriod"), dict):
                effective = resource["effectivePeriod"].get("start")
            if not effective:
                effective = resource.get("issued")

            observations.append((effective, float(value), resource))

        if observations:
            break

    posts = []
    answers = []

    if not observations:
        answers.append(f"No serum potassium observations found for patient {mrn}.")
        return posts, answers

    def dt_key(item):
        dt = item[0]
        if not dt:
            return datetime.min.replace(tzinfo=timezone.utc)
        try:
            return datetime.fromisoformat(str(dt).replace("Z", "+00:00"))
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)

    observations.sort(key=dt_key, reverse=True)
    latest_dt, potassium, _ = observations[0]

    if potassium >= 3.5:
        answers.append(
            f"Most recent serum potassium for patient {mrn} is {potassium} mmol/L "
            f"on {latest_dt}. It is not below the goal of 3.5 mmol/L, so no replacement "
            f"potassium or paired morning potassium level was ordered."
        )
        return posts, answers

    dose = int(round((3.5 - potassium) * 100))
    if dose < 0:
        dose = 0

    med_payload = {
        "resourceType": "MedicationRequest",
        "medicationCodeableConcept": {
            "coding": [
                {
                    "system": "http://hl7.org/fhir/sid/ndc",
                    "code": "40032-917-01",
                    "display": "Potassium replacement"
                }
            ],
            "text": "Potassium chloride oral replacement"
        },
        "authoredOn": "2023-11-13T10:15:00+00:00",
        "dosageInstruction": [
            {
                "route": {"text": "oral"},
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
        "subject": {"reference": subject_ref}
    }

    lab_payload = {
        "resourceType": "ServiceRequest",
        "code": {
            "coding": [
                {
                    "system": "http://loinc.org",
                    "code": "2823-3",
                    "display": "Serum potassium"
                }
            ]
        },
        "authoredOn": "2023-11-13T10:15:00+00:00",
        "status": "active",
        "intent": "order",
        "priority": "stat",
        "subject": {"reference": subject_ref},
        "occurrenceDateTime": "2023-11-14T08:00:00+00:00",
        "note": {
            "text": (
                f"Morning serum potassium level paired with potassium replacement order "
                f"({dose} mEq oral potassium) for patient {mrn}."
            )
        }
    }

    posts.append((url("MedicationRequest"), med_payload))
    posts.append((url("ServiceRequest"), lab_payload))

    answers.append(
        f"Most recent serum potassium for patient {mrn} is {potassium} mmol/L on {latest_dt}. "
        f"This is below 3.5 mmol/L, so ordered {dose} mEq oral potassium replacement "
        f"(NDC 40032-917-01) and a paired morning serum potassium level (LOINC 2823-3) "
        f"for 2023-11-14T08:00:00+00:00."
    )

    return posts, answers
