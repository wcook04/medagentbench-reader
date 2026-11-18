# Written by deepseek/deepseek-v4.1-flash-1017, condition "contract", seed 18. Unedited.
from datetime import datetime, timedelta
from decimal import Decimal

def plan(observations, now):
    def parse_dt(s):
        if isinstance(s, str) and s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)

    now_dt = parse_dt(now)

    counted = []
    for obs in observations:
        if obs.get("status") != "final":
            continue
        try:
            specimen_time = parse_dt(obs["effectiveDateTime"])
        except Exception:
            continue
        if specimen_time > now_dt:
            continue

        value = obs.get("value")
        if value is None:
            continue

        counted.append((specimen_time, value))

    if not counted:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "no final potassium results at or before now",
        }

    latest_time = max(t for t, _ in counted)
    latest_values = [v for t, v in counted if t == latest_time]

    first_value = latest_values[0]
    for value in latest_values[1:]:
        if value != first_value:
            return {
                "order_replacement": False,
                "dose_mEq": None,
                "repeat_potassium_at": None,
                "cannot_apply": "conflicting potassium values at the most recent specimen time",
            }

    try:
        value_dec = Decimal(str(first_value))
    except Exception:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "invalid potassium value",
        }

    threshold = Decimal("3.5")

    if value_dec >= threshold:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": None,
        }

    dose_dec = (threshold - value_dec) * Decimal("100")
    if dose_dec == dose_dec.to_integral_value():
        dose = int(dose_dec)
    else:
        dose = float(dose_dec)

    next_date = (now_dt + timedelta(days=1)).date()
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
