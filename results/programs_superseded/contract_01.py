# Written by deepseek/deepseek-v4.1-flash-1017, condition "contract", seed 1. Unedited.
from datetime import datetime, timedelta, timezone, time
from decimal import Decimal


def plan(observations, now):
    def parse_iso(s):
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)

    now_dt = parse_iso(now)

    applicable = []
    for obs in observations:
        if obs.get("status") != "final":
            continue
        value = obs.get("value")
        if value is None:
            continue
        try:
            specimen_dt = parse_iso(obs["effectiveDateTime"])
        except Exception:
            continue
        if specimen_dt <= now_dt:
            applicable.append((specimen_dt, value))

    if not applicable:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "no applicable final potassium result at or before now",
        }

    most_recent_dt = max(dt for dt, _ in applicable)
    recent_values = [value for dt, value in applicable if dt == most_recent_dt]

    first_value = recent_values[0]
    if any(value != first_value for value in recent_values[1:]):
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "most recent potassium results conflict",
        }

    value = first_value
    threshold = Decimal("3.5")
    value_dec = Decimal(str(value))

    if value_dec >= threshold:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": None,
        }

    dose_dec = (threshold - value_dec) * Decimal("100")
    if dose_dec == dose_dec.to_integral_value():
        dose_mEq = int(dose_dec)
    else:
        dose_mEq = float(dose_dec)

    offset = now_dt.utcoffset()
    tz = timezone(offset) if offset is not None else now_dt.tzinfo
    next_date = now_dt.date() + timedelta(days=1)
    repeat_dt = datetime.combine(next_date, time(8, 0, 0), tzinfo=tz)

    return {
        "order_replacement": True,
        "dose_mEq": dose_mEq,
        "repeat_potassium_at": repeat_dt.isoformat(),
        "cannot_apply": None,
    }
