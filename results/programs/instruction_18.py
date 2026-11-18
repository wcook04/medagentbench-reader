# Written by deepseek/deepseek-v4.1-flash-1017, condition "instruction", seed 18. Unedited.
from datetime import datetime, timedelta, time
from decimal import Decimal, InvalidOperation, ROUND_CEILING


def plan(observations, now):
    def out(order=False, dose=None, repeat=None, cannot=None):
        return {
            "order_replacement": order,
            "dose_mEq": dose,
            "repeat_potassium_at": repeat,
            "cannot_apply": cannot,
        }

    def parse_dt(value):
        if not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None

    try:
        now_dt = datetime.fromisoformat(str(now).replace("Z", "+00:00"))
    except Exception:
        return out(cannot="invalid now")

    if now_dt.tzinfo is None:
        return out(cannot="now has no timezone offset")

    usable_statuses = {"final", "amended", "corrected"}
    candidates = []

    for idx, obs in enumerate(observations or []):
        if not isinstance(obs, dict):
            continue

        status = obs.get("status")
        if not isinstance(status, str) or status.lower() not in usable_statuses:
            continue

        dt = parse_dt(obs.get("effectiveDateTime"))
        if dt is None or dt.tzinfo is None:
            continue

        candidates.append((dt, idx, obs))

    if not candidates:
        return out(cannot="no final potassium observation")

    latest = max(candidates, key=lambda item: (item[0], item[1]))[2]

    raw_value = latest.get("value")
    if raw_value is None or isinstance(raw_value, bool):
        return out(cannot="most recent potassium has no numeric value")

    try:
        value = Decimal(str(raw_value))
    except (InvalidOperation, ValueError):
        return out(cannot="most recent potassium value is invalid")

    if not value.is_finite():
        return out(cannot="most recent potassium value is invalid")

    unit = latest.get("unit")
    if unit is not None:
        if not isinstance(unit, str):
            return out(cannot="unsupported potassium unit")
        normalized_unit = unit.strip().lower().replace(" ", "")
        if normalized_unit not in {"mmol/l", "meq/l"}:
            return out(cannot="unsupported potassium unit")

    threshold = Decimal("3.5")
    if value >= threshold:
        return out()

    deficit = threshold - value
    increments = (deficit / Decimal("0.1")).to_integral_value(rounding=ROUND_CEILING)
    dose = int(increments) * 10

    repeat_dt = datetime.combine(
        now_dt.date() + timedelta(days=1),
        time(8, 0, 0, tzinfo=now_dt.tzinfo),
    )

    return out(
        order=True,
        dose=dose,
        repeat=repeat_dt.isoformat(),
        cannot=None,
    )
