# Written by deepseek/deepseek-v4.1-flash-1017, condition "seen": blind_14.py after one look at the server's responses on a made-up chart, seed 1014, temperature 1.0. Unedited.
def run_task(get, api_base, mrn):
    import json
    import math
    from urllib.parse import urlencode
    from datetime import datetime, timedelta

    base = api_base.rstrip('/')

    def _json(text):
        try:
            return json.loads(text)
        except Exception:
            return {}

    # Resolve patient FHIR ID from MRN identifier.
    patient_url = f"{base}/Patient?" + urlencode({"identifier": mrn})
    patient_bundle = _json(get(patient_url))
    pid = mrn
    entries = patient_bundle.get("entry") or []
    if entries:
        pid = (entries[0].get("resource") or {}).get("id") or mrn

    target_codes = {"K", "2823-3"}

    def matches_potassium_code(code_obj):
        if not isinstance(code_obj, dict):
            return False
        if "potassium" in (code_obj.get("text") or "").lower():
            return True
        for coding in code_obj.get("coding") or []:
            if not isinstance(coding, dict):
                continue
            if coding.get("code") in target_codes:
                return True
            if "potassium" in (coding.get("display") or "").lower():
                return True
        return False

    def get_value(obj):
        vq = obj.get("valueQuantity")
        if isinstance(vq, dict) and "value" in vq:
            return vq.get("value")
        if "valueString" in obj:
            return obj.get("valueString")
        if "value" in obj:
            return obj.get("value")
        return None

    def fetch_all_observations(code):
        """Fetch all observations for a code, following 'next' pagination links."""
        url = f"{base}/Observation?" + urlencode({"code": code, "patient": pid})
        all_entries = []
        seen_urls = set()
        while url and url not in seen_urls:
            seen_urls.add(url)
            bundle = _json(get(url))
            all_entries.extend(bundle.get("entry") or [])
            next_url = None
            for link in bundle.get("link") or []:
                if link.get("relation") == "next":
                    next_url = link.get("url")
                    break
            url = next_url
        return all_entries

    def collect_potassium_values(entries):
        values = []
        for idx, entry in enumerate(entries):
            res = entry.get("resource") or {}
            date = (
                res.get("effectiveDateTime")
                or res.get("issued")
                or ((res.get("meta") or {}).get("lastUpdated"))
                or ""
            )
            found = []
            for comp in res.get("component") or []:
                if matches_potassium_code(comp.get("code") or {}):
                    v = get_value(comp)
                    if v is not None:
                        found.append(v)
            if not found and matches_potassium_code(res.get("code") or {}):
                v = get_value(res)
                if v is not None:
                    found.append(v)
            for v in found:
                values.append((date, idx, v))
        return values

    raw_values = collect_potassium_values(fetch_all_observations("K"))
    if not raw_values:
        raw_values = collect_potassium_values(fetch_all_observations("2823-3"))

    potassium_values = []
    for date, idx, value in raw_values:
        try:
            potassium_values.append((date, idx, float(value)))
        except Exception:
            pass

    if not potassium_values:
        return [], [f"No serum potassium level found for patient {mrn}; no order placed."]

    # Latest by effective date (stable tiebreak by original index).
    potassium_values.sort(key=lambda x: (x[0] or "", x[1]))
    k = potassium_values[-1][2]

    now_str = "2023-11-13T10:15:00+00:00"
    now_dt = datetime.fromisoformat(now_str)
    next_morning = (now_dt + timedelta(days=1)).replace(
        hour=8, minute=0, second=0, microsecond=0
    ).isoformat()

    posts = []

    if k < 3.5:
        # For every 0.1 mEq/L below 3.5, order 10 mEq oral potassium.
        steps = math.ceil(((3.5 - k) / 0.1) - 1e-9)
        dose = int(steps * 10)

        medication_request = {
            "resourceType": "MedicationRequest",
            "medicationCodeableConcept": {
                "coding": [
                    {
                        "system": "http://hl7.org/fhir/sid/ndc",
                        "code": "40032-917-01",
                        "display": "Potassium chloride oral replacement"
                    }
                ],
                "text": "Potassium chloride oral replacement"
            },
            "authoredOn": now_str,
            "dosageInstruction": [
                {
                    "route": {"text": "Oral"},
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
            "subject": {"reference": f"Patient/{pid}"}
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
            "authoredOn": now_str,
            "status": "active",
            "intent": "order",
            "priority": "stat",
            "subject": {"reference": f"Patient/{pid}"},
            "note": {
                "text": "Morning serum potassium level paired with potassium replacement order"
            },
            "occurrenceDateTime": next_morning
        }

        posts.append((f"{base}/MedicationRequest", medication_request))
        posts.append((f"{base}/ServiceRequest", service_request))

        answers = [
            f"Patient {mrn}: most recent potassium was {k:g} mEq/L, which is low. "
            f"Ordered {dose} mEq oral potassium replacement (NDC 40032-917-01) "
            f"and a morning serum potassium level for {next_morning}."
        ]
    else:
        answers = [
            f"Patient {mrn}: most recent potassium was {k:g} mEq/L, which is not low. "
            f"No replacement potassium or lab order placed."
        ]

    return posts, answers
