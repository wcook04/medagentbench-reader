# Written by deepseek/deepseek-v4.1-flash-1017, condition "contract", seed 6. Unedited.
from datetime import datetime, time, timedelta
from decimal import Decimal


def _parse_datetime(value):
    if isinstance(value, str) and value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def plan(observations, now):
    now_dt = _parse_datetime(now)

    counted = []
    for obs in observations:
        if obs.get("status") != "final":
            continue
        specimen_time = _parse_datetime(obs["effectiveDateTime"])
        if specimen_time <= now_dt:
            counted.append((specimen_time, obs["value"]))

    if not counted:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "no final potassium results at or before now"
        }

    most_recent_time = max(specimen_time for specimen_time, _ in counted)
    most_recent_values = [
        value for specimen_time, value in counted
        if specimen_time == most_recent_time
    ]

    first_value = most_recent_values[0]
    if any(value != first_value for value in most_recent_values[1:]):
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "multiple different final potassium values at most recent specimen time"
        }

    value = Decimal(str(first_value))
    threshold = Decimal("3.5")

    if value < threshold:
        dose_decimal = (threshold - value) * Decimal("100")
        if dose_decimal == dose_decimal.to_integral_value():
            dose = int(dose_decimal)
        else:
            dose = float(dose_decimal)

        tomorrow = now_dt.date() + timedelta(days=1)
        repeat_dt = datetime.combine(tomorrow, time(8, 0, 0), tzinfo=now_dt.tzinfo)

        return {
            "order_replacement": True,
            "dose_mEq": dose,
            "repeat_potassium_at": repeat_dt.isoformat(),
            "cannot_apply": None
        }

    return {
        "order_replacement": False,
        "dose_mEq": None,
        "repeat_potassium_at": None,
        "cannot_apply": None
    }
