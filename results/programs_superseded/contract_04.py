# Written by deepseek/deepseek-v4.1-flash-1017, condition "contract", seed 4. Unedited.
from datetime import datetime, time, timedelta
from decimal import Decimal

def plan(observations, now):
    now_dt = datetime.fromisoformat(now)

    counted = []
    for obs in observations:
        if obs.get("status") != "final":
            continue
        effective = datetime.fromisoformat(obs["effectiveDateTime"])
        if effective <= now_dt:
            counted.append((effective, obs.get("value")))

    if not counted:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "no final potassium result at or before now",
        }

    latest_time = max(effective for effective, _ in counted)
    latest_values = [value for effective, value in counted if effective == latest_time]

    first_value = latest_values[0]
    if any(value != first_value for value in latest_values[1:]):
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "most recent final potassium results have conflicting values",
        }

    value = first_value

    if value < Decimal("3.5"):
        dose = (Decimal("3.5") - Decimal(str(value))) / Decimal("0.1") * Decimal("10")
        next_date = now_dt.date() + timedelta(days=1)
        repeat_dt = datetime.combine(next_date, time(8, 0, 0), tzinfo=now_dt.tzinfo)
        return {
            "order_replacement": True,
            "dose_mEq": float(dose),
            "repeat_potassium_at": repeat_dt.isoformat(),
            "cannot_apply": None,
        }

    return {
        "order_replacement": False,
        "dose_mEq": None,
        "repeat_potassium_at": None,
        "cannot_apply": None,
    }
