# Written by deepseek/deepseek-v4.1-flash-1017, condition "blind", seed 15, temperature 1.0. Unedited.
def run_task(get, api_base, mrn):
    import json
    import math
    from urllib.parse import urlencode

    base = api_base.rstrip("/")
    now = "2023-11-13T10:15:00+00:00"
    next_day_8am = "2023-11-14T08:00:00+00:00"
    posts = []

    def fetch_json(path, params):
        url = f"{base}/{path}?{urlencode(params)}"
        text = get(url)
        try:
            return json.loads(text)
        except Exception:
            return {}

    # Resolve the MRN identifier to the patient's FHIR ID.
    patient_bundle = fetch_json("Patient", {"identifier": mrn})
    patient_id = mrn
    for entry in patient_bundle.get("entry", []) if isinstance(patient_bundle, dict) else []:
        resource = entry.get("resource", {})
        if resource.get("resourceType") == "Patient" and resource.get("id"):
            patient_id = resource["id"]
            break

    # Search for potassium labs using the potassium base code "K".
    obs_bundle = fetch_json("Observation", {"patient": patient_id, "code": "K"})

    candidates = []
    for entry in obs_bundle.get("entry", []) if isinstance(obs_bundle, dict) else []:
        resource = entry.get("resource", {})
        if resource.get("resourceType") != "Observation":
            continue

        value = None
        value_quantity = resource.get("valueQuantity", {})
        if isinstance(value_quantity, dict) and "value" in value_quantity:
            value = value_quantity["value"]
        elif "valueString" in resource:
            try:
                value = float(resource["valueString"])
            except Exception:
                value = None

        if value is None:
            continue

        when = (
            resource.get("effectiveDateTime")
            or resource.get("issued")
            or resource.get("meta", {}).get("lastUpdated")
            or ""
        )
        candidates.append((when, float(value), resource))

    if not candidates:
        return posts, [f"No serum potassium result found for patient {mrn}."]

    candidates.sort(key=lambda item: item[0], reverse=True)
    observed_at, potassium, _ = candidates[0]
    is_low = potassium < 3.5

    answer = (
        f"Most recent serum potassium for patient {mrn} is {potassium} mEq/L "
        f"on {observed_at}. "
    )

    if is_low:
        deficit = 3.5 - potassium
        # One 10 mEq oral dose for each 0.1 mEq/L, or portion thereof, below goal.
        meq = int(math.ceil(round(deficit, 10) / 0.1) * 10)
        if meq <= 0:
            meq = 10

        medication_request = {
            "resourceType": "MedicationRequest",
            "medicationCodeableConcept": {
                "coding": [
                    {
                        "system": "http://hl7.org/fhir/sid/ndc",
                        "code": "40032-917-01",
                        "display": "Potassium replacement oral"
                    }
                ],
                "text": "Replacement potassium oral"
            },
            "authoredOn": now,
            "dosageInstruction": [
                {
                    "route": {"text": "oral"},
                    "doseAndRate": [
                        {
                            "doseQuantity": {
                                "value": meq,
                                "unit": "mEq"
                            }
                        }
                    ]
                }
            ],
            "status": "active",
            "intent": "order",
            "subject": {"reference": patient_id}
        }
        posts.append((f"{base}/MedicationRequest", medication_request))

        service_request = {
            "resourceType": "ServiceRequest",
            "code": {
                "coding": [
                    {
                        "system": "http://loinc.org",
                        "code": "2823-3",
                        "display": "Potassium [Moles/volume] in Serum or Plasma"
                    }
                ]
            },
            "authoredOn": now,
            "status": "active",
            "intent": "order",
            "priority": "stat",
            "subject": {"reference": patient_id},
            "occurrenceDateTime": next_day_8am,
            "note": {"text": "Morning serum potassium level"}
        }
        posts.append((f"{base}/ServiceRequest", service_request))

        answer += (
            f"It is low. Ordered {meq} mEq oral potassium replacement and a "
            f"morning serum potassium level for {next_day_8am}."
        )
    else:
        answer += "It is not low; no replacement potassium order was placed."

    return posts, [answer]
