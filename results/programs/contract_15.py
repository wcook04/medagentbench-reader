# Written by deepseek/deepseek-v4.1-flash-1017, condition "contract", seed 15. Unedited.
from datetime import datetime, timedelta, time

def _parse_dt(value):
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)

def plan(observations, now):
    now_dt = _parse_dt(now)

    counted = []
    for obs in observations:
        if obs.get("status") != "final":
            continue
        try:
            specimen_dt = _parse_dt(obs["effectiveDateTime"])
        except Exception:
            continue
        if specimen_dt > now_dt:
            continue
        counted.append((specimen_dt, float(obs["value"])))

    if not counted:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "no final potassium result at or before now",
        }

    most_recent_dt = max(dt for dt, _ in counted)
    most_recent_values = {value for dt, value in counted if dt == most_recent_dt}

    if len(most_recent_values) > 1:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "conflicting values at most recent time",
        }

    potassium = next(iter(most_recent_values))

    if potassium >= 3.5:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": None,
        }

    dose = 10 * (3.5 - potassium) / 0.1
    next_date = now_dt.date() + timedelta(days=1)
    repeat_dt = datetime.combine(next_date, time(8, 0, 0), tzinfo=now_dt.tzinfo)

    return {
        "order_replacement": True,
        "dose_mEq": dose,
        "repeat_potassium_at": repeat_dt.isoformat(),
        "cannot_apply": None,
    }
