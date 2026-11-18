# Written by deepseek/deepseek-v4.1-flash-1017, condition "blind", seed 19, temperature 1.0. Unedited.
def run_task(get, api_base, mrn):
    import json
    from urllib.parse import urlencode
    from datetime import datetime, timezone
    from decimal import Decimal, ROUND_CEILING

    base = api_base.rstrip("/")
    now_str = "2023-11-13T10:15:00+00:00"
    next_day_8 = "2023-11-14T08:00:00+00:00"

    def load_json(text):
        try:
            return json.loads(text)
        except Exception:
            return {}

    def bundle_resources(obj):
        if not isinstance(obj, dict):
            return []
        if obj.get("resourceType") == "Bundle":
            out = []
            for entry in obj.get("entry", []) or []:
                if isinstance(entry, dict):
                    res = entry.get("resource", entry)
                    if isinstance(res, dict):
                        out.append(res)
            return out
        if "resourceType" in obj:
            return [obj]
        return []

    # Resolve the MRN/identifier to a FHIR Patient id when possible.
    patient_id = mrn
    try:
        p_url = base + "/Patient?" + urlencode({"identifier": mrn})
        p_obj = load_json(get(p_url))
        for res in bundle_resources(p_obj):
            if res.get("resourceType") == "Patient" and res.get("id"):
                patient_id = res["id"]
                break
    except Exception:
        pass

    patient_ref = "Patient/" + str(patient_id)

    def parse_dt(s):
        if not isinstance(s, str):
            return datetime.min.replace(tzinfo=timezone.utc)
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            return d
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)

    def extract_value(res):
        if not isinstance(res, dict):
            return None, None

        vq = res.get("valueQuantity")
        if isinstance(vq, dict) and "value" in vq:
            return vq.get("value"), vq.get("unit") or vq.get("code")

        if "value" in res:
            return res.get("value"), res.get("unit")

        vs = res.get("valueString")
        if vs is not None:
            try:
                return float(vs), None
            except Exception:
                return vs, None

        for comp in res.get("component", []) or []:
            if isinstance(comp, dict):
                vq = comp.get("valueQuantity")
                if isinstance(vq, dict) and "value" in vq:
                    return vq.get("value"), vq.get("unit") or vq.get("code")
                if "value" in comp:
                    return comp.get("value"), comp.get("unit")

        return None, None

    latest_obs = None
    latest_dt = None

    def consider_observations(obj):
        nonlocal latest_obs, latest_dt
        for res in bundle_resources(obj):
            if res.get("resourceType") != "Observation":
                continue
            val, unit = extract_value(res)
            if val is None:
                continue
            dt_s = res.get("effectiveDateTime") or res.get("issued")
            if not dt_s and isinstance(res.get("effectivePeriod"), dict):
                dt_s = res["effectivePeriod"].get("start")
            dt = parse_dt(dt_s)
            if latest_obs is None or dt > latest_dt:
                latest_obs = (res, val, unit, dt_s)
                latest_dt = dt

    # Prefer the local potassium code; fall back to the LOINC code if needed.
    for code in ["K", "2823-3"]:
        try:
            o_url = base + "/Observation?" + urlencode({
                "patient": patient_id,
                "code": code
            })
            consider_observations(load_json(get(o_url)))
        except Exception:
            pass
        if latest_obs is not None:
            break

    posts = []

    if latest_obs is None:
        return posts, ["No potassium level found; no order placed."]

    res, value, unit, dt_s = latest_obs

    try:
        k_value = float(value)
    except Exception:
        return posts, [
            "Most recent potassium value {} is not numeric; no order placed.".format(value)
        ]

    answers = [
        "Most recent potassium: {} {} at {}".format(
            value,
            unit or "",
            dt_s or "unknown time"
        ).strip()
    ]

    if k_value >= 3.5:
        answers.append("Potassium is not low; no replacement ordered.")
        return posts, answers

    diff = Decimal("3.5") - Decimal(str(k_value))
    units_needed = (diff / Decimal("0.1")).to_integral_value(rounding=ROUND_CEILING)
    dose_mEq = int(units_needed * Decimal("10"))

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
        "authoredOn": now_str,
        "dosageInstruction": [
            {
                "route": {"text": "oral"},
                "doseAndRate": [
                    {
                        "doseQuantity": {
                            "value": dose_mEq,
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
    posts.append((base + "/MedicationRequest", med_payload))

    service_payload = {
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
        "subject": {"reference": patient_ref},
        "note": {"text": "Morning serum potassium level to be completed next day at 8am"},
        "occurrenceDateTime": next_day_8
    }
    posts.append((base + "/ServiceRequest", service_payload))

    answers.append("Low potassium: yes. Ordered {} mEq oral potassium replacement.".format(dose_mEq))
    answers.append("Ordered morning serum potassium level for 2023-11-14T08:00:00+00:00.")

    return posts, answers
