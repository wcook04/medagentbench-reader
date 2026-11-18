# Written by deepseek/deepseek-v4.1-flash-1017, condition "contract", seed 2. Unedited.
from datetime import datetime, timedelta, time
from decimal import Decimal

def plan(observations, now):
    def parse_dt(value):
        if value is None:
            raise ValueError("missing datetime")
        if isinstance(value, str) and value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)

    now_dt = parse_dt(now)

    counted = []
    for obs in observations:
        status = obs.get("status")
        if status is None or str(status).lower() != "final":
            continue

        try:
            specimen_dt = parse_dt(obs.get("effectiveDateTime"))
        except Exception:
            continue

        if specimen_dt > now_dt:
            continue

        unit = obs.get("unit")
        if unit is not None:
            u = str(unit).strip().lower()
            if u != "" and u not in ("mmol/l", "mmol", "meq/l", "meq"):
                continue

        value = obs.get("value")
        if value is None:
            continue

        try:
            value_decimal = Decimal(str(value))
        except Exception:
            continue

        counted.append((specimen_dt, value_decimal))

    if not counted:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "no qualifying final potassium result at or before now",
        }

    most_recent_time = max(dt for dt, _ in counted)
    recent_values = [value for dt, value in counted if dt == most_recent_time]

    distinct_values = []
    for value in recent_values:
        if value not in distinct_values:
            distinct_values.append(value)

    if len(distinct_values) > 1:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "multiple different potassium values at the most recent specimen time",
        }

    potassium = distinct_values[0]
    threshold = Decimal("3.5")

    if potassium >= threshold:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": None,
        }

    dose = (threshold - potassium) * Decimal("100")
    if dose == dose.to_integral_value():
        dose_out = int(dose)
    else:
        dose_out = float(dose)

    repeat_date = now_dt.date() + timedelta(days=1)
    repeat_dt = datetime.combine(repeat_date, time(8, 0, 0), tzinfo=now_dt.tzinfo)

    return {
        "order_replacement": True,
        "dose_mEq": dose_out,
        "repeat_potassium_at": repeat_dt.isoformat(),
        "cannot_apply": None,
    }
