# Written by deepseek/deepseek-v4.1-flash-1017, condition "contract", seed 8. Unedited.
from datetime import datetime, time, timedelta
from decimal import Decimal

def plan(observations, now):
    def parse_dt(s):
        if isinstance(s, str) and s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)

    now_dt = parse_dt(now)

    eligible = []
    for obs in observations:
        if obs.get("status") != "final":
            continue
        try:
            dt = parse_dt(obs["effectiveDateTime"])
            value = Decimal(str(obs["value"]))
        except (KeyError, TypeError, ValueError):
            continue
        if dt <= now_dt:
            eligible.append((dt, value))

    if not eligible:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "no final potassium results at or before now",
        }

    most_recent_time = max(dt for dt, _ in eligible)
    recent_values = [value for dt, value in eligible if dt == most_recent_time]

    if len(set(recent_values)) > 1:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "multiple different potassium values at the most recent specimen time",
        }

    value = recent_values[0]

    if value >= Decimal("3.5"):
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": None,
        }

    dose_decimal = (Decimal("3.5") - value) / Decimal("0.1") * Decimal("10")
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
