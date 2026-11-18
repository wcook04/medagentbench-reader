# Written by deepseek/deepseek-v4.1-flash-1017, condition "seen": blind_12.py after one look at the server's responses on a made-up chart, seed 1012, temperature 1.0. Unedited.
def run_task(get, api_base, mrn):
    import json
    import math
    from urllib.parse import urlencode, urljoin
    from datetime import datetime, timezone

    base = api_base.rstrip("/")

    def parse_json(text):
        try:
            return json.loads(text)
        except Exception:
            return {}

    def bundle_resources(data, rtype):
        out = []
        if not isinstance(data, dict):
            return out
        if data.get("resourceType") == rtype:
            out.append(data)
        for entry in data.get("entry", []) or []:
            if isinstance(entry, dict):
                res = entry.get("resource")
                if isinstance(res, dict) and res.get("resourceType") == rtype:
                    out.append(res)
        return out

    def next_link(data):
        if not isinstance(data, dict):
            return None
        for link in data.get("link", []) or []:
            if isinstance(link, dict) and link.get("relation") == "next":
                u = link.get("url")
                if u:
                    return u
        return None

    def cc_matches(cc, codes):
        if not isinstance(cc, dict):
            return False
        text = str(cc.get("text", "")).strip().lower()
        if text and (text in {c.lower() for c in codes} or "potassium" in text):
            return True
        for coding in cc.get("coding", []) or []:
            if not isinstance(coding, dict):
                continue
            code = str(coding.get("code", "")).strip()
            disp = str(coding.get("display", "")).strip().lower()
            if code in codes:
                return True
            if "potassium" in disp:
                return True
        return False

    def extract_value(obj):
        if not isinstance(obj, dict):
            return None
        vq = obj.get("valueQuantity")
        if isinstance(vq, dict) and "value" in vq:
            try:
                return float(vq["value"])
            except Exception:
                pass
        for key in ("valueInteger", "valueDecimal", "valueString", "value"):
            if key in obj:
                try:
                    return float(obj[key])
                except Exception:
                    pass
        return None

    def get_obs_value(res, codes):
        if cc_matches(res.get("code", {}), codes):
            v = extract_value(res)
            if v is not None:
                return v
        for comp in res.get("component", []) or []:
            if cc_matches(comp.get("code", {}), codes):
                v = extract_value(comp)
                if v is not None:
                    return v
        return None

    def effective_time(res):
        for key in ("effectiveDateTime", "issued", "effectiveInstant"):
            if res.get(key):
                return res[key]
        per = res.get("effectivePeriod", {})
        if isinstance(per, dict) and per.get("start"):
            return per["start"]
        return ""

    def parse_dt(s):
        if not s:
            return datetime.min.replace(tzinfo=timezone.utc)
        try:
            s2 = str(s).replace("Z", "+00:00")
            dt = datetime.fromisoformat(s2)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)

    patient_url = f"{base}/Patient?{urlencode({'identifier': mrn})}"
    patient_data = parse_json(get(patient_url))
    patients = bundle_resources(patient_data, "Patient")

    pid = None
    for p in patients:
        if p.get("id"):
            pid = p["id"]
            break

    if not pid:
        return [], [f"Unable to find patient with identifier {mrn}."]

    codes = {"K", "2823-3"}

    def search_all_observations(initial_url):
        results = []
        visited = set()
        url = initial_url
        while url and url not in visited:
            visited.add(url)
            try:
                data = parse_json(get(url))
            except Exception:
                break
            results.extend(bundle_resources(data, "Observation"))
            nxt = next_link(data)
            if nxt and not nxt.startswith("http"):
                nxt = urljoin(base + "/", nxt)
            url = nxt
        return results

    observations = search_all_observations(
        f"{base}/Observation?{urlencode({'patient': pid, 'code': 'K'})}"
    )
    if not observations:
        observations = search_all_observations(
            f"{base}/Observation?{urlencode({'patient': pid, 'code': '2823-3'})}"
        )

    best = None
    for res in observations:
        val = get_obs_value(res, codes)
        if val is None:
            continue
        dt = parse_dt(effective_time(res))
        if best is None or dt > best[0]:
            best = (dt, val, res, effective_time(res))

    if best is None:
        return [], [f"No serum potassium level found for patient {pid}."]

    _, potassium, _, when = best

    if potassium >= 3.5:
        return [], [
            f"Patient {pid} most recent potassium is {potassium:g} mmol/L "
            f"(effective {when or 'unknown'}). It is not below 3.5; no replacement "
            f"potassium order or paired morning potassium level was placed."
        ]

    deficit = 3.5 - potassium
    increments = math.ceil(round(deficit / 0.1, 10))
    if increments < 1:
        increments = 1
    dose = increments * 10

    authored_on = "2023-11-13T10:15:00+00:00"
    occurrence = "2023-11-14T08:00:00+00:00"

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
        "authoredOn": authored_on,
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

    lab_payload = {
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
        "authoredOn": authored_on,
        "status": "active",
        "intent": "order",
        "priority": "stat",
        "subject": {"reference": f"Patient/{pid}"},
        "occurrenceDateTime": occurrence,
        "note": {
            "text": "Morning serum potassium level paired with potassium replacement order"
        }
    }

    posts = [
        (f"{base}/MedicationRequest", med_payload),
        (f"{base}/ServiceRequest", lab_payload)
    ]

    answers = [
        f"Patient {pid} most recent potassium is {potassium:g} mmol/L "
        f"(effective {when or 'unknown'}), which is low. Ordered {dose} mEq oral "
        f"potassium replacement (NDC 40032-917-01) and a morning serum potassium "
        f"level (LOINC 2823-3) for 2023-11-14T08:00:00+00:00."
    ]

    return posts, answers
