# Written by deepseek/deepseek-v4.1-flash-1017, condition "instruction", seed 1. Unedited.
def plan(observations, now):
    from datetime import datetime, time, timedelta
    from decimal import Decimal, ROUND_CEILING, InvalidOperation

    def parse_dt(s):
        if not isinstance(s, str):
            return None
        s = s.strip()
        if s.endswith("Z") or s.endswith("z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
        except Exception:
            return None
        if dt.tzinfo is None:
            return None
        return dt

    now_dt = parse_dt(now)
    if now_dt is None:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "invalid current time"
        }

    usable_statuses = {"final", "amended", "corrected"}
    accepted_units = {"mmol/l", "mmoll", "meq/l", "meql"}

    def unit_ok(unit):
        if unit is None:
            return True
        if not isinstance(unit, str):
            return False
        u = unit.strip().lower().replace(" ", "")
        if u == "":
            return True
        return u in accepted_units

    candidates = []
    for idx, obs in enumerate(observations or []):
        if not isinstance(obs, dict):
            continue
        status = obs.get("status")
        if not isinstance(status, str) or status.strip().lower() not in usable_statuses:
            continue

        dt = parse_dt(obs.get("effectiveDateTime"))
        if dt is None:
            continue

        value = obs.get("value")
        if value is None:
            continue

        try:
            numeric_value = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            continue

        candidates.append((dt, idx, numeric_value, obs.get("unit")))

    if not candidates:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "no usable potassium observation"
        }

    candidates.sort(key=lambda item: (item[0], item[1]))
    latest_dt, latest_idx, latest_value, latest_unit = candidates[-1]

    if not unit_ok(latest_unit):
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "unsupported potassium unit"
        }

    threshold = Decimal("3.5")
    if latest_value >= threshold:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": None
        }

    deficit = threshold - latest_value
    increments = (deficit / Decimal("0.1")).to_integral_value(rounding=ROUND_CEILING)
    dose_mEq = int(increments) * 10

    next_date = now_dt.date() + timedelta(days=1)
    repeat_dt = datetime.combine(next_date, time(8, 0, 0), tzinfo=now_dt.tzinfo)

    return {
        "order_replacement": True,
        "dose_mEq": dose_mEq,
        "repeat_potassium_at": repeat_dt.isoformat(),
        "cannot_apply": None
    }
