# Written by deepseek/deepseek-v4.1-flash-1017, condition "blind", seed 16, temperature 1.0. Unedited.
def run_task(get, api_base, mrn):
    import json
    import math
    from urllib.parse import urlencode

    base = api_base.rstrip('/')
    NOW = "2023-11-13T10:15:00+00:00"
    NEXT_8AM = "2023-11-14T08:00:00+00:00"

    def get_json(path, params=None):
        url = base + path
        if params:
            url += '?' + urlencode(params)
        try:
            return url, json.loads(get(url))
        except Exception:
            return url, None

    # Resolve patient identifier to FHIR patient ID.
    pid = mrn
    _, patient_bundle = get_json('/Patient', {'identifier': mrn})
    if isinstance(patient_bundle, dict):
        entries = patient_bundle.get('entry', [])
        if entries:
            pid = entries[0].get('resource', {}).get('id', mrn)

    patient_ref = "Patient/" + str(pid)

    def collect_potassium(patient_param, code):
        _, bundle = get_json('/Observation', {'code': code, 'patient': patient_param})
        results = []
        if not isinstance(bundle, dict):
            return results

        for entry in bundle.get('entry', []):
            resource = entry.get('resource', {})
            dt = resource.get('effectiveDateTime') or resource.get('issued') or ''
            value = None

            vq = resource.get('valueQuantity')
            if isinstance(vq, dict) and vq.get('value') is not None:
                try:
                    value = float(vq.get('value'))
                except Exception:
                    value = None

            if value is None:
                for component in resource.get('component', []) or []:
                    codes = []
                    for coding in component.get('code', {}).get('coding', []) or []:
                        codes.append(coding.get('code'))
                    if 'K' in codes or '2823-3' in codes:
                        cvq = component.get('valueQuantity')
                        if isinstance(cvq, dict) and cvq.get('value') is not None:
                            try:
                                value = float(cvq.get('value'))
                                break
                            except Exception:
                                pass

            if value is not None:
                results.append((dt, value))

        return results

    candidates = collect_potassium(patient_ref, 'K')
    if not candidates and str(pid) != patient_ref:
        candidates = collect_potassium(str(pid), 'K')
    if not candidates:
        candidates = collect_potassium(patient_ref, '2823-3')
    if not candidates and str(pid) != patient_ref:
        candidates = collect_potassium(str(pid), '2823-3')

    if not candidates:
        return [], ["No potassium level found; no orders placed."]

    latest_dt, latest_value = max(candidates, key=lambda x: x[0])
    posts = []

    if latest_value < 3.5:
        deficit = 3.5 - latest_value
        dose = int(math.ceil((deficit / 0.1) - 1e-9) * 10)
        if dose < 10:
            dose = 10

        medication_request = {
            "resourceType": "MedicationRequest",
            "medicationCodeableConcept": {
                "coding": [
                    {
                        "system": "http://hl7.org/fhir/sid/ndc",
                        "code": "40032-917-01",
                        "display": "Potassium Chloride 10 mEq oral tablet"
                    }
                ],
                "text": "Potassium Chloride 10 mEq oral tablet"
            },
            "authoredOn": NOW,
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
            "authoredOn": NOW,
            "status": "active",
            "intent": "order",
            "priority": "stat",
            "subject": {"reference": patient_ref},
            "occurrenceDateTime": NEXT_8AM
        }

        posts.append((base + '/MedicationRequest', medication_request))
        posts.append((base + '/ServiceRequest', service_request))

        answers = [
            f"Most recent potassium {latest_value:g} mmol/L; ordered {dose} mEq oral potassium replacement and morning serum potassium at {NEXT_8AM}."
        ]
    else:
        answers = [
            f"Most recent potassium {latest_value:g} mmol/L; no replacement potassium ordered."
        ]

    return posts, answers
