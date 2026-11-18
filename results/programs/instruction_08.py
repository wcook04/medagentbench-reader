# Written by deepseek/deepseek-v4.1-flash-1017, condition "instruction", seed 8. Unedited.
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_CEILING

def plan(observations, now):
    def parse_iso(s):
        if not isinstance(s, str):
            raise ValueError("not a string")
        return datetime.fromisoformat(s.replace("Z", "+00:00"))

    def result(order=False, dose=None, repeat=None, cannot=None):
        return {
            "order_replacement": order,
            "dose_mEq": dose,
            "repeat_potassium_at": repeat,
            "cannot_apply": cannot,
        }

    usable = []
    for i, obs in enumerate(observations or []):
        if not isinstance(obs, dict):
            continue
        status = obs.get("status")
        if status in ("cancelled", "entered-in-error"):
            continue
        try:
            dt = parse_iso(obs.get("effectiveDateTime"))
        except Exception:
            continue
        if dt.tzinfo is None:
            continue
        usable.append((dt, i, obs))

    if not usable:
        return result(cannot="no usable potassium observations")

    _, _, latest = max(usable, key=lambda x: (x[0], x[1]))

    try:
        potassium = Decimal(str(latest.get("value")))
    except (InvalidOperation, ValueError, TypeError):
        return result(cannot="invalid potassium value")

    if not potassium.is_finite():
        return result(cannot="invalid potassium value")

    threshold = Decimal("3.5")
    if potassium >= threshold:
        return result()

    deficit = threshold - potassium
    increments = (deficit / Decimal("0.1")).to_integral_value(rounding=ROUND_CEILING)
    dose = int(increments) * 10

    try:
        now_dt = parse_iso(now)
    except Exception:
        return result(cannot="invalid now")

    if now_dt.tzinfo is None:
        return result(cannot="invalid now")

    repeat_dt = (now_dt + timedelta(days=1)).replace(
        hour=8, minute=0, second=0, microsecond=0
    )

    return result(
        order=True,
        dose=dose,
        repeat=repeat_dt.isoformat(),
    )
