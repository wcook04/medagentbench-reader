# Written by deepseek/deepseek-v4.1-flash-1017, condition "instruction", seed 7. Unedited.
def plan(observations, now):
    from datetime import datetime, timedelta
    import math

    def parse_dt(value):
        if not isinstance(value, str):
            return None
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(text)
        except Exception:
            return None

    def cannot(reason):
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": reason,
        }

    now_dt = parse_dt(now)
    if now_dt is None:
        return cannot("invalid current time")

    valid_statuses = {"final", "amended", "corrected"}
    valid_units = {"mmol/l", "meq/l"}

    usable = []
    for obs in observations or []:
        if not isinstance(obs, dict):
            continue

        status = obs.get("status")
        if status is not None and str(status).strip().lower() not in valid_statuses:
            continue

        value = obs.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        value = float(value)
        if not math.isfinite(value):
            continue

        unit = obs.get("unit")
        if unit is not None:
            unit_norm = str(unit).strip().lower().replace(" ", "")
            if unit_norm not in valid_units:
                continue

        effective = parse_dt(obs.get("effectiveDateTime"))
        if effective is None:
            continue

        usable.append((effective, value))

    if not usable:
        return cannot("no usable potassium observations")

    usable.sort(key=lambda item: item[0], reverse=True)
    most_recent_value = usable[0][1]

    if most_recent_value < 3.5:
        dose = (3.5 - most_recent_value) * 100.0
        if abs(dose - round(dose)) < 1e-9:
            dose = int(round(dose))
        else:
            dose = round(dose, 3)

        repeat_dt = now_dt.replace(hour=8, minute=0, second=0, microsecond=0) + timedelta(days=1)

        return {
            "order_replacement": True,
            "dose_mEq": dose,
            "repeat_potassium_at": repeat_dt.isoformat(),
            "cannot_apply": None,
        }

    return {
        "order_replacement": False,
        "dose_mEq": None,
        "repeat_potassium_at": None,
        "cannot_apply": None,
    }
