# Written by deepseek/deepseek-v4.1-flash-1017, condition "seen": blind_13.py after one look at the server's responses on a made-up chart, seed 1013, temperature 1.0. Unedited.
def run_task(get, api_base, mrn):
    import json
    import math
    from urllib.parse import urlencode
    from datetime import datetime, timezone

    base = api_base.rstrip("/")

    # Resolve the patient identifier mrn to a FHIR Patient resource id when possible.
    patient_id = mrn
    try:
        patient_url = f"{base}/Patient?{urlencode({'identifier': mrn})}"
        patient_body = get(patient_url)
        patient_data = json.loads(patient_body)
        entries = patient_data.get("entry") or []
        if entries:
            resource = entries[0].get("resource") or {}
            patient_id = resource.get("id") or patient_id
    except Exception:
        pass

    # Retrieve potassium observations, following pagination links.
    observations = []
    for code in ("2823-3", "K"):
        try:
            url = f"{base}/Observation?{urlencode({'patient': patient_id, 'code': code})}"
            visited = set()
            while url and url not in visited:
                visited.add(url)
                body = get(url)
                data = json.loads(body)
                for entry in data.get("entry") or []:
                    resource = entry.get("resource") or {}
                    if resource.get("resourceType") == "Observation":
                        observations.append(resource)
                next_url = None
                for link in data.get("link") or []:
                    if link.get("relation") == "next" and link.get("url"):
                        next_url = link.get("url")
                        break
                url = next_url
        except Exception:
            pass

    # Deduplicate observations by id when available.
    seen = set()
    unique_observations = []
    for obs in observations:
        obs_id = obs.get("id")
        if obs_id:
            if obs_id in seen:
                continue
            seen.add(obs_id)
        unique_observations.append(obs)

    def parse_datetime(value):
        if not value or not isinstance(value, str):
            return None
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            try:
                dt = datetime.fromisoformat(value[:10])
                return dt.replace(tzinfo=timezone.utc)
            except Exception:
                return None

    def observation_value(obs):
        value_quantity = obs.get("valueQuantity")
        if isinstance(value_quantity, dict):
            value = value_quantity.get("value")
            if isinstance(value, (int, float)):
                return float(value)

        for key in ("valueDecimal", "valueInteger", "valueString"):
            value = obs.get(key)
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                try:
                    return float(value.strip())
                except Exception:
                    pass

        components = obs.get("component") or []
        for component in components:
            code = component.get("code") or {}
            code_text = json.dumps(code).lower()
            codings = code.get("coding") or []
            matches_potassium = (
                "2823-3" in code_text
                or '"k"' in code_text
                or "potassium" in code_text
            )
            for coding in codings:
                if str(coding.get("code", "")).upper() == "K":
                    matches_potassium = True
            if matches_potassium:
                component_quantity = component.get("valueQuantity") or {}
                value = component_quantity.get("value")
                if isinstance(value, (int, float)):
                    return float(value)

        for component in components:
            component_quantity = component.get("valueQuantity") or {}
            value = component_quantity.get("value")
            if isinstance(value, (int, float)):
                return float(value)

        return None

    def observation_datetime(obs):
        for key in ("effectiveDateTime", "issued", "valueDateTime"):
            parsed = parse_datetime(obs.get(key))
            if parsed is not None:
                return parsed

        effective_period = obs.get("effectivePeriod")
        if isinstance(effective_period, dict):
            parsed = parse_datetime(effective_period.get("start"))
            if parsed is not None:
                return parsed

        return None

    candidates = []
    for obs in unique_observations:
        value = observation_value(obs)
        if value is None:
            continue
        dt = observation_datetime(obs) or datetime.min.replace(tzinfo=timezone.utc)
        candidates.append((dt, value, obs))

    if not candidates:
        return [], ["No potassium level found for the patient."]

    candidates.sort(key=lambda item: item[0], reverse=True)
    most_recent_dt, potassium_level, _ = candidates[0]

    answers = [
        f"Most recent potassium level: {potassium_level} mmol/L "
        f"on {most_recent_dt.isoformat()}."
    ]

    posts = []

    if potassium_level < 3.5:
        deficit = 3.5 - potassium_level
        increments = max(1, math.ceil((deficit / 0.1) - 1e-9))
        dose_mEq = increments * 10

        authored_on = "2023-11-13T10:15:00+00:00"
        subject = {"reference": f"Patient/{patient_id}"}

        medication_request = {
            "resourceType": "MedicationRequest",
            "medicationCodeableConcept": {
                "coding": [
                    {
                        "system": "http://hl7.org/fhir/sid/ndc",
                        "code": "40032-917-01",
                        "display": "Potassium replacement"
                    }
                ],
                "text": "Potassium replacement oral"
            },
            "authoredOn": authored_on,
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
            "subject": subject
        }

        posts.append((f"{base}/MedicationRequest", medication_request))

        occurrence_datetime = "2023-11-14T08:00:00+00:00"
        service_request = {
            "resourceType": "ServiceRequest",
            "code": {
                "coding": [
                    {
                        "system": "http://loinc.org",
                        "code": "2823-3",
                        "display": "Serum potassium"
                    }
                ],
                "text": "Serum potassium level"
            },
            "authoredOn": authored_on,
            "status": "active",
            "intent": "order",
            "priority": "stat",
            "subject": subject,
            "occurrenceDateTime": occurrence_datetime,
            "note": {
                "text": "Morning serum potassium level paired with potassium replacement order."
            }
        }

        posts.append((f"{base}/ServiceRequest", service_request))

        answers.append(f"Ordered {dose_mEq} mEq oral potassium replacement.")
        answers.append(
            f"Ordered morning serum potassium level for {occurrence_datetime}."
        )
    else:
        answers.append(
            "Potassium level is not low; no potassium replacement or follow-up order placed."
        )

    return posts, answers
