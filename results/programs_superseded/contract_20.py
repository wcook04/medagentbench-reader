# Written by deepseek/deepseek-v4.1-flash-1017, condition "contract", seed 20. Unedited.
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation


def _parse_iso(value):
    if not isinstance(value, str):
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _cannot_apply(message):
    return {
        "order_replacement": False,
        "dose_mEq": None,
        "repeat_potassium_at": None,
        "cannot_apply": message,
    }


def plan(observations, now):
    now_dt = _parse_iso(now)
    if now_dt is None or now_dt.tzinfo is None:
        return _cannot_apply("invalid or offsetless now")

    counted = []
    for obs in observations or []:
        if not isinstance(obs, dict):
            continue
        if obs.get("status") != "final":
            continue

        specimen_dt = _parse_iso(obs.get("effectiveDateTime"))
        if specimen_dt is None or specimen_dt.tzinfo is None:
            continue
        if specimen_dt > now_dt:
            continue

        try:
            value = Decimal(str(obs.get("value")))
        except (InvalidOperation, ValueError):
            continue
        if not value.is_finite():
            continue

        counted.append((specimen_dt, value))

    if not counted:
        return _cannot_apply("no final potassium observations at or before now")

    latest_time = max(dt for dt, _ in counted)
    latest_values = {value for dt, value in counted if dt == latest_time}

    if len(latest_values) != 1:
        return _cannot_apply("most recent final potassium results have conflicting values")

    latest_value = next(iter(latest_values))
    threshold = Decimal("3.5")

    if latest_value < threshold:
        dose_decimal = (threshold - latest_value) * Decimal("100")
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
            tzinfo=now_dt.tzinfo,
        )

        return {
            "order_replacement": True,
            "dose_mEq": dose,
            "repeat_potassium_at": repeat_dt.isoformat(),
            "cannot_apply": None,
        }

    return {
        "order_replacement": False,
        "dose_mEq": None,
        "repeat_potassium_at": None,
        "cannot_apply": None,
    }
