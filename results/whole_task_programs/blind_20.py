# Written by deepseek/deepseek-v4.1-flash-1017, condition "blind", seed 20, temperature 1.0. Unedited.
def run_task(get, api_base, mrn):
    import json
    import math
    import datetime
    from urllib.parse import quote

    base = api_base.rstrip("/")

    def load_json(text):
        try:
            return json.loads(text)
        except Exception:
            return None

    def parse_dt(value):
        if not value:
            return None
        try:
            s = str(value).replace("Z", "+00:00")
            dt = datetime.datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            return dt
        except Exception:
            return None

    def extract_value(resource):
        if not isinstance(resource, dict):
            return None

        q = resource.get("valueQuantity")
        if isinstance(q, dict) and q.get("value") is not None:
            try:
                return float(q["value"])
            except Exception:
                pass

        if resource.get("valueString") is not None:
            try:
                return float(str(resource["valueString"]).strip())
            except Exception:
                pass

        for comp in resource.get("component", []) or []:
            if not isinstance(comp, dict):
                continue
            q = comp.get("valueQuantity")
            if isinstance(q, dict) and q.get("value") is not None:
                try:
                    return float(q["value"])
                except Exception:
                    pass

        return None

    def extract_dt(resource):
        if not isinstance(resource, dict):
            return None

        for key in ("effectiveDateTime", "effectiveInstant", "issued"):
            dt = parse_dt(resource.get(key))
            if dt is not None:
                return dt

        period = resource.get("effectivePeriod")
        if isinstance(period, dict):
            for key in ("start", "end"):
                dt = parse_dt(period.get(key))
                if dt is not None:
                    return dt

        return None

    # Resolve MRN identifier to a Patient FHIR id.
    patient_id = str(mrn)
    patient_url = f"{base}/Patient?identifier={quote(str(mrn), safe='')}"
    patient_bundle = load_json(get(patient_url))

    if isinstance(patient_bundle, dict):
        if patient_bundle.get("resourceType") == "Patient" and patient_bundle.get("id"):
            patient_id = str(patient_bundle["id"])
        else:
            for entry in patient_bundle.get("entry", []) or []:
                if not isinstance(entry, dict):
                    continue
                res = entry.get("resource")
                if isinstance(res, dict) and res.get("resourceType") == "Patient" and res.get("id"):
                    patient_id = str(res["id"])
                    break

    if patient_id.startswith("Patient/"):
        patient_id = patient_id.split("/", 1)[1]

    patient_ref = f"Patient/{patient_id}"

    # Get most recent potassium level. The lab code for potassium is "K".
    obs_url = f"{base}/Observation?code=K&patient={quote(patient_ref, safe='')}"
    obs_bundle = load_json(get(obs_url))

    level = None
    if isinstance(obs_bundle, dict):
        candidates = []
        for entry in obs_bundle.get("entry", []) or []:
            if not isinstance(entry, dict):
                continue
            res = entry.get("resource")
            if not isinstance(res, dict) or res.get("resourceType") != "Observation":
                continue

            code_obj = res.get("code", {}) or {}
            codes = []
            for coding in code_obj.get("coding", []) or []:
                if isinstance(coding, dict) and coding.get("code") is not None:
                    codes.append(str(coding["code"]))

            text = str(code_obj.get("text", "")).lower()
            if codes and not any(c in ("K", "2823-3") for c in codes) and "potassium" not in text:
                continue

            value = extract_value(res)
            if value is None:
                continue

            dt = extract_dt(res)
            if dt is None:
                dt = datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)

            candidates.append((dt, value))

        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            level = candidates[0][1]

    now = datetime.datetime.fromisoformat("2023-11-13T10:15:00+00:00")
    authored_iso = now.isoformat()
    next_day_8am = (now + datetime.timedelta(days=1)).replace(
        hour=8, minute=0, second=0, microsecond=0
    )
    next_day_iso = next_day_8am.isoformat()

    if level is None:
        return [], ["No potassium level found."]

    if level >= 3.5:
        return [], [
            f"Most recent potassium level: {level:g} mEq/L (not low). "
            "No replacement potassium ordered."
        ]

    deficit = 3.5 - level
    increments = math.ceil(round(deficit / 0.1, 10))
    if increments < 1:
        increments = 1
    dose_mEq = increments * 10

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
            "text": "Potassium replacement oral"
        },
        "authoredOn": authored_iso,
        "dosageInstruction": [
            {
                "route": {"text": "Oral"},
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
        "subject": {"reference": patient_ref}
    }

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
        "authoredOn": authored_iso,
        "status": "active",
        "intent": "order",
        "priority": "stat",
        "subject": {"reference": patient_ref},
        "occurrenceDateTime": next_day_iso,
        "note": {"text": "Morning serum potassium level; paired with potassium replacement order."}
    }

    posts = [
        (f"{base}/MedicationRequest", medication_request),
        (f"{base}/ServiceRequest", service_request)
    ]

    answers = [
        f"Most recent potassium level: {level:g} mEq/L (low). "
        f"Ordered {dose_mEq} mEq oral potassium replacement and morning serum "
        f"potassium level for {next_day_iso}."
    ]

    return posts, answers
