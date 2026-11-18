# Written by deepseek/deepseek-v4.1-flash-1017, condition "contract", seed 10. Unedited.
from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation


def _parse_iso(value):
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def _unit_is_acceptable(unit):
    if unit is None:
        return True
    if not isinstance(unit, str):
        return False
    normalized = unit.strip().lower().replace(" ", "")
    return normalized in ("", "mmol/l", "meq/l")


def plan(observations, now):
    now_dt = _parse_iso(now)

    counted = []
    for obs in observations:
        try:
            if obs.get("status") != "final":
                continue

            effective = obs.get("effectiveDateTime")
            if effective is None:
                continue

            specimen_time = _parse_iso(effective)
            if specimen_time > now_dt:
                continue

            if not _unit_is_acceptable(obs.get("unit")):
                continue

            raw_value = obs.get("value")
            if raw_value is None:
                continue

            try:
                value = Decimal(str(raw_value))
            except (InvalidOperation, ValueError):
                continue

            counted.append((specimen_time, value))
        except Exception:
            continue

    if not counted:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "no final potassium result at or before now",
        }

    latest_time = max(t for t, _ in counted)
    latest_values = [v for t, v in counted if t == latest_time]

    if len(set(latest_values)) > 1:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "conflicting potassium values at most recent specimen time",
        }

    value = latest_values[0]
    threshold = Decimal("3.5")

    if value >= threshold:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": None,
        }

    dose_decimal = (threshold - value) / Decimal("0.1") * Decimal("10")

    if dose_decimal == dose_decimal.to_integral_value():
        dose = int(dose_decimal)
    else:
        dose = float(dose_decimal)

    next_day = now_dt.date() + timedelta(days=1)
    repeat_dt = datetime.combine(next_day, time(8, 0, 0)).replace(tzinfo=now_dt.tzinfo)

    return {
        "order_replacement": True,
        "dose_mEq": dose,
        "repeat_potassium_at": repeat_dt.isoformat(),
        "cannot_apply": None,
    }
