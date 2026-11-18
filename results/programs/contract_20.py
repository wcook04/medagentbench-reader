# Written by deepseek/deepseek-v4.1-flash-1017, condition "contract", seed 20. Unedited.
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

def _parse_iso(s):
    if isinstance(s, str) and s.endswith(("Z", "z")):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)

def plan(observations, now):
    now_dt = _parse_iso(now)
    counted = []

    for obs in observations:
        if obs.get("status") != "final":
            continue
        try:
            dt = _parse_iso(obs.get("effectiveDateTime"))
        except Exception:
            continue
        if dt > now_dt:
            continue
        counted.append((dt, obs.get("value")))

    if not counted:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "no qualifying potassium results",
        }

    latest_dt = max(dt for dt, _ in counted)
    latest_values = [value for dt, value in counted if dt == latest_dt]

    decimal_values = []
    for value in latest_values:
        try:
            decimal_values.append(Decimal(str(value)))
        except (InvalidOperation, ValueError):
            return {
                "order_replacement": False,
                "dose_mEq": None,
                "repeat_potassium_at": None,
                "cannot_apply": "invalid potassium value",
            }

    if len(set(decimal_values)) > 1:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "conflicting most recent potassium values",
        }

    potassium = decimal_values[0]
    threshold = Decimal("3.5")

    if potassium >= threshold:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": None,
        }

    dose_decimal = (threshold - potassium) * Decimal("100")
    if dose_decimal == dose_decimal.to_integral_value():
        dose = int(dose_decimal)
    else:
        dose = float(dose_decimal)

    repeat_dt = now_dt.replace(hour=8, minute=0, second=0, microsecond=0) + timedelta(days=1)

    return {
        "order_replacement": True,
        "dose_mEq": dose,
        "repeat_potassium_at": repeat_dt.isoformat(),
        "cannot_apply": None,
    }
