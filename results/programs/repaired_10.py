# Written by deepseek/deepseek-v4.1-flash-1017: "instruction" seed 10, then 2 round(s) of counterexample feedback. Unedited.
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_CEILING

def plan(observations, now):
    result = {
        "order_replacement": False,
        "dose_mEq": None,
        "repeat_potassium_at": None,
        "cannot_apply": None,
    }

    try:
        now_dt = datetime.fromisoformat(str(now).replace("Z", "+00:00"))
        if now_dt.tzinfo is None:
            result["cannot_apply"] = "current time lacks offset"
            return result
    except Exception:
        result["cannot_apply"] = "invalid current time"
        return result

    usable = []

    for obs in observations or []:
        if not isinstance(obs, dict):
            continue

        status = str(obs.get("status") or "").strip().lower()
        if status in {
            "entered-in-error",
            "cancelled",
            "canceled",
            "unknown",
            "error",
        }:
            continue

        try:
            eff = datetime.fromisoformat(
                str(obs.get("effectiveDateTime")).replace("Z", "+00:00")
            )
            if eff.tzinfo is None:
                continue
        except Exception:
            continue

        value = obs.get("value")
        if value is None:
            continue

        try:
            value_dec = Decimal(str(value))
            if not value_dec.is_finite():
                continue
        except Exception:
            continue

        unit = obs.get("unit")
        if unit is not None:
            unit_norm = str(unit).strip().lower()
            if unit_norm not in {"mmol/l", "meq/l"}:
                continue

        usable.append((eff, value_dec))

    if not usable:
        result["cannot_apply"] = "no usable potassium observations"
        return result

    current = [(eff, val) for eff, val in usable if eff <= now_dt]
    if not current:
        result["cannot_apply"] = "no potassium observations at or before current time"
        return result

    latest_time = max(eff for eff, _ in current)
    latest_values = [val for eff, val in current if eff == latest_time]
    distinct_values = set(latest_values)

    if len(distinct_values) > 1:
        result["cannot_apply"] = "conflicting most recent potassium observations"
        return result

    most_recent_value = next(iter(distinct_values))
    threshold = Decimal("3.5")

    if most_recent_value < threshold:
        deficit = threshold - most_recent_value
        step = Decimal("0.1")
        increments = (deficit / step).to_integral_value(rounding=ROUND_CEILING)

        result["order_replacement"] = True
        result["dose_mEq"] = int(increments) * 10

        next_day = (now_dt + timedelta(days=1)).replace(
            hour=8, minute=0, second=0, microsecond=0
        )
        result["repeat_potassium_at"] = next_day.isoformat()

    return result
