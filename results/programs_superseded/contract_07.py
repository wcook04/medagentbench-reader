# Written by deepseek/deepseek-v4.1-flash-1017, condition "contract", seed 7. Unedited.
from datetime import datetime, timedelta, time


def _parse_iso_datetime(value):
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def plan(observations, now):
    now_dt = _parse_iso_datetime(now)

    counted = []
    for obs in observations:
        if obs.get("status") != "final":
            continue

        specimen_dt = _parse_iso_datetime(obs["effectiveDateTime"])
        if specimen_dt > now_dt:
            continue

        counted.append((specimen_dt, obs["value"]))

    if not counted:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "no final potassium observations at or before now",
        }

    most_recent_time = max(dt for dt, _ in counted)
    most_recent_values = [value for dt, value in counted if dt == most_recent_time]

    first_value = most_recent_values[0]
    if any(value != first_value for value in most_recent_values[1:]):
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "ambiguous most recent potassium results with different values",
        }

    potassium_value = first_value

    if potassium_value >= 3.5:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": None,
        }

    dose_mEq = (3.5 - potassium_value) * 100.0

    next_day = now_dt.date() + timedelta(days=1)
    repeat_dt = datetime.combine(next_day, time(8, 0, 0), tzinfo=now_dt.tzinfo)

    return {
        "order_replacement": True,
        "dose_mEq": dose_mEq,
        "repeat_potassium_at": repeat_dt.isoformat(),
        "cannot_apply": None,
    }
