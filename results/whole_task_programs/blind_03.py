# Written by deepseek/deepseek-v4.1-flash-1017, condition "blind", seed 3, temperature 1.0. Unedited.
def run_task(get, api_base, mrn):
    import json
    import math
    import re
    from urllib.parse import urlencode

    base = api_base.rstrip("/")
    now = "2023-11-13T10:15:00+00:00"
    next_morning = "2023-11-14T08:00:00+00:00"
    potassium_loinc = "2823-3"
    potassium_code = "K"
    potassium_ndc = "40032-917-01"

    def parse_json(text):
        try:
            return json.loads(text)
        except Exception:
            return None

    def to_number(value):
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            match = re.search(r"[-+]?\d+(?:\.\d+)?", value)
            if match:
                return float(match.group(0))
        return None

    def entries_from_bundle(data):
        if not isinstance(data, dict):
            return []
        if data.get("resourceType") == "Bundle":
            return data.get("entry", []) or []
        if data.get("resourceType"):
            return [{"resource": data}]
        return []

    posts = []

    patient_search = parse_json(get(base + "/Patient?" + urlencode({"identifier": mrn})))
    patient_id = None

    for entry in entries_from_bundle(patient_search):
        resource = entry.get("resource", {})
        if resource.get("resourceType") == "Patient" and resource.get("id"):
            patient_id = resource["id"]
            break

    if not patient_id:
        return posts, [f"Unable to find a patient with identifier {mrn}."]

    obs_search = parse_json(get(base + "/Observation?" + urlencode({
        "patient": patient_id,
        "code": potassium_code,
    })))

    potassium_values = []

    for entry in entries_from_bundle(obs_search):
        resource = entry.get("resource", {})
        if resource.get("resourceType") != "Observation":
            continue

        raw_value = None
        if isinstance(resource.get("valueQuantity"), dict):
            raw_value = resource["valueQuantity"].get("value")
        if raw_value is None:
            raw_value = resource.get("valueString")

        value = to_number(raw_value)
        if value is None:
            continue

        when = (
            resource.get("effectiveDateTime")
            or resource.get("issued")
            or (resource.get("effectivePeriod") or {}).get("start")
            or ""
        )
        potassium_values.append((when, value))

    if not potassium_values:
        return posts, [f"No potassium level was found for patient {mrn}."]

    potassium_values.sort(key=lambda item: item[0] or "")
    latest_when, latest_level = potassium_values[-1]

    if latest_level >= 3.5:
        return posts, [
            f"Most recent potassium level is {latest_level:g} mEq/L, which is not low. "
            "No replacement potassium or follow-up potassium order was placed."
        ]

    diff = 3.5 - latest_level
    units = int(math.ceil(diff / 0.1 - 1e-9))
    dose_mEq = max(units * 10, 10)

    med_payload = {
        "resourceType": "MedicationRequest",
        "medicationCodeableConcept": {
            "coding": [
                {
                    "system": "http://hl7.org/fhir/sid/ndc",
                    "code": potassium_ndc,
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
        "subject": {"reference": f"Patient/{patient_id}"},
    }

    service_payload = {
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
        "authoredOn": now,
        "status": "active",
        "intent": "order",
        "priority": "stat",
        "subject": {"reference": f"Patient/{patient_id}"},
        "note": {"text": "Morning serum potassium level"},
        "occurrenceDateTime": next_morning,
    }

    posts.append((base + "/MedicationRequest", med_payload))
    posts.append((base + "/ServiceRequest", service_payload))

    answer = (
        f"Most recent potassium level is {latest_level:g} mEq/L, which is low. "
        f"Ordered {dose_mEq} mEq oral potassium replacement (NDC {potassium_ndc}) "
        f"and a morning serum potassium level for 2023-11-14 at 08:00."
    )
    return posts, [answer]
