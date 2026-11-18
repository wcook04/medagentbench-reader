# Written by deepseek/deepseek-v4.1-flash-1017, condition "contract", seed 1. Unedited.
from datetime import datetime, timedelta
from decimal import Decimal

def _parse_datetime(value):
    if not isinstance(value, str):
        raise ValueError
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)

def plan(observations, now):
    now_dt = _parse_datetime(now)
    counted = []

    for obs in observations or []:
        if not isinstance(obs, dict):
            continue
        if str(obs.get("status", "")).lower() != "final":
            continue

        effective = obs.get("effectiveDateTime")
        raw_value = obs.get("value")
        if effective is None or raw_value is None:
            continue

        try:
            specimen_dt = _parse_datetime(effective)
            specimen_value = Decimal(str(raw_value))
        except Exception:
            continue

        try:
            if specimen_dt > now_dt:
                continue
        except TypeError:
            continue

        counted.append((specimen_dt, specimen_value))

    if not counted:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "no qualifying potassium result",
        }

    latest_time = max(t for t, _ in counted)
    latest_values = [v for t, v in counted if t == latest_time]

    unique_values = []
    for v in latest_values:
        if v not in unique_values:
            unique_values.append(v)

    if len(unique_values) > 1:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "multiple different potassium values at most recent time",
        }

    value = unique_values[0]
    threshold = Decimal("3.5")

    if value >= threshold:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": None,
        }

    dose_decimal = (threshold - value) * Decimal("100")
    if dose_decimal == dose_decimal.to_integral_value():
        dose = int(dose_decimal)
    else:
        dose = float(dose_decimal)

    next_day = now_dt.date() + timedelta(days=1)
    repeat_dt = datetime(
        next_day.year,
        next_day.month,
        next_day.day,
        8,
        0,
        0,
        tzinfo=now_dt.tzinfo,
    )

    return {
        "order_replacement": True,
        "dose_mEq": dose,
        "repeat_potassium_at": repeat_dt.isoformat(),
        "cannot_apply": None,
    }
