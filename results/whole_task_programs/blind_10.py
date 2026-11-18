# Written by deepseek/deepseek-v4.1-flash-1017, condition "blind", seed 10, temperature 1.0. Unedited.
def run_task(get, api_base, mrn):
    import json
    import math
    import re
    from urllib.parse import urlencode

    now = "2023-11-13T10:15:00+00:00"
    next_morning = "2023-11-14T08:00:00+00:00"

    # Look up the most recent potassium lab.
    obs_url = f"{api_base}/Observation?" + urlencode({
        "patient": mrn,
        "code": "K"
    })

    raw = get(obs_url)

    try:
        data = json.loads(raw)
    except Exception:
        data = {}

    if isinstance(data, list):
        entries = data
    elif isinstance(data, dict):
        if data.get("resourceType") == "Observation":
            entries = [data]
        else:
            entries = data.get("entry", [])
    else:
        entries = []

    best = None

    for entry in entries:
        if not isinstance(entry, dict):
            continue

        res = entry.get("resource", entry)
        if not isinstance(res, dict):
            continue

        if res.get("resourceType") not in (None, "Observation"):
            continue

        value = None
        vq = res.get("valueQuantity")
        if isinstance(vq, dict):
            value = vq.get("value")

        if value is None and "valueString" in res:
            match = re.search(r"-?\d+(?:\.\d+)?", str(res["valueString"]))
            if match:
                value = match.group()

        if value is None:
            continue

        try:
            value = float(value)
        except Exception:
            continue

        dt = res.get("effectiveDateTime") or res.get("issued")
        if not dt and isinstance(res.get("effectivePeriod"), dict):
            dt = res["effectivePeriod"].get("start")

        if best is None or (dt or "") > (best[0] or ""):
            best = (dt, value, res)

    if best is None:
        return [], [f"No potassium level found for patient {mrn}."]

    dt, level, _ = best
    posts = []
    answers = [
        f"Most recent potassium level: {level} mEq/L"
        + (f" on {dt}" if dt else "")
        + "."
    ]

    if level < 3.5:
        deficit = 3.5 - level
        dose = int(math.ceil(deficit / 0.1 - 1e-9) * 10)
        if dose < 10:
            dose = 10

        med_payload = {
            "resourceType": "MedicationRequest",
            "medicationCodeableConcept": {
                "coding": [
                    {
                        "system": "http://hl7.org/fhir/sid/ndc",
                        "code": "40032-917-01",
                        "display": "Potassium oral replacement"
                    }
                ],
                "text": "Potassium oral replacement"
            },
            "authoredOn": now,
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
            "subject": {"reference": mrn}
        }

        sr_payload = {
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
            "authoredOn": now,
            "status": "active",
            "intent": "order",
            "priority": "stat",
            "subject": {"reference": mrn},
            "occurrenceDateTime": next_morning,
            "note": {"text": "Morning serum potassium level"}
        }

        posts.append((f"{api_base}/MedicationRequest", med_payload))
        posts.append((f"{api_base}/ServiceRequest", sr_payload))

        answers.append(
            f"Potassium is low; ordered {dose} mEq oral potassium replacement "
            "(NDC 40032-917-01)."
        )
        answers.append(
            f"Ordered morning serum potassium level (LOINC 2823-3) for {next_morning}."
        )
    else:
        answers.append("Potassium is not low; no replacement potassium ordered.")

    return posts, answers
