# Written by deepseek/deepseek-v4.1-flash-1017, condition "contract", seed 14. Unedited.
from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation

def plan(observations, now):
    def parse_dt(value):
        if value is None:
            return None
        try:
            if isinstance(value, str) and value.endswith("Z"):
                value = value[:-1] + "+00:00"
            return datetime.fromisoformat(value)
        except Exception:
            return None

    def unit_is_ok(unit):
        if unit is None:
            return True
        if not isinstance(unit, str):
            return False
        u = unit.strip().lower().replace(" ", "")
        if u == "":
            return True
        return u in ("mmol/l", "meq/l")

    now_dt = parse_dt(now)
    if now_dt is None:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "invalid now value"
        }

    counted = []
    for obs in observations:
        if str(obs.get("status", "")).lower() != "final":
            continue

        specimen_dt = parse_dt(obs.get("effectiveDateTime"))
        if specimen_dt is None:
            continue

        try:
            if specimen_dt > now_dt:
                continue
        except TypeError:
            continue

        if not unit_is_ok(obs.get("unit")):
            continue

        value = obs.get("value")
        if value is None:
            continue

        try:
            decimal_value = Decimal(str(value))
        except (InvalidOperation, ValueError):
            continue

        counted.append((specimen_dt, decimal_value))

    if not counted:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "no eligible potassium result"
        }

    most_recent_dt = max(dt for dt, _ in counted)
    recent_values = [value for dt, value in counted if dt == most_recent_dt]
    unique_values = set(recent_values)

    if len(unique_values) > 1:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "conflicting most recent potassium values"
        }

    recent_value = next(iter(unique_values))
    threshold = Decimal("3.5")

    if recent_value >= threshold:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": None
        }

    dose_decimal = (threshold - recent_value) * Decimal("100")
    if dose_decimal == dose_decimal.to_integral_value():
        dose = int(dose_decimal)
    else:
        dose = float(dose_decimal)

    next_date = now_dt.date() + timedelta(days=1)
    repeat_dt = datetime(
        next_date.year,
        next_date.month,
        next_date.day,
        8,
        0,
        0,
        tzinfo=now_dt.tzinfo
    )

    return {
        "order_replacement": True,
        "dose_mEq": dose,
        "repeat_potassium_at": repeat_dt.isoformat(),
        "cannot_apply": None
    }
