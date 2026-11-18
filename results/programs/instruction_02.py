# Written by deepseek/deepseek-v4.1-flash-1017, condition "instruction", seed 2. Unedited.
from datetime import datetime, timedelta
import math


def _parse_iso(value):
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def plan(observations, now):
    result = {
        "order_replacement": False,
        "dose_mEq": None,
        "repeat_potassium_at": None,
        "cannot_apply": None,
    }

    try:
        now_dt = _parse_iso(now)
    except Exception:
        result["cannot_apply"] = "invalid now"
        return result

    if now_dt.tzinfo is None:
        result["cannot_apply"] = "now lacks timezone offset"
        return result

    candidates = []
    for obs in observations or []:
        status = (obs.get("status") or "").lower()
        if status not in ("final", "amended", "corrected"):
            continue

        try:
            effective_dt = _parse_iso(obs.get("effectiveDateTime"))
        except Exception:
            continue

        if effective_dt.tzinfo is None:
            continue

        value = obs.get("value")
        if value is None:
            continue

        try:
            numeric_value = float(value)
        except Exception:
            continue

        candidates.append((effective_dt, numeric_value))

    if not candidates:
        result["cannot_apply"] = "no usable final potassium observations"
        return result

    candidates.sort(key=lambda item: item[0])
    _, most_recent_value = candidates[-1]

    if most_recent_value < 3.5:
        difference = 3.5 - most_recent_value
        increments = math.ceil(round(difference / 0.1, 10))
        if increments < 1:
            increments = 1

        dose = increments * 10
        repeat_dt = (now_dt + timedelta(days=1)).replace(
            hour=8, minute=0, second=0, microsecond=0
        )

        result["order_replacement"] = True
        result["dose_mEq"] = dose
        result["repeat_potassium_at"] = repeat_dt.isoformat()

    return result
