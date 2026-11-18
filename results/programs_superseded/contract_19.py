# Written by deepseek/deepseek-v4.1-flash-1017, condition "contract", seed 19. Unedited.
from datetime import datetime, time, timedelta


def plan(observations, now):
    def parse_dt(value):
        if isinstance(value, str) and value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)

    now_dt = parse_dt(now)

    valid = []
    for obs in observations:
        if obs.get("status") != "final":
            continue
        try:
            specimen_dt = parse_dt(obs["effectiveDateTime"])
        except (KeyError, TypeError, ValueError):
            continue
        if specimen_dt <= now_dt:
            valid.append((specimen_dt, obs["value"]))

    if not valid:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "no final potassium result at or before now",
        }

    most_recent_time = max(specimen_dt for specimen_dt, _ in valid)
    most_recent_values = [
        value for specimen_dt, value in valid if specimen_dt == most_recent_time
    ]

    first_value = most_recent_values[0]
    if any(value != first_value for value in most_recent_values[1:]):
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "conflicting potassium values at most recent specimen time",
        }

    potassium = first_value

    if potassium >= 3.5:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": None,
        }

    dose = (3.5 - potassium) * 100.0
    next_day = now_dt.date() + timedelta(days=1)
    repeat_dt = datetime.combine(next_day, time(8, 0, 0), tzinfo=now_dt.tzinfo)

    return {
        "order_replacement": True,
        "dose_mEq": dose,
        "repeat_potassium_at": repeat_dt.isoformat(),
        "cannot_apply": None,
    }
