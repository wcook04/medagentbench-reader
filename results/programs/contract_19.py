# Written by deepseek/deepseek-v4.1-flash-1017, condition "contract", seed 19. Unedited.
from datetime import datetime, timedelta
from decimal import Decimal


def plan(observations, now):
    def parse_dt(s):
        if s is None:
            return None
        s = s.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        elif s.endswith("z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)

    now_dt = parse_dt(now)

    counted = []
    for obs in observations:
        if obs.get("status") != "final":
            continue

        try:
            specimen_dt = parse_dt(obs.get("effectiveDateTime"))
        except Exception:
            continue

        if specimen_dt is None or specimen_dt > now_dt:
            continue

        value = obs.get("value")
        if value is None:
            continue

        try:
            value_dec = Decimal(str(value))
        except Exception:
            continue

        counted.append((specimen_dt, value_dec))

    if not counted:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "no qualifying final potassium result at or before now",
        }

    most_recent_dt = max(dt for dt, _ in counted)
    values_at_most_recent = {
        value for dt, value in counted if dt == most_recent_dt
    }

    if len(values_at_most_recent) != 1:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "conflicting potassium values at the most recent specimen time",
        }

    most_recent_value = next(iter(values_at_most_recent))
    threshold = Decimal("3.5")

    if most_recent_value >= threshold:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": None,
        }

    dose_dec = (threshold - most_recent_value) * Decimal("100")
    if dose_dec == dose_dec.to_integral_value():
        dose = int(dose_dec)
    else:
        dose = float(dose_dec)

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
