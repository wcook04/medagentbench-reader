# Written by deepseek/deepseek-v4.1-flash-1017, condition "contract", seed 4. Unedited.
from datetime import datetime, timedelta
from decimal import Decimal


def _parse_iso(value):
    value = value.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def plan(observations, now):
    now_dt = _parse_iso(now)

    counted = []
    for obs in observations:
        if obs.get("status") != "final":
            continue
        try:
            specimen_time = _parse_iso(obs["effectiveDateTime"])
            if specimen_time.tzinfo is None:
                specimen_time = specimen_time.replace(tzinfo=now_dt.tzinfo)
            if specimen_time <= now_dt:
                counted.append((specimen_time, obs.get("value")))
        except Exception:
            continue

    if not counted:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "no final potassium result at or before now",
        }

    most_recent_time = max(t for t, _ in counted)
    most_recent_values = [v for t, v in counted if t == most_recent_time]

    try:
        values = [Decimal(str(v)) for v in most_recent_values]
    except Exception:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "invalid potassium value",
        }

    if len(set(values)) > 1:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "conflicting most recent potassium results",
        }

    value = values[0]
    threshold = Decimal("3.5")

    if value >= threshold:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": None,
        }

    dose_decimal = (threshold - value) / Decimal("0.1") * Decimal("10")
    dose = float(dose_decimal)
    if dose_decimal == dose_decimal.to_integral_value():
        dose = int(dose_decimal)

    repeat_at = (now_dt + timedelta(days=1)).replace(
        hour=8, minute=0, second=0, microsecond=0
    )

    return {
        "order_replacement": True,
        "dose_mEq": dose,
        "repeat_potassium_at": repeat_at.isoformat(),
        "cannot_apply": None,
    }
