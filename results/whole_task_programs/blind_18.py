# Written by deepseek/deepseek-v4.1-flash-1017, condition "blind", seed 18, temperature 1.0. Unedited.
def run_task(get, api_base, mrn):
    import json
    import math
    import re
    from urllib.parse import urlencode

    base = api_base.rstrip("/")
    now_iso = "2023-11-13T10:15:00+00:00"
    next_day_8am_iso = "2023-11-14T08:00:00+00:00"
    potassium_loinc = "2823-3"
    potassium_ndc = "40032-917-01"
    threshold = 3.5

    def fetch(path, params):
        url = f"{base}/{path}?{urlencode(params)}"
        try:
            return json.loads(get(url))
        except Exception:
            return {}

    def resources(bundle):
        if not isinstance(bundle, dict):
            return []
        if isinstance(bundle.get("entry"), list):
            out = []
            for entry in bundle["entry"]:
                if isinstance(entry, dict) and isinstance(entry.get("resource"), dict):
                    out.append(entry["resource"])
            return out
        if bundle.get("resourceType"):
            return [bundle]
        return []

    def to_float(value):
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            match = re.search(r"[-+]?\d*\.?\d+", value)
            if match:
                try:
                    return float(match.group(0))
                except ValueError:
                    pass
        return None

    # Resolve the patient identifier to a FHIR Patient ID when possible.
    patient_bundle = fetch("Patient", {"identifier": mrn})
    patient_id = None
    for resource in resources(patient_bundle):
        if resource.get("resourceType") == "Patient":
            patient_id = resource.get("id")
            if patient_id:
                break
    if not patient_id:
        patient_id = mrn

    # Find the most recent serum potassium observation.
    observation_bundle = fetch(
        "Observation",
        {"patient": patient_id, "code": potassium_loinc},
    )
    observations = [
        r for r in resources(observation_bundle)
        if r.get("resourceType") == "Observation"
    ]

    if not observations:
        observation_bundle = fetch(
            "Observation",
            {"patient": patient_id, "code": "K"},
        )
        observations = [
            r for r in resources(observation_bundle)
            if r.get("resourceType") == "Observation"
        ]

    if not observations:
        return (
            [],
            [f"No serum potassium observation found for patient {mrn}."],
        )

    def observation_date(obs):
        for key in ("effectiveDateTime", "effectiveInstant", "issued"):
            if obs.get(key):
                return str(obs[key])
        return ""

    latest = max(observations, key=observation_date)

    value = None
    quantity = latest.get("valueQuantity")
    if isinstance(quantity, dict):
        value = to_float(quantity.get("value"))

    if value is None:
        value = to_float(latest.get("valueString"))

    if value is None:
        value = to_float(latest.get("value"))

    if value is None:
        for component in latest.get("component", []) or []:
            if not isinstance(component, dict):
                continue
            component_text = json.dumps(component.get("code", {}))
            if (
                potassium_loinc in component_text
                or "Potassium" in component_text
                or '"K"' in component_text
            ):
                component_quantity = component.get("valueQuantity", {})
                if isinstance(component_quantity, dict):
                    value = to_float(component_quantity.get("value"))
                if value is not None:
                    break

    if value is None:
        return (
            [],
            [f"Most recent potassium observation has no numeric value for patient {mrn}."],
        )

    date_text = observation_date(latest)

    if value >= threshold:
        return (
            [],
            [
                f"Most recent serum potassium is {value:g} mmol/L "
                f"on {date_text or 'unknown date'}; not low. "
                "No replacement potassium ordered."
            ],
        )

    deficit = threshold - value
    steps = int(math.ceil(round(deficit / 0.1, 8)))
    if steps < 1:
        steps = 1
    dose_mEq = steps * 10

    medication_request = {
        "resourceType": "MedicationRequest",
        "medicationCodeableConcept": {
            "coding": [
                {
                    "system": "http://hl7.org/fhir/sid/ndc",
                    "code": potassium_ndc,
                    "display": "Potassium replacement",
                }
            ],
            "text": "Potassium replacement",
        },
        "authoredOn": now_iso,
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
        "subject": {"reference": f"Patient/{patient_id}"},
    }

    potassium_lab_request = {
        "resourceType": "ServiceRequest",
        "code": {
            "coding": [
                {
                    "system": "http://loinc.org",
                    "code": potassium_loinc,
                    "display": "Potassium [Moles/volume] in Serum or Plasma",
                }
            ]
        },
        "authoredOn": now_iso,
        "status": "active",
        "intent": "order",
        "priority": "stat",
        "subject": {"reference": f"Patient/{patient_id}"},
        "note": {
            "text": "Morning serum potassium level to be completed the next day at 8am."
        },
        "occurrenceDateTime": next_day_8am_iso,
    }

    posts = [
        (f"{base}/MedicationRequest", medication_request),
        (f"{base}/ServiceRequest", potassium_lab_request),
    ]

    answers = [
        f"Most recent serum potassium is {value:g} mmol/L "
        f"on {date_text or 'unknown date'}, below 3.5.",
        f"Ordered oral potassium replacement {dose_mEq} mEq "
        f"(NDC {potassium_ndc}).",
        "Scheduled morning serum potassium level for "
        "2023-11-14 at 08:00.",
    ]

    return posts, answers
