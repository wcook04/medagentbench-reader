# Written by deepseek/deepseek-v4.1-flash-1017, condition "contract", seed 5. Unedited.
def plan(observations, now):
    from datetime import datetime, time, timedelta
    from decimal import Decimal, InvalidOperation

    def parse_iso(value):
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        text = value.strip()
        if text.endswith("Z") or text.endswith("z"):
            text = text[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None

    now_dt = parse_iso(now)
    if now_dt is None:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "invalid now time",
        }

    counted = []
    for obs in observations:
        if obs.get("status") != "final":
            continue
        specimen_dt = parse_iso(obs.get("effectiveDateTime"))
        if specimen_dt is None:
            continue
        if specimen_dt <= now_dt:
            counted.append((specimen_dt, obs.get("value")))

    if not counted:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "no final potassium results at or before now",
        }

    most_recent = max(specimen_dt for specimen_dt, _ in counted)
    recent_values = [value for specimen_dt, value in counted if specimen_dt == most_recent]

    try:
        decimal_values = [Decimal(str(value)) for value in recent_values]
    except (InvalidOperation, ValueError, TypeError):
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "invalid potassium value",
        }

    if len(set(decimal_values)) > 1:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "conflicting most recent potassium values",
        }

    potassium = decimal_values[0]
    threshold = Decimal("3.5")

    if potassium < threshold:
        dose_decimal = (threshold - potassium) * Decimal("100")
        if dose_decimal == dose_decimal.to_integral_value():
            dose = int(dose_decimal)
        else:
            dose = float(dose_decimal)

        next_date = now_dt.date() + timedelta(days=1)
        repeat_dt = datetime.combine(next_date, time(8, 0, 0)).replace(tzinfo=now_dt.tzinfo)

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
