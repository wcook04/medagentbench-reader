# Written by deepseek/deepseek-v4.1-flash-1017, condition "blind", seed 7, temperature 1.0. Unedited.
import json
import math
from urllib.parse import urlencode


def run_task(get, api_base, mrn):
    base = api_base.rstrip("/")

    def parse_response(text):
        if isinstance(text, (dict, list)):
            return text
        try:
            return json.loads(text)
        except Exception:
            return None

    # Find the patient's FHIR ID from the MRN identifier.
    patient_url = base + "/Patient?" + urlencode({"identifier": mrn})
    patient_resp = parse_response(get(patient_url))
    patient_id = None

    if isinstance(patient_resp, dict):
        if patient_resp.get("resourceType") == "Patient":
            patient_id = patient_resp.get("id")
        else:
            for entry in patient_resp.get("entry", []) or []:
                resource = entry.get("resource", {})
                if resource.get("resourceType") == "Patient":
                    patient_id = resource.get("id")
                    break

    if not patient_id:
        patient_id = mrn

    def get_observations(code):
        obs_url = base + "/Observation?" + urlencode({
            "patient": patient_id,
            "code": code,
        })
        obs_resp = parse_response(get(obs_url))
        observations = []
        if isinstance(obs_resp, dict):
            if obs_resp.get("resourceType") == "Observation":
                observations = [obs_resp]
            else:
                for entry in obs_resp.get("entry", []) or []:
                    resource = entry.get("resource", {})
                    if resource.get("resourceType") == "Observation":
                        observations.append(resource)
        return observations

    def code_strings(code_obj):
        values = set()
        if not isinstance(code_obj, dict):
            return values
        for coding in code_obj.get("coding", []) or []:
            if isinstance(coding, dict):
                if coding.get("code") is not None:
                    values.add(str(coding.get("code")))
                if coding.get("display") is not None:
                    values.add(str(coding.get("display")).lower())
        if code_obj.get("text") is not None:
            values.add(str(code_obj.get("text")).lower())
        return values

    def extract_potassium_value(resource):
        value = None

        # Most lab observations have a top-level valueQuantity.
        quantity = resource.get("valueQuantity")
        if isinstance(quantity, dict) and quantity.get("value") is not None:
            value = quantity.get("value")

        if value is None and resource.get("value") is not None:
            value = resource.get("value")

        if value is None and resource.get("valueString") is not None:
            try:
                value = float(resource.get("valueString"))
            except Exception:
                pass

        # Some lab results return component-level data.
        if value is None:
            for component in resource.get("component", []) or []:
                comp_codes = code_strings(component.get("code", {}))
                is_potassium = (
                    "K" in comp_codes
                    or "2823-3" in comp_codes
                    or any("potassium" in c for c in comp_codes)
                )
                if not is_potassium:
                    continue

                comp_qty = component.get("valueQuantity")
                if isinstance(comp_qty, dict) and comp_qty.get("value") is not None:
                    value = comp_qty.get("value")
                    break

                if component.get("value") is not None:
                    value = component.get("value")
                    break

                if component.get("valueString") is not None:
                    try:
                        value = float(component.get("valueString"))
                        break
                    except Exception:
                        pass

        try:
            return float(value)
        except Exception:
            return None

    # Search by the potassium base name first; fall back to the LOINC code if needed.
    observations = get_observations("K")
    dated_values = []

    for obs in observations:
        val = extract_potassium_value(obs)
        if val is None:
            continue
        dt = obs.get("effectiveDateTime") or obs.get("issued") or ""
        dated_values.append((dt, val, obs))

    if not dated_values:
        observations = get_observations("2823-3")
        for obs in observations:
            val = extract_potassium_value(obs)
            if val is None:
                continue
            dt = obs.get("effectiveDateTime") or obs.get("issued") or ""
            dated_values.append((dt, val, obs))

    if not dated_values:
        return [], [f"No potassium level found for patient identifier {mrn}."]

    dated_values.sort(key=lambda item: item[0], reverse=True)
    latest_dt, potassium, latest_obs = dated_values[0]

    threshold = 3.5
    if potassium >= threshold:
        return [], [
            f"Most recent potassium level is {potassium:g} mEq/L on {latest_dt}; "
            f"no potassium replacement ordered."
        ]

    deficit = threshold - potassium
    increments = int(math.ceil((deficit / 0.1) - 1e-9))
    dose_mEq = increments * 10

    now = "2023-11-13T10:15:00+00:00"
    next_day_morning = "2023-11-14T08:00:00+00:00"
    subject = {"reference": f"Patient/{patient_id}"}

    medication_request = {
        "resourceType": "MedicationRequest",
        "medicationCodeableConcept": {
            "coding": [
                {
                    "system": "http://hl7.org/fhir/sid/ndc",
                    "code": "40032-917-01",
                    "display": "Potassium chloride oral replacement",
                }
            ],
            "text": "Potassium chloride oral replacement",
        },
        "authoredOn": now,
        "dosageInstruction": [
            {
                "route": {"text": "Oral"},
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
        "subject": subject,
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
        "subject": subject,
        "note": {
            "text": "Morning serum potassium level to assess potassium repletion."
        },
        "occurrenceDateTime": next_day_morning,
    }

    posts = [
        (base + "/MedicationRequest", medication_request),
        (base + "/ServiceRequest", service_request),
    ]

    answers = [
        f"Most recent potassium level is {potassium:g} mEq/L on {latest_dt}.",
        f"Ordered {dose_mEq} mEq oral potassium replacement.",
        f"Scheduled morning serum potassium level for {next_day_morning}.",
    ]

    return posts, answers
