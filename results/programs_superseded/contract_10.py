# Written by deepseek/deepseek-v4.1-flash-1017, condition "contract", seed 10. Unedited.
from datetime import datetime, timedelta
from decimal import Decimal

def plan(observations, now):
    def parse_dt(s):
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)

    now_dt = parse_dt(now)

    counted = []
    for obs in observations:
        if obs.get("status") != "final":
            continue
        obs_dt = parse_dt(obs["effectiveDateTime"])
        if obs_dt <= now_dt:
            counted.append((obs_dt, obs["value"]))

    if not counted:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "no final potassium results at or before now",
        }

    latest_time = max(dt for dt, _ in counted)
    latest_values = [value for dt, value in counted if dt == latest_time]

    if len(set(latest_values)) > 1:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "multiple different values at most recent specimen time",
        }

    value = latest_values[0]
    threshold = Decimal("3.5")
    value_dec = Decimal(str(value))

    if value_dec >= threshold:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": None,
        }

    dose = (threshold - value_dec) * Decimal("100")
    if dose == dose.to_integral_value():
        dose_out = int(dose)
    else:
        dose_out = float(dose)

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
        "dose_mEq": dose_out,
        "repeat_potassium_at": repeat_dt.isoformat(),
        "cannot_apply": None,
    }
