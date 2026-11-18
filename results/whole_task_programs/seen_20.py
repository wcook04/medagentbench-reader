# Written by deepseek/deepseek-v4.1-flash-1017, condition "seen": blind_20.py after one look at the server's responses on a made-up chart, seed 1020, temperature 1.0. Unedited.
def run_task(get, api_base, mrn):
    import json, math, datetime
    from urllib.parse import quote

    base = api_base.rstrip("/")

    def load_json(text):
        try:
            return json.loads(text)
        except Exception:
            return None

    def parse_dt(value):
        if not value:
            return None
        try:
            s = str(value).replace("Z", "+00:00")
            dt = datetime.datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            return dt
        except Exception:
            return None

    def extract_value(resource):
        if not isinstance(resource, dict):
            return None
        q = resource.get("valueQuantity")
        if isinstance(q, dict) and q.get("value") is not None:
            try:
                return float(q["value"])
            except Exception:
                pass
        if resource.get("valueString") is not None:
            try:
                return float(str(resource["valueString"]).strip())
            except Exception:
                pass
        for comp in resource.get("component", []) or []:
            if not isinstance(comp, dict):
                continue
            q = comp.get("valueQuantity")
            if isinstance(q, dict) and q.get("value") is not None:
                try:
                    return float(q["value"])
                except Exception:
                    pass
        return None

    def extract_dt(resource):
        if not isinstance(resource, dict):
            return None
        for key in ("effectiveDateTime", "effectiveInstant", "issued"):
            dt = parse_dt(resource.get(key))
            if dt is not None:
                return dt
        period = resource.get("effectivePeriod")
        if isinstance(period, dict):
            for key in ("start", "end"):
                dt = parse_dt(period.get(key))
                if dt is not None:
                    return dt
        return None

    # Resolve MRN identifier to a Patient FHIR id.
    patient_id = str(mrn)
    pb = load_json(get(f"{base}/Patient?identifier={quote(str(mrn), safe='')}"))
    if isinstance(pb, dict):
        if pb.get("resourceType") == "Patient" and pb.get("id"):
            patient_id = str(pb["id"])
        else:
            for e in pb.get("entry", []) or []:
                r = e.get("resource") if isinstance(e, dict) else None
                if isinstance(r, dict) and r.get("resourceType") == "Patient" and r.get("id"):
                    patient_id = str(r["id"])
                    break
    if patient_id.startswith("Patient/"):
        patient_id = patient_id.split("/", 1)[1]
    patient_ref = f"Patient/{patient_id}"

    def collect(bundle):
        out = []
        if not isinstance(bundle, dict):
            return out
        for e in bundle.get("entry", []) or []:
            if not isinstance(e, dict):
                continue
            r = e.get("resource")
            if not isinstance(r, dict) or r.get("resourceType") != "Observation":
                continue
            code_obj = r.get("code", {}) or {}
            codes = [
                str(c.get("code"))
                for c in (code_obj.get("coding") or [])
                if isinstance(c, dict) and c.get("code") is not None
            ]
            text = str(code_obj.get("text", "")).lower()
            if codes and not any(c in ("K", "2823-3") for c in codes) and "potassium" not in text:
                continue
            v = extract_value(r)
            if v is None:
                continue
            dt = extract_dt(r) or datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)
            out.append((dt, v))
        return out

    entries = []

    # Strategy 1: server-side sort by date desc; truncation-safe since
    # the entries returned are the most recent ones.
    b = load_json(get(
        f"{base}/Observation?code=K&patient={quote(patient_ref, safe='')}"
        f"&_sort=-date&_count=10"
    ))
    entries = collect(b)

    # Strategy 2: fall back to plain search + follow `next` links.
    if not entries:
        b = load_json(get(
            f"{base}/Observation?code=K&patient={quote(patient_ref, safe='')}"
            f"&_count=10"
        ))
        entries = collect(b)
        pages = 0
        while isinstance(b, dict) and pages < 20:
            nxt = None
            for link in b.get("link", []) or []:
                if isinstance(link, dict) and link.get("relation") == "next":
                    nxt = link.get("url")
                    break
            if not nxt:
                break
            b = load_json(get(nxt))
            entries.extend(collect(b))
            pages += 1

    if not entries:
        return [], ["No potassium level found."]

    entries.sort(key=lambda x: x[0], reverse=True)
    level = entries[0][1]

    now = datetime.datetime.fromisoformat("2023-11-13T10:15:00+00:00")
    authored = now.isoformat()
    next8 = (now + datetime.timedelta(days=1)).replace(
        hour=8, minute=0, second=0, microsecond=0
    )
    next8_iso = next8.isoformat()

    if level >= 3.5:
        return [], [
            f"Most recent potassium level: {level:g} mEq/L (not low). "
            f"No replacement potassium ordered."
        ]

    inc = max(1, math.ceil(round((3.5 - level) / 0.1, 10)))
    dose = inc * 10

    med = {
        "resourceType": "MedicationRequest",
        "medicationCodeableConcept": {
            "coding": [{
                "system": "http://hl7.org/fhir/sid/ndc",
                "code": "40032-917-01",
                "display": "Potassium replacement oral",
            }],
            "text": "Potassium replacement oral",
        },
        "authoredOn": authored,
        "dosageInstruction": [{
            "route": {"text": "Oral"},
            "doseAndRate": [{"doseQuantity": {"value": dose, "unit": "mEq"}}],
        }],
        "status": "active",
        "intent": "order",
        "subject": {"reference": patient_ref},
    }

    svc = {
        "resourceType": "ServiceRequest",
        "code": {
            "coding": [{
                "system": "http://loinc.org",
                "code": "2823-3",
                "display": "Potassium [Moles/volume] in Serum or Plasma",
            }]
        },
        "authoredOn": authored,
        "status": "active",
        "intent": "order",
        "priority": "stat",
        "subject": {"reference": patient_ref},
        "occurrenceDateTime": next8_iso,
        "note": {"text": "Morning serum potassium level; paired with potassium replacement order."},
    }

    return (
        [(f"{base}/MedicationRequest", med), (f"{base}/ServiceRequest", svc)],
        [
            f"Most recent potassium level: {level:g} mEq/L (low). "
            f"Ordered {dose} mEq oral potassium replacement and morning serum "
            f"potassium level for {next8_iso}."
        ],
    )
