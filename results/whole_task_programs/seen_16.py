# Written by deepseek/deepseek-v4.1-flash-1017, condition "seen": blind_16.py after one look at the server's responses on a made-up chart, seed 1016, temperature 1.0. Unedited.
def run_task(get, api_base, mrn):
    import json
    import math
    from urllib.parse import urlencode

    base = api_base.rstrip('/')
    NOW = "2023-11-13T10:15:00+00:00"
    NEXT_8AM = "2023-11-14T08:00:00+00:00"

    def get_json(url):
        try:
            return json.loads(get(url))
        except Exception:
            return None

    def build_url(path, params=None):
        url = base + path
        if params:
            url += '?' + urlencode(params)
        return url

    # Resolve patient identifier -> FHIR patient ID
    pid = mrn
    patient_bundle = get_json(build_url('/Patient', {'identifier': mrn}))
    if isinstance(patient_bundle, dict):
        entries = patient_bundle.get('entry', []) or []
        if entries:
            pid = entries[0].get('resource', {}).get('id', mrn)

    patient_ref = "Patient/" + str(pid)

    def fetch_all(url):
        """Follow pagination links and collect all resources."""
        resources = []
        seen = set()
        while url and url not in seen:
            seen.add(url)
            body = get_json(url)
            if not isinstance(body, dict):
                break
            for entry in body.get('entry', []) or []:
                resources.append(entry.get('resource', {}))
            next_url = None
            for link in body.get('link', []) or []:
                if link.get('relation') == 'next':
                    next_url = link.get('url')
                    break
            url = next_url
        return resources

    def collect_potassium(patient_param):
        results = []
        for code in ('K', '2823-3'):
            url = build_url('/Observation', {'code': code, 'patient': patient_param})
            for resource in fetch_all(url):
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
                        codes = [c.get('code') for c in
                                 (component.get('code', {}).get('coding', []) or [])]
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

    candidates = collect_potassium(patient_ref)
    if not candidates and str(pid) != patient_ref:
        candidates = collect_potassium(str(pid))

    if not candidates:
        return [], ["No potassium level found; no orders placed."]

    latest_dt, latest_value = max(candidates, key=lambda x: x[0])
    posts = []

    if latest_value < 3.5:
        deficit = round(3.5 - latest_value, 10)
        # For every 0.1 mEq/L below threshold -> 10 mEq oral repletion
        dose = int(math.ceil(deficit / 0.1) * 10)
        if dose < 10:
            dose = 10

        medication_request = {
            "resourceType": "MedicationRequest",
            "medicationCodeableConcept": {
                "coding": [{
                    "system": "http://hl7.org/fhir/sid/ndc",
                    "code": "40032-917-01",
                    "display": "Potassium Chloride 10 mEq oral tablet"
                }],
                "text": "Potassium Chloride 10 mEq oral tablet"
            },
            "authoredOn": NOW,
            "dosageInstruction": [{
                "route": {"text": "oral"},
                "doseAndRate": [{
                    "doseQuantity": {"value": dose, "unit": "mEq"}
                }]
            }],
            "status": "active",
            "intent": "order",
            "subject": {"reference": patient_ref}
        }

        service_request = {
            "resourceType": "ServiceRequest",
            "code": {
                "coding": [{
                    "system": "http://loinc.org",
                    "code": "2823-3",
                    "display": "Potassium [Moles/volume] in Serum or Plasma"
                }]
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
            f"Most recent potassium {latest_value:g} mmol/L (effective {latest_dt}); "
            f"ordered {dose} mEq oral potassium repletion and a morning serum "
            f"potassium draw at {NEXT_8AM}."
        ]
    else:
        answers = [
            f"Most recent potassium {latest_value:g} mmol/L (effective {latest_dt}); "
            f"no replacement potassium ordered."
        ]

    return posts, answers
