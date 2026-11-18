# Written by deepseek/deepseek-v4.1-flash-1017, condition "contract", seed 5. Unedited.
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation


def _parse_iso(value):
    if isinstance(value, str) and value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def _to_decimal(value):
    return Decimal(str(value))


def plan(observations, now):
    now_dt = _parse_iso(now)

    counted = []
    for obs in observations:
        try:
            if obs.get("status") != "final":
                continue

            specimen_dt = _parse_iso(obs["effectiveDateTime"])
            if specimen_dt > now_dt:
                continue

            value = _to_decimal(obs["value"])
            counted.append((specimen_dt, value))
        except (KeyError, TypeError, ValueError, InvalidOperation):
            continue

    if not counted:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "no final potassium result at or before now",
        }

    latest_dt = max(dt for dt, _ in counted)
    latest_values = [value for dt, value in counted if dt == latest_dt]
    first_value = latest_values[0]

    if any(value != first_value for value in latest_values[1:]):
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "conflicting most recent potassium values",
        }

    value = first_value
    threshold = Decimal("3.5")

    if value >= threshold:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": None,
        }

    dose_dec = (threshold - value) / Decimal("0.1") * Decimal("10")
    if dose_dec == dose_dec.to_integral_value():
        dose = int(dose_dec)
    else:
        dose = float(dose_dec)

    repeat_dt = now_dt.replace(hour=8, minute=0, second=0, microsecond=0) + timedelta(days=1)

    return {
        "order_replacement": True,
        "dose_mEq": dose,
        "repeat_potassium_at": repeat_dt.isoformat(),
        "cannot_apply": None,
    }
