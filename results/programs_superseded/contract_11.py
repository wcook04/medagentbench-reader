# Written by deepseek/deepseek-v4.1-flash-1017, condition "contract", seed 11. Unedited.
from datetime import datetime, time, timedelta
from decimal import Decimal


def plan(observations, now):
    def parse_iso(s):
        if s.endswith("Z") or s.endswith("z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)

    now_dt = parse_iso(now)
    counted = []

    for obs in observations:
        if obs.get("status") != "final":
            continue

        effective = obs.get("effectiveDateTime")
        if effective is None:
            continue

        try:
            specimen_dt = parse_iso(effective)
        except ValueError:
            continue

        if specimen_dt <= now_dt:
            counted.append((specimen_dt, obs.get("value")))

    if not counted:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "no final potassium observations at or before now",
        }

    latest_dt = max(dt for dt, _ in counted)
    latest_values = [v for dt, v in counted if dt == latest_dt]
    first_value = latest_values[0]

    if any(v != first_value for v in latest_values[1:]):
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "conflicting values for most recent potassium",
        }

    if first_value is None:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "most recent potassium has no value",
        }

    value = Decimal(str(first_value))
    threshold = Decimal("3.5")

    if value < threshold:
        dose_dec = (threshold - value) / Decimal("0.1") * Decimal("10")
        if dose_dec == dose_dec.to_integral_value():
            dose = int(dose_dec)
        else:
            dose = float(dose_dec)

        repeat_date = now_dt.date() + timedelta(days=1)
        repeat_dt = datetime.combine(repeat_date, time(8, 0, 0)).replace(tzinfo=now_dt.tzinfo)

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
