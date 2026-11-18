# Written by deepseek/deepseek-v4.1-flash-1017, condition "contract", seed 6. Unedited.
from datetime import datetime, timedelta
from decimal import Decimal


def plan(observations, now):
    def parse_datetime(value):
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)

    now_dt = parse_datetime(now)
    counted = []

    for obs in observations or []:
        if obs.get("status") != "final":
            continue

        try:
            specimen_dt = parse_datetime(obs["effectiveDateTime"])
        except Exception:
            continue

        if specimen_dt > now_dt:
            continue

        try:
            value = Decimal(str(obs["value"]))
        except Exception:
            continue

        counted.append((specimen_dt, value))

    if not counted:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "no qualifying potassium result",
        }

    most_recent = max(specimen_dt for specimen_dt, _ in counted)
    values = [value for specimen_dt, value in counted if specimen_dt == most_recent]

    first_value = values[0]
    if any(value != first_value for value in values[1:]):
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "conflicting most recent potassium values",
        }

    value = first_value
    threshold = Decimal("3.5")

    if value >= threshold:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": None,
        }

    dose_decimal = (threshold - value) * Decimal("100")
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
