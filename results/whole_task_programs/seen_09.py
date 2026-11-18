# Written by deepseek/deepseek-v4.1-flash-1017, condition "seen": blind_09.py after one look at the server's responses on a made-up chart, seed 1009, temperature 1.0. Unedited.
def run_task(get, api_base, mrn):
    import json
    import math
    from datetime import datetime, timezone
    from urllib.parse import urlencode

    base = api_base.rstrip("/")
    now = "2023-11-13T10:15:00+00:00"
    next_day_8am = "2023-11-14T08:00:00+00:00"

    def as_json(resp):
        if isinstance(resp, dict):
            return resp
        return json.loads(resp)

    def bundle_entries(bundle):
        return (bundle or {}).get("entry", []) or []

    def parse_dt(value):
        if not value:
            return datetime(1970, 1, 1, tzinfo=timezone.utc)
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except Exception:
            return datetime(1970, 1, 1, tzinfo=timezone.utc)

    # Find the patient by MRN identifier.
    patient_url = f"{base}/Patient?{urlencode({'identifier': mrn})}"
    patient_bundle = as_json(get(patient_url))
    patient_id = None
    for entry in bundle_entries(patient_bundle):
        resource = entry.get("resource", {})
        if resource.get("resourceType") == "Patient" and resource.get("id"):
            patient_id = resource["id"]
            break

    if not patient_id:
        return [], [f"No patient found for identifier {mrn}."]

    # Fetch all observations for the patient; filter for potassium client-side
    # (the server's `code` search parameter does not match LOINC in this env).
    obs_url = f"{base}/Observation?{urlencode({'patient': patient_id})}"
    obs_bundle = as_json(get(obs_url))

    def is_potassium_obs(resource):
        code = resource.get("code") or {}
        for coding in (code.get("coding") or []):
            if coding.get("code") == "2823-3":
                return True
            if coding.get("system") == "http://loinc.org" and coding.get("code") == "2823-3":
                return True
        text = (code.get("text") or "").lower()
        if "potassium" in text:
            return True
        for coding in (code.get("coding") or []):
            if "potassium" in (coding.get("display") or "").lower():
                return True
        return False

    most_recent = None
    most_recent_dt = None
    most_recent_level = None

    for entry in bundle_entries(obs_bundle):
        resource = entry.get("resource", {})
        if resource.get("resourceType") != "Observation":
            continue
        if not is_potassium_obs(resource):
            continue

        value = None
        vq = resource.get("valueQuantity") or {}
        if isinstance(vq, dict) and "value" in vq:
            try:
                value = float(vq["value"])
            except Exception:
                value = None

        if value is None and "valueString" in resource:
            try:
                value = float(resource["valueString"])
            except Exception:
                value = None

        if value is None:
            continue

        dt_str = resource.get("effectiveDateTime") or resource.get("issued")
        dt = parse_dt(dt_str)

        if most_recent is None or dt > most_recent_dt:
            most_recent = resource
            most_recent_dt = dt
            most_recent_level = value

    if most_recent is None or most_recent_level is None:
        return [], ["No serum potassium level found; no replacement potassium ordered."]

    if most_recent_level >= 3.5:
        return [], [
            f"Most recent serum potassium level is {most_recent_level} mEq/L; not low, so no replacement potassium ordered."
        ]

    # Dosing: 10 mEq potassium for every 0.1 mEq/L below 3.5, rounded up to next 10 mEq.
    deficit = 3.5 - most_recent_level
    units_of_0_1 = math.ceil(round(deficit / 0.1, 10))
    dose_mEq = units_of_0_1 * 10

    subject_ref = f"Patient/{patient_id}"

    med_request = {
        "resourceType": "MedicationRequest",
        "medicationCodeableConcept": {
            "coding": [
                {
                    "system": "http://hl7.org/fhir/sid/ndc",
                    "code": "40032-917-01",
                    "display": "Potassium oral replacement",
                }
            ],
            "text": "Potassium oral replacement",
        },
        "authoredOn": now,
        "dosageInstruction": [
            {
                "route": {"text": "oral"},
                "doseAndRate": [
                    {
                        "doseQuantity": {
                            "value": dose_mEq,
                            "unit": "mEq",
                        }
                    }
                ],
            }
        ],
        "status": "active",
        "intent": "order",
        "subject": {"reference": subject_ref},
    }

    service_request = {
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
        "subject": {"reference": subject_ref},
        "occurrenceDateTime": next_day_8am,
        "note": {
            "text": "Morning serum potassium level to pair with potassium replacement order."
        },
    }

    posts = [
        (f"{base}/MedicationRequest", med_request),
        (f"{base}/ServiceRequest", service_request),
    ]

    answers = [
        f"Most recent serum potassium level is {most_recent_level} mEq/L, which is low. "
        f"Ordered {dose_mEq} mEq oral potassium replacement and a morning serum potassium level for {next_day_8am}."
    ]

    return posts, answers
