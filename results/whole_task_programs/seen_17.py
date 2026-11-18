# Written by deepseek/deepseek-v4.1-flash-1017, condition "seen": blind_17.py after one look at the server's responses on a made-up chart, seed 1017, temperature 1.0. Unedited.
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

    def fetch_all(start_url):
        """Follow FHIR 'next' links so we don't miss newer results on later pages."""
        results = []
        current = start_url
        visited = set()
        while current and current not in visited:
            visited.add(current)
            resp = parse_json(get(current))
            if not resp:
                break
            for entry in resp.get("entry", []) or []:
                results.append(entry)
            nxt = None
            for link in resp.get("link", []) or []:
                if link.get("relation") == "next":
                    nxt = link.get("url")
                    break
            current = nxt
        return results

    # Resolve patient identifier to a FHIR Patient id.
    patient_id = mrn
    patient_resp = parse_json(get(url("Patient", {"identifier": mrn})))
    if patient_resp and isinstance(patient_resp.get("entry"), list) and patient_resp["entry"]:
        resource = patient_resp["entry"][0].get("resource", {})
        if resource.get("id"):
            patient_id = resource["id"]

    subject_ref = patient_id if str(patient_id).startswith("Patient/") else f"Patient/{patient_id}"

    # Look up potassium observations, trying LOINC first, then the base name "K".
    observations = []
    for code in ("2823-3", "K"):
        entries = fetch_all(
            url("Observation", {"code": code, "patient": patient_id, "_count": 100})
        )
        for entry in entries:
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

    # Goal is 3.5 mmol/L; anything at or above goal needs no repletion.
    if potassium >= 3.5:
        answers.append(
            f"Most recent serum potassium for patient {mrn} is {potassium} mmol/L "
            f"on {latest_dt}, which is not below the 3.5 mmol/L goal. "
            f"No replacement potassium or follow-up potassium level was ordered."
        )
        return posts, answers

    # Dosing: 10 mEq oral potassium for every 0.1 mmol/L below 3.5.
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
        f"Most recent serum potassium for patient {mrn} is {potassium} mmol/L on {latest_dt}, "
        f"below the 3.5 mmol/L goal. Ordered {dose} mEq oral potassium replacement "
        f"(NDC 40032-917-01) and a paired morning serum potassium level (LOINC 2823-3) "
        f"for 2023-11-14T08:00:00+00:00."
    )

    return posts, answers
