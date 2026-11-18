# Written by deepseek/deepseek-v4.1-flash-1017, condition "blind", seed 6, temperature 1.0. Unedited.
def run_task(get, api_base, mrn):
    """Check the most recent potassium level; if low, order oral potassium
    replacement and a next-morning serum potassium level."""
    import json
    import re
    from decimal import Decimal, ROUND_CEILING
    from urllib.parse import urlencode

    base = api_base.rstrip("/")
    patient_ref = str(mrn)
    if not patient_ref.startswith("Patient/"):
        patient_ref = "Patient/" + patient_ref

    def fetch_observations(code):
        url = f"{base}/Observation?{urlencode({'patient': mrn, 'code': code})}"
        raw = get(url)
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def resource_of(entry):
        if isinstance(entry, dict) and "resource" in entry:
            return entry["resource"]
        return entry

    def numeric_value(obs):
        obs = resource_of(obs)
        if not isinstance(obs, dict):
            return None

        vq = obs.get("valueQuantity")
        if isinstance(vq, dict) and vq.get("value") is not None:
            try:
                return Decimal(str(vq["value"]))
            except Exception:
                pass

        vs = obs.get("valueString")
        if vs is not None:
            m = re.search(r"-?\d+(?:\.\d+)?", str(vs))
            if m:
                try:
                    return Decimal(m.group(0))
                except Exception:
                    pass

        for comp in obs.get("component", []) or []:
            if isinstance(comp, dict):
                cvq = comp.get("valueQuantity")
                if isinstance(cvq, dict) and cvq.get("value") is not None:
                    try:
                        return Decimal(str(cvq["value"]))
                    except Exception:
                        pass
        return None

    def observation_time(obs):
        obs = resource_of(obs)
        if not isinstance(obs, dict):
            return ""
        return (
            obs.get("effectiveDateTime")
            or obs.get("issued")
            or (obs.get("meta") or {}).get("lastUpdated")
            or ""
        )

    # The lab search parameter uses the potassium base name "K".
    bundle = fetch_observations("K")
    entries = bundle.get("entry", []) if isinstance(bundle, dict) else []

    # Fallback to LOINC if the base-name search returns nothing.
    if not entries:
        bundle = fetch_observations("2823-3")
        entries = bundle.get("entry", []) if isinstance(bundle, dict) else []

    best_value = None
    best_time = ""
    for entry in entries:
        value = numeric_value(entry)
        if value is None:
            continue
        t = observation_time(entry)
        if best_value is None or t > best_time:
            best_value = value
            best_time = t

    posts = []
    answers = []

    if best_value is None:
        answers.append("No recent serum potassium level was found; no orders placed.")
        return posts, answers

    answers.append(f"Most recent serum potassium level: {best_value} mEq/L.")

    threshold = Decimal("3.5")
    if best_value < threshold:
        deficit = threshold - best_value
        # For every 0.1 mEq/L below goal, order 10 mEq oral potassium.
        steps = (deficit / Decimal("0.1")).to_integral_value(rounding=ROUND_CEILING)
        dose_mEq = int(steps) * 10

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
            "authoredOn": "2023-11-13T10:15:00+00:00",
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
            "subject": {"reference": patient_ref}
        }

        service_request = {
            "resourceType": "ServiceRequest",
            "code": {
                "coding": [
                    {
                        "system": "http://loinc.org",
                        "code": "2823-3",
                        "display": "Potassium [Mass/volume] in Serum or Plasma"
                    }
                ]
            },
            "authoredOn": "2023-11-13T10:15:00+00:00",
            "status": "active",
            "intent": "order",
            "priority": "stat",
            "subject": {"reference": patient_ref},
            "occurrenceDateTime": "2023-11-14T08:00:00+00:00"
        }

        posts.append((f"{base}/MedicationRequest", medication_request))
        posts.append((f"{base}/ServiceRequest", service_request))

        answers.append(
            f"Ordered {dose_mEq} mEq oral potassium replacement and a morning "
            f"serum potassium level for 2023-11-14 at 08:00."
        )
    else:
        answers.append("Potassium level is not low; no replacement or lab order placed.")

    return posts, answers
