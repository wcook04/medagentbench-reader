# Written by deepseek/deepseek-v4.1-flash-1017, condition "seen": blind_10.py after one look at the server's responses on a made-up chart, seed 1010, temperature 1.0. Unedited.
def run_task(get, api_base, mrn):
    import json
    import math
    import re

    now = "2023-11-13T10:15:00+00:00"
    next_morning = "2023-11-14T08:00:00+00:00"

    base = api_base.rstrip("/")

    def parse(raw):
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def entries_of(data):
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            if data.get("resourceType") == "Observation":
                return [data]
            return data.get("entry") or []
        return []

    def next_link(data):
        if not isinstance(data, dict):
            return None
        for link in data.get("link") or []:
            if link.get("relation") == "next" and link.get("url"):
                return link["url"]
        return None

    def consider(entries, best):
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
                m = re.search(r"-?\d+(?:\.\d+)?", str(res["valueString"]))
                if m:
                    value = m.group()
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
                best = (dt, value)
        return best

    url = f"{base}/Observation?patient={mrn}&code=K"
    raw = get(url)
    data = parse(raw)

    best = consider(entries_of(data), None)

    seen = set()
    nxt = next_link(data)
    while nxt and nxt not in seen and len(seen) < 10:
        seen.add(nxt)
        try:
            raw2 = get(nxt)
        except Exception:
            break
        data2 = parse(raw2)
        if not data2:
            break
        best = consider(entries_of(data2), best)
        nxt = next_link(data2)

    if best is None:
        return [], [f"No potassium level found for patient {mrn}."]

    dt, level = best
    posts = []
    answers = [
        f"Most recent potassium level: {level} mEq/L"
        + (f" on {dt}" if dt else "")
        + "."
    ]

    if level < 3.5:
        deficit = 3.5 - level
        steps = math.ceil(deficit / 0.1 - 1e-9)
        dose = max(10, steps * 10)

        med_payload = {
            "resourceType": "MedicationRequest",
            "medicationCodeableConcept": {
                "coding": [{
                    "system": "http://hl7.org/fhir/sid/ndc",
                    "code": "40032-917-01",
                    "display": "Potassium oral replacement"
                }],
                "text": "Potassium oral replacement"
            },
            "authoredOn": now,
            "dosageInstruction": [{
                "route": {"text": "oral"},
                "doseAndRate": [{
                    "doseQuantity": {"value": dose, "unit": "mEq"}
                }]
            }],
            "status": "active",
            "intent": "order",
            "subject": {"reference": mrn}
        }

        sr_payload = {
            "resourceType": "ServiceRequest",
            "code": {
                "coding": [{
                    "system": "http://loinc.org",
                    "code": "2823-3",
                    "display": "Potassium [Moles/volume] in Serum or Plasma"
                }]
            },
            "authoredOn": now,
            "status": "active",
            "intent": "order",
            "priority": "stat",
            "subject": {"reference": mrn},
            "occurrenceDateTime": next_morning,
            "note": {"text": "Morning serum potassium level"}
        }

        posts.append((f"{base}/MedicationRequest", med_payload))
        posts.append((f"{base}/ServiceRequest", sr_payload))

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
