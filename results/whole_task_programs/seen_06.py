# Written by deepseek/deepseek-v4.1-flash-1017, condition "seen": blind_06.py after one look at the server's responses on a made-up chart, seed 1006, temperature 1.0. Unedited.
def run_task(get, api_base, mrn):
    """Check the most recent potassium level; if low, order oral potassium
    replacement and a next-morning serum potassium level."""
    import json
    from decimal import Decimal, ROUND_CEILING
    from urllib.parse import urlencode

    base = api_base.rstrip("/")
    patient_ref = str(mrn)
    if not patient_ref.startswith("Patient/"):
        patient_ref = "Patient/" + patient_ref

    def fetch_all(code):
        url = f"{base}/Observation?{urlencode({'patient': mrn, 'code': code})}"
        entries = []
        seen = set()
        while url and url not in seen:
            seen.add(url)
            try:
                bundle = json.loads(get(url))
            except Exception:
                break
            if not isinstance(bundle, dict):
                break
            for e in bundle.get("entry", []) or []:
                entries.append(e)
            next_url = None
            for link in bundle.get("link", []) or []:
                if isinstance(link, dict) and link.get("relation") == "next":
                    next_url = link.get("url")
                    break
            url = next_url
        return entries

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
            s = str(vs).strip()
            i = 0
            while i < len(s) and (s[i].isdigit() or s[i] in '.-+'):
                i += 1
            try:
                return Decimal(s[:i])
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

    entries = fetch_all("K")
    if not entries:
        entries = fetch_all("2823-3")

    best_value = None
    best_time = ""
    for entry in entries:
        v = numeric_value(entry)
        if v is None:
            continue
        t = observation_time(entry)
        if best_value is None or t > best_time:
            best_value = v
            best_time = t

    posts = []
    answers = []

    if best_value is None:
        answers.append("No serum potassium level found; no orders placed.")
        return posts, answers

    answers.append(
        f"Most recent serum potassium level: {best_value} mmol/L on {best_time}."
    )

    threshold = Decimal("3.5")
    if best_value < threshold:
        deficit = threshold - best_value
        steps = (deficit / Decimal("0.1")).to_integral_value(rounding=ROUND_CEILING)
        dose_mEq = int(steps) * 10

        medication_request = {
            "resourceType": "MedicationRequest",
            "medicationCodeableConcept": {
                "coding": [{
                    "system": "http://hl7.org/fhir/sid/ndc",
                    "code": "40032-917-01",
                    "display": "Potassium replacement"
                }],
                "text": "Potassium replacement oral"
            },
            "authoredOn": "2023-11-13T10:15:00+00:00",
            "dosageInstruction": [{
                "route": {"text": "oral"},
                "doseAndRate": [{
                    "doseQuantity": {"value": dose_mEq, "unit": "mEq"}
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
                    "display": "Potassium [Mass/volume] in Serum or Plasma"
                }]
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
            f"serum potassium level for 2023-11-14T08:00:00+00:00."
        )
    else:
        answers.append("Potassium level is not low; no orders placed.")

    return posts, answers
