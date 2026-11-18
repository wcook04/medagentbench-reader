# Written by deepseek/deepseek-v4.1-flash-1017, condition "contract", seed 3. Unedited.
from datetime import datetime, timedelta, time
from decimal import Decimal

def plan(observations, now):
    def parse_dt(s):
        if isinstance(s, str) and (s.endswith("Z") or s.endswith("z")):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)

    now_dt = parse_dt(now)
    counted = []

    for obs in observations:
        try:
            if obs.get("status") != "final":
                continue
            specimen_dt = parse_dt(obs["effectiveDateTime"])
            if specimen_dt > now_dt:
                continue
            value = Decimal(str(obs["value"]))
        except Exception:
            continue
        counted.append((specimen_dt, value))

    empty = {
        "order_replacement": False,
        "dose_mEq": None,
        "repeat_potassium_at": None,
        "cannot_apply": None,
    }

    if not counted:
        empty["cannot_apply"] = "no final potassium result at or before now"
        return empty

    most_recent_time = max(dt for dt, _ in counted)
    recent_values = {value for dt, value in counted if dt == most_recent_time}

    if len(recent_values) > 1:
        empty["cannot_apply"] = "conflicting values at most recent specimen time"
        return empty

    value = next(iter(recent_values))
    threshold = Decimal("3.5")

    if value >= threshold:
        return empty

    dose = (threshold - value) * Decimal("100")
    if dose == dose.to_integral_value():
        dose_out = int(dose)
    else:
        dose_out = float(dose)

    next_date = now_dt.date() + timedelta(days=1)
    repeat_dt = datetime.combine(next_date, time(8, 0, 0)).replace(tzinfo=now_dt.tzinfo)

    return {
        "order_replacement": True,
        "dose_mEq": dose_out,
        "repeat_potassium_at": repeat_dt.isoformat(timespec="seconds"),
        "cannot_apply": None,
    }
