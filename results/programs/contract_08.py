# Written by deepseek/deepseek-v4.1-flash-1017, condition "contract", seed 8. Unedited.
from datetime import datetime, time, timedelta
from decimal import Decimal


def plan(observations, now):
    def parse_dt(value):
        if not isinstance(value, str):
            raise ValueError
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    now_dt = parse_dt(now)

    counted = []
    for obs in observations:
        try:
            if obs.get("status") != "final":
                continue

            specimen_dt = parse_dt(obs.get("effectiveDateTime"))
            if specimen_dt > now_dt:
                continue

            value = obs.get("value")
            if value is None:
                continue

            counted.append((specimen_dt, Decimal(str(value))))
        except Exception:
            continue

    if not counted:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "no qualifying final potassium result at or before now",
        }

    most_recent_dt = max(dt for dt, _ in counted)
    recent_values = [value for dt, value in counted if dt == most_recent_dt]

    first_value = recent_values[0]
    if any(value != first_value for value in recent_values[1:]):
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "conflicting final potassium results at the most recent specimen time",
        }

    potassium = first_value

    if potassium >= Decimal("3.5"):
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": None,
        }

    dose = (Decimal("3.5") - potassium) * Decimal("100")
    if dose == dose.to_integral_value():
        dose_out = int(dose)
    else:
        dose_out = float(dose)

    next_date = now_dt.date() + timedelta(days=1)
    repeat_dt = datetime.combine(
        next_date,
        time(8, 0, 0, tzinfo=now_dt.tzinfo),
    )

    return {
        "order_replacement": True,
        "dose_mEq": dose_out,
        "repeat_potassium_at": repeat_dt.isoformat(),
        "cannot_apply": None,
    }
