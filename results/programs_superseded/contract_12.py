# Written by deepseek/deepseek-v4.1-flash-1017, condition "contract", seed 12. Unedited.
from datetime import datetime, time, timedelta
from decimal import Decimal


def plan(observations, now):
    def parse_dt(value):
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)

    now_dt = parse_dt(now)

    candidates = []
    for obs in observations:
        if obs.get("status") != "final":
            continue
        try:
            specimen_dt = parse_dt(obs["effectiveDateTime"])
        except Exception:
            continue
        if specimen_dt <= now_dt:
            candidates.append((specimen_dt, obs["value"]))

    if not candidates:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "no qualifying final potassium result at or before now",
        }

    latest_dt = max(dt for dt, _ in candidates)
    latest_values = [v for dt, v in candidates if dt == latest_dt]
    unique_values = {Decimal(str(v)) for v in latest_values}

    if len(unique_values) > 1:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "conflicting values at most recent specimen time",
        }

    potassium = unique_values.pop()
    threshold = Decimal("3.5")

    if potassium >= threshold:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": None,
        }

    dose_decimal = (threshold - potassium) * Decimal("100")
    if dose_decimal == dose_decimal.to_integral_value():
        dose = int(dose_decimal)
    else:
        dose = float(dose_decimal)

    next_day = now_dt.date() + timedelta(days=1)
    repeat_dt = datetime.combine(next_day, time(8, 0, 0)).replace(tzinfo=now_dt.tzinfo)

    return {
        "order_replacement": True,
        "dose_mEq": dose,
        "repeat_potassium_at": repeat_dt.isoformat(),
        "cannot_apply": None,
    }
