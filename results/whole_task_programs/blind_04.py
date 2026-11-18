# Written by deepseek/deepseek-v4.1-flash-1017, condition "blind", seed 4, temperature 1.0. Unedited.
import json
import math
import urllib.parse


def run_task(get, api_base, mrn):
    base = api_base.rstrip("/")
    now = "2023-11-13T10:15:00+00:00"
    next_morning = "2023-11-14T08:00:00+00:00"

    def make_url(path, params=None):
        url = base + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        return url

    def parse_entries(text):
        try:
            data = json.loads(text)
        except Exception:
            return []
        if not isinstance(data, dict):
            return []
        if data.get("resourceType") == "Bundle":
            out = []
            for entry in data.get("entry", []) or []:
                if isinstance(entry, dict) and isinstance(entry.get("resource"), dict):
                    out.append(entry["resource"])
            return out
        if data.get("resourceType"):
            return [data]
        return []

    def obs_value(obs):
        if isinstance(obs.get("valueQuantity"), dict):
            value = obs["valueQuantity"].get("value")
            if value is not None:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    pass
        if obs.get("valueString") is not None:
            try:
                return float(obs["valueString"])
            except (TypeError, ValueError):
                pass
        return None

    def obs_date(obs):
        for key in ("effectiveDateTime", "issued"):
            if obs.get(key):
                return str(obs[key])
        period = obs.get("effectivePeriod")
        if isinstance(period, dict) and period.get("start"):
            return str(period["start"])
        return ""

    patient_entries = parse_entries(
        get(make_url("/Patient", {"identifier": mrn}))
    )
    patient_entries = [
        r for r in patient_entries if r.get("resourceType") == "Patient"
    ]

    if not patient_entries:
        return ([], [f"No patient found for identifier {mrn}."])

    patient_id = patient_entries[0].get("id")
    if not patient_id:
        return ([], [f"No patient id found for identifier {mrn}."])

    patient_id = str(patient_id)

    def get_observations(code):
        entries = parse_entries(
            get(make_url("/Observation", {"patient": patient_id, "code": code}))
        )
        return [r for r in entries if r.get("resourceType") == "Observation"]

    observations = get_observations("K")
    if not any(obs_value(o) is not None for o in observations):
        observations = get_observations("2823-3")

    best_value = None
    best_date = None
    best_obs = None

    for obs in observations:
        value = obs_value(obs)
        if value is None:
            continue
        date = obs_date(obs)
        if best_obs is None or date >= best_date:
            best_obs = obs
            best_date = date
            best_value = value

    if best_obs is None:
        return ([], ["No potassium level found."])

    potassium = best_value

    if potassium >= 3.5:
        return (
            [],
            [f"Most recent potassium level is {potassium:g} mEq/L; no replacement ordered."]
        )

    deficit = 3.5 - potassium
    increments = math.ceil(round(deficit / 0.1, 6))
    dose = int(increments * 10)

    patient_ref = (
        patient_id if patient_id.startswith("Patient/") else f"Patient/{patient_id}"
    )

    medication_payload = {
        "resourceType": "MedicationRequest",
        "medicationCodeableConcept": {
            "coding": [
                {
                    "system": "http://hl7.org/fhir/sid/ndc",
                    "code": "40032-917-01",
                    "display": "Potassium replacement",
                }
            ],
            "text": "Potassium replacement",
        },
        "authoredOn": now,
        "dosageInstruction": [
            {
                "route": {"text": "oral"},
                "doseAndRate": [
                    {
                        "doseQuantity": {
                            "value": dose,
                            "unit": "mEq",
                        }
                    }
                ],
            }
        ],
        "status": "active",
        "intent": "order",
        "subject": {"reference": patient_ref},
    }

    service_request_payload = {
        "resourceType": "ServiceRequest",
        "code": {
            "coding": [
                {
                    "system": "http://loinc.org",
                    "code": "2823-3",
                    "display": "Potassium [Moles/volume] in Serum or Plasma",
                }
            ]
        },
        "authoredOn": now,
        "status": "active",
        "intent": "order",
        "priority": "stat",
        "subject": {"reference": patient_ref},
        "occurrenceDateTime": next_morning,
        "note": {"text": "Paired with potassium replacement order."},
    }

    posts = [
        (base + "/MedicationRequest", medication_payload),
        (base + "/ServiceRequest", service_request_payload),
    ]

    answers = [
        f"Most recent potassium level: {potassium:g} mEq/L.",
        f"Ordered potassium replacement: {dose} mEq oral (NDC 40032-917-01).",
        "Ordered morning serum potassium level (LOINC 2823-3) for 2023-11-14T08:00:00+00:00.",
    ]

    return posts, answers
