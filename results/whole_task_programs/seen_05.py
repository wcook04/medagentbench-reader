# Written by deepseek/deepseek-v4.1-flash-1017, condition "seen": blind_05.py after one look at the server's responses on a made-up chart, seed 1005, temperature 1.0. Unedited.
def run_task(get, api_base, mrn):
    import json
    import math
    from urllib.parse import urlencode

    base = api_base.rstrip("/")

    def get_json(url):
        try:
            return json.loads(get(url))
        except Exception:
            return None

    def collect_entries(bundle):
        """Collect all entries across pages, following `next` links."""
        entries = []
        pages = 0
        while bundle and pages < 30:
            for e in bundle.get("entry") or []:
                entries.append(e)
            nxt = None
            for link in bundle.get("link") or []:
                if link.get("relation") == "next" and link.get("url"):
                    nxt = link["url"]
                    break
            if not nxt:
                break
            bundle = get_json(nxt)
            pages += 1
        return entries

    # 1. Resolve the patient FHIR ID from the MRN identifier.
    patient_url = f"{base}/Patient?{urlencode({'identifier': mrn})}"
    patient_bundle = get_json(patient_url)
    patient_id = None
    if patient_bundle:
        entries = patient_bundle.get("entry") or []
        if entries:
            patient_id = entries[0].get("resource", {}).get("id")
    if not patient_id:
        patient_id = mrn

    # 2. Retrieve all potassium lab results (follow pagination).
    obs_url = f"{base}/Observation?{urlencode({'patient': patient_id, 'code': 'K'})}"
    obs_bundle = get_json(obs_url)
    all_entries = collect_entries(obs_bundle)

    # 3. Find the most recent potassium value.
    latest_val = None
    latest_date = ""
    for entry in all_entries:
        resource = entry.get("resource", entry)
        value = None

        q = resource.get("valueQuantity")
        if isinstance(q, dict) and "value" in q:
            try:
                value = float(q["value"])
            except Exception:
                pass
        if value is None and "valueString" in resource:
            try:
                value = float(resource["valueString"])
            except Exception:
                pass
        if value is None and "value" in resource:
            try:
                value = float(resource["value"])
            except Exception:
                pass
        if value is None:
            continue

        date = resource.get("effectiveDateTime") or resource.get("issued") or ""
        if not date:
            period = resource.get("effectivePeriod")
            if isinstance(period, dict):
                date = period.get("start") or ""

        if latest_val is None or date > latest_date:
            latest_val = value
            latest_date = date

    if latest_val is None:
        return ([], ["No potassium level found for patient."])

    # 4. If potassium is not low (>= 3.5), no action needed.
    if latest_val >= 3.5:
        return (
            [],
            [f"Most recent potassium level is {latest_val:g} mEq/L, not low; no replacement ordered."]
        )

    # 5. Compute replacement dose: 10 mEq per 0.1 mEq/L below 3.5.
    deficit = round(3.5 - latest_val, 10)
    steps = int(math.ceil(deficit / 0.1 - 1e-9))
    dose = steps * 10

    authored_on = "2023-11-13T10:15:00+00:00"
    next_morning = "2023-11-14T08:00:00+00:00"
    subject = {"reference": f"Patient/{patient_id}"}

    # 6. MedicationRequest for oral potassium replacement.
    med_payload = {
        "resourceType": "MedicationRequest",
        "medicationCodeableConcept": {
            "coding": [
                {
                    "system": "http://hl7.org/fhir/sid/ndc",
                    "code": "40032-917-01",
                    "display": "Potassium replacement"
                }
            ],
            "text": "Potassium oral repletion"
        },
        "authoredOn": authored_on,
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
        "subject": subject
    }

    # 7. ServiceRequest for the following morning's potassium level (LOINC 2823-3).
    service_payload = {
        "resourceType": "ServiceRequest",
        "code": {
            "coding": [
                {
                    "system": "http://loinc.org",
                    "code": "2823-3",
                    "display": "Potassium [Moles/volume] in Serum or Plasma"
                }
            ],
            "text": "Serum potassium level"
        },
        "authoredOn": authored_on,
        "status": "active",
        "intent": "order",
        "priority": "stat",
        "subject": subject,
        "occurrenceDateTime": next_morning,
        "note": {
            "text": "Morning serum potassium level, paired with potassium replacement order"
        }
    }

    posts = [
        (f"{base}/MedicationRequest", med_payload),
        (f"{base}/ServiceRequest", service_payload)
    ]

    answers = [
        f"Most recent potassium is {latest_val:g} mEq/L. "
        f"Ordered {dose} mEq oral potassium replacement and a morning serum potassium "
        f"level for 2023-11-14T08:00:00+00:00."
    ]

    return (posts, answers)
