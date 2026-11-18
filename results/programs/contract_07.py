# Written by deepseek/deepseek-v4.1-flash-1017, condition "contract", seed 7. Unedited.
from datetime import datetime, timedelta, timezone, time
from decimal import Decimal, InvalidOperation


def plan(observations, now):
    def parse_dt(value):
        if isinstance(value, str) and value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)

    def unit_is_usable(unit):
        if unit is None:
            return True
        s = str(unit).strip().lower().replace(" ", "")
        if s == "":
            return True
        return s in {"mmol/l", "mmol", "meq/l", "meq"}

    try:
        now_dt = parse_dt(now)
    except Exception:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "invalid current time",
        }

    valid = []
    for obs in observations:
        if obs.get("status") != "final":
            continue

        try:
            specimen_dt = parse_dt(obs.get("effectiveDateTime"))
        except Exception:
            continue

        try:
            if specimen_dt > now_dt:
                continue
        except TypeError:
            continue

        if not unit_is_usable(obs.get("unit")):
            continue

        try:
            value = Decimal(str(obs.get("value")))
        except (InvalidOperation, ValueError, TypeError):
            continue

        valid.append((specimen_dt, value))

    if not valid:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "no final potassium result at or before now",
        }

    most_recent_time = max(specimen_dt for specimen_dt, _ in valid)
    recent_values = [
        value for specimen_dt, value in valid if specimen_dt == most_recent_time
    ]

    chosen_value = recent_values[0]
    if any(value != chosen_value for value in recent_values[1:]):
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "most recent potassium results have different values",
        }

    goal = Decimal("3.5")
    if chosen_value >= goal:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": None,
        }

    dose = (goal - chosen_value) * Decimal("100")

    offset = now_dt.utcoffset()
    if offset is None:
        offset = timedelta(0)
    repeat_tz = timezone(offset)
    next_day = now_dt.date() + timedelta(days=1)
    repeat_dt = datetime.combine(next_day, time(8, 0, 0)).replace(tzinfo=repeat_tz)

    return {
        "order_replacement": True,
        "dose_mEq": float(dose),
        "repeat_potassium_at": repeat_dt.isoformat(),
        "cannot_apply": None,
    }
