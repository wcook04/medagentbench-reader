# Written by deepseek/deepseek-v4.1-flash-1017, condition "contract", seed 17. Unedited.
from datetime import datetime, timedelta
from decimal import Decimal

def _parse_datetime(value):
    if isinstance(value, datetime):
        return value
    value = value.strip()
    if value.endswith("Z") or value.endswith("z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)

def plan(observations, now):
    now_dt = _parse_datetime(now)

    counted = []
    for obs in observations:
        if obs.get("status") != "final":
            continue

        effective_raw = obs.get("effectiveDateTime")
        if effective_raw is None:
            continue

        try:
            effective_dt = _parse_datetime(effective_raw)
        except Exception:
            continue

        if effective_dt > now_dt:
            continue

        value = obs.get("value")
        if value is None:
            continue

        try:
            value_dec = Decimal(str(value))
        except Exception:
            continue

        counted.append((effective_dt, value_dec))

    if not counted:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "no qualifying potassium result",
        }

    most_recent_time = max(dt for dt, _ in counted)
    recent_values = [value for dt, value in counted if dt == most_recent_time]

    distinct_values = []
    for value in recent_values:
        if not any(value == existing for existing in distinct_values):
            distinct_values.append(value)

    if len(distinct_values) > 1:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "conflicting most recent potassium results",
        }

    potassium = recent_values[0]
    threshold = Decimal("3.5")

    if potassium >= threshold:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": None,
        }

    dose_decimal = (threshold - potassium) / Decimal("0.1") * Decimal("10")
    if dose_decimal == dose_decimal.to_integral_value():
        dose = int(dose_decimal)
    else:
        dose = float(dose_decimal)

    next_day = now_dt + timedelta(days=1)
    repeat_dt = next_day.replace(hour=8, minute=0, second=0, microsecond=0)

    return {
        "order_replacement": True,
        "dose_mEq": dose,
        "repeat_potassium_at": repeat_dt.isoformat(),
        "cannot_apply": None,
    }
