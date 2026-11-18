# Written by deepseek/deepseek-v4.1-flash-1017, condition "contract", seed 18. Unedited.
from datetime import datetime, time, timedelta
from decimal import Decimal


def _parse_datetime(value):
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def plan(observations, now):
    now_dt = _parse_datetime(now)

    counted = []
    for obs in observations:
        if obs.get("status") != "final":
            continue
        eff = _parse_datetime(obs["effectiveDateTime"])
        if eff <= now_dt:
            counted.append((eff, obs["value"]))

    if not counted:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "no final potassium result at or before now",
        }

    latest_time = max(eff for eff, _ in counted)
    latest_values = [value for eff, value in counted if eff == latest_time]
    first_value = latest_values[0]

    for value in latest_values[1:]:
        if value != first_value:
            return {
                "order_replacement": False,
                "dose_mEq": None,
                "repeat_potassium_at": None,
                "cannot_apply": "conflicting values at most recent specimen time",
            }

    value_dec = Decimal(str(first_value))
    threshold = Decimal("3.5")

    if value_dec >= threshold:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": None,
        }

    dose_dec = (threshold - value_dec) / Decimal("0.1") * Decimal("10")
    dose = float(dose_dec)

    next_date = now_dt.date() + timedelta(days=1)
    repeat_dt = datetime.combine(next_date, time(8, 0, 0), tzinfo=now_dt.tzinfo)

    return {
        "order_replacement": True,
        "dose_mEq": dose,
        "repeat_potassium_at": repeat_dt.isoformat(),
        "cannot_apply": None,
    }
