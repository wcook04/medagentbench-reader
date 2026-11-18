# Written by deepseek/deepseek-v4.1-flash-1017, condition "contract", seed 12. Unedited.
from datetime import datetime, time, timedelta
from decimal import Decimal


def plan(observations, now):
    def parse_dt(s):
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)

    now_dt = parse_dt(now)

    counted = []
    for obs in observations:
        if obs.get("status") != "final":
            continue
        try:
            eff = parse_dt(obs["effectiveDateTime"])
        except Exception:
            continue
        if eff <= now_dt:
            try:
                value = Decimal(str(obs["value"]))
            except Exception:
                continue
            counted.append((eff, value))

    if not counted:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "no final potassium result at or before now",
        }

    most_recent = max(eff for eff, _ in counted)
    recent_values = [value for eff, value in counted if eff == most_recent]

    if len(set(recent_values)) > 1:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "multiple different potassium values at most recent time",
        }

    value = recent_values[0]
    threshold = Decimal("3.5")

    if value >= threshold:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": None,
        }

    dose_dec = (threshold - value) * Decimal("100")
    if dose_dec == dose_dec.to_integral_value():
        dose = int(dose_dec)
    else:
        dose = float(dose_dec)

    next_date = now_dt.date() + timedelta(days=1)
    repeat_dt = datetime.combine(next_date, time(8, 0, 0)).replace(tzinfo=now_dt.tzinfo)

    return {
        "order_replacement": True,
        "dose_mEq": dose,
        "repeat_potassium_at": repeat_dt.isoformat(),
        "cannot_apply": None,
    }
