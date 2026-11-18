# Written by deepseek/deepseek-v4.1-flash-1017, condition "contract", seed 13. Unedited.
from datetime import datetime, timedelta
from decimal import Decimal


def plan(observations, now):
    def parse_iso(value):
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)

    now_dt = parse_iso(now)

    counted = []
    for obs in observations:
        if obs.get("status") != "final":
            continue

        try:
            specimen_time = parse_iso(obs["effectiveDateTime"])
        except Exception:
            continue

        if specimen_time <= now_dt:
            counted.append((specimen_time, obs))

    if not counted:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "no final potassium results at or before now",
        }

    most_recent_time = max(t for t, _ in counted)
    recent_results = [obs for t, obs in counted if t == most_recent_time]

    try:
        values = [Decimal(str(obs["value"])) for obs in recent_results]
    except Exception:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "most recent potassium result has no usable numeric value",
        }

    first_value = values[0]
    if any(value != first_value for value in values[1:]):
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "multiple different potassium values at the most recent specimen time",
        }

    potassium = first_value
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

    repeat_dt = (now_dt + timedelta(days=1)).replace(
        hour=8, minute=0, second=0, microsecond=0
    )

    return {
        "order_replacement": True,
        "dose_mEq": dose_out,
        "repeat_potassium_at": repeat_dt.isoformat(),
        "cannot_apply": None,
    }
