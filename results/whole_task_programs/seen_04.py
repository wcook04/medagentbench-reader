# Written by deepseek/deepseek-v4.1-flash-1017, condition "seen": blind_04.py after one look at the server's responses on a made-up chart, seed 1004, temperature 1.0. Unedited.
import json
import math
import urllib.parse
from datetime import datetime


def run_task(get, api_base, mrn):
    base = api_base.rstrip("/")
    now = "2023-11-13T10:15:00+00:00"
    next_morning = "2023-11-14T08:00:00+00:00"

    def make_url(path, params=None):
        url = base + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        return url

    def parse_bundle(text):
        try:
            data = json.loads(text)
        except Exception:
            return [], {}
        entries = []
        if isinstance(data, dict):
            if data.get("resourceType") == "Bundle":
                for entry in data.get("entry", []) or []:
                    if isinstance(entry, dict) and isinstance(entry.get("resource"), dict):
                        entries.append(entry["resource"])
            elif data.get("resourceType"):
                entries.append(data)
        return entries, data if isinstance(data, dict) else {}

    def fetch_all(url):
        all_res = []
        seen = set()
        while url and url not in seen:
            seen.add(url)
            text = get(url)
            entries, data = parse_bundle(text)
            all_res.extend(entries)
            nxt = None
            for link in data.get("link", []) or []:
                if isinstance(link, dict) and link.get("relation") == "next":
                    nxt = link.get("url")
                    break
            url = nxt
        return all_res

    def parse_dt(s):
        if not s:
            return None
        try:
            return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        except Exception:
            return None

    def obs_value(obs):
        vq = obs.get("valueQuantity")
        if isinstance(vq, dict) and vq.get("value") is not None:
            try:
                return float(vq["value"])
            except (TypeError, ValueError):
                pass
        vs = obs.get("valueString")
        if vs is not None:
            try:
                return float(vs)
            except (TypeError, ValueError):
                pass
        return None

    def obs_time(obs):
        return parse_dt(obs.get("effectiveDateTime")) or parse_dt(obs.get("issued"))

    # 1. Find the patient
    patient_entries = fetch_all(make_url("/Patient", {"identifier": mrn}))
    patients = [r for r in patient_entries if r.get("resourceType") == "Patient"]
    if not patients:
        return ([], [f"No patient found for identifier {mrn}."])
    patient_id = patients[0].get("id")
    if not patient_id:
        return ([], [f"No patient id found for identifier {mrn}."])
    patient_id = str(patient_id)

    # 2. Fetch potassium observations, following pagination, trying both codes.
    observations = []
    for code in ("K", "2823-3"):
        obs = fetch_all(make_url("/Observation", {"patient": patient_id, "code": code}))
        observations.extend([o for o in obs if o.get("resourceType") == "Observation"])

    # Deduplicate by id
    seen_ids = set()
    uniq = []
    for o in observations:
        oid = o.get("id")
        if oid:
            if oid in seen_ids:
                continue
            seen_ids.add(oid)
        uniq.append(o)
    observations = uniq

    # 3. Find the most recent observation with a numeric value
    best_value = None
    best_time = None
    for obs in observations:
        v = obs_value(obs)
        t = obs_time(obs)
        if v is None or t is None:
            continue
        if best_time is None or t > best_time:
            best_time = t
            best_value = v

    if best_value is None:
        return ([], ["No potassium level found."])

    potassium = best_value

    if potassium >= 3.5:
        return (
            [],
            [f"Most recent potassium level is {potassium:g} mEq/L; no replacement ordered."]
        )

    # 4. Compute dose: for every 0.1 mEq/L below 3.5, 10 mEq oral potassium.
    deficit = 3.5 - potassium
    increments = math.ceil(round(deficit / 0.1, 6))
    dose = int(increments * 10)

    patient_ref = (
        patient_id if patient_id.startswith("Patient/") else f"Patient/{patient_id}"
    )

    medication_payload = {
        "resourceType": "MedicationRequest",
        "medicationCodeableConcept": {
            "coding": [
                {
                    "system": "http://hl7.org/fhir/sid/ndc",
                    "code": "40032-917-01",
                    "display": "Potassium replacement",
                }
            ],
            "text": "Potassium replacement",
        },
        "authoredOn": now,
        "dosageInstruction": [
            {
                "route": {"text": "oral"},
                "doseAndRate": [
                    {
                        "doseQuantity": {
                            "value": dose,
                            "unit": "mEq",
                        }
                    }
                ],
            }
        ],
        "status": "active",
        "intent": "order",
        "subject": {"reference": patient_ref},
    }

    service_request_payload = {
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
        "subject": {"reference": patient_ref},
        "occurrenceDateTime": next_morning,
        "note": {"text": "Morning serum potassium paired with potassium replacement order."},
    }

    posts = [
        (base + "/MedicationRequest", medication_payload),
        (base + "/ServiceRequest", service_request_payload),
    ]

    answers = [
        f"Most recent potassium level: {potassium:g} mEq/L.",
        f"Ordered potassium replacement: {dose} mEq oral (NDC 40032-917-01).",
        "Ordered morning serum potassium level (LOINC 2823-3) for 2023-11-14T08:00:00+00:00.",
    ]

    return posts, answers
