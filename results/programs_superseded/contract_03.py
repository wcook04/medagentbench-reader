# Written by deepseek/deepseek-v4.1-flash-1017, condition "contract", seed 3. Unedited.
from datetime import datetime, timedelta, time as dt_time
from decimal import Decimal

def plan(observations, now):
    def parse_dt(s):
        if s.endswith("Z") or s.endswith("z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)

    now_dt = parse_dt(now)
    counted = []

    for obs in observations:
        if obs.get("status") != "final":
            continue
        et = obs.get("effectiveDateTime")
        if et is None:
            continue
        try:
            specimen_dt = parse_dt(et)
        except ValueError:
            continue
        if specimen_dt <= now_dt:
            counted.append((specimen_dt, obs.get("value")))

    if not counted:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "no final potassium result at or before now",
        }

    latest_time = max(t for t, _ in counted)
    latest_values = [v for t, v in counted if t == latest_time]
    first_value = latest_values[0]

    if first_value is None:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "most recent potassium result has no value",
        }

    if any(v != first_value for v in latest_values):
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "conflicting values at most recent specimen time",
        }

    k = first_value
    if k < 3.5:
        dose_dec = (Decimal("3.5") - Decimal(str(k))) * Decimal("100")
        if dose_dec == dose_dec.to_integral_value():
            dose = int(dose_dec)
        else:
            dose = float(dose_dec)

        next_date = now_dt.date() + timedelta(days=1)
        next_dt = datetime.combine(next_date, dt_time(8, 0, 0)).replace(tzinfo=now_dt.tzinfo)

        return {
            "order_replacement": True,
            "dose_mEq": dose,
            "repeat_potassium_at": next_dt.isoformat(),
            "cannot_apply": None,
        }

    return {
        "order_replacement": False,
        "dose_mEq": None,
        "repeat_potassium_at": None,
        "cannot_apply": None,
    }
