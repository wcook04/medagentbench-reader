# Written by deepseek/deepseek-v4.1-flash-1017, condition "contract", seed 9. Unedited.
from datetime import datetime, timedelta
from decimal import Decimal


def _parse_dt(value):
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    elif value.endswith("z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def plan(observations, now):
    now_dt = _parse_dt(now)

    counted = []
    for obs in observations or []:
        try:
            if obs.get("status") != "final":
                continue

            specimen_dt = _parse_dt(obs["effectiveDateTime"])
            if specimen_dt > now_dt:
                continue

            unit = obs.get("unit")
            if unit is not None:
                normalized_unit = unit.strip().lower().replace(" ", "")
                if normalized_unit and normalized_unit not in ("mmol/l", "meq/l"):
                    continue

            value = obs.get("value")
            if value is None:
                continue

            counted.append((specimen_dt, float(value)))
        except Exception:
            continue

    if not counted:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "no final potassium result at or before now",
        }

    most_recent_dt = max(dt for dt, _ in counted)
    most_recent_values = [value for dt, value in counted if dt == most_recent_dt]

    first_value = most_recent_values[0]
    if any(value != first_value for value in most_recent_values[1:]):
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "conflicting potassium results at most recent specimen time",
        }

    potassium = first_value

    if potassium >= 3.5:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": None,
        }

    dose_decimal = (Decimal("3.5") - Decimal(str(potassium))) * Decimal("100")
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
