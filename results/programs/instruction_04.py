# Written by deepseek/deepseek-v4.1-flash-1017, condition "instruction", seed 4. Unedited.
from datetime import datetime, timedelta
import math


def _parse_datetime(value):
    if not isinstance(value, str):
        raise ValueError("not a string")
    text = value.strip()
    if text.endswith("Z") or text.endswith("z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def plan(observations, now):
    result = {
        "order_replacement": False,
        "dose_mEq": None,
        "repeat_potassium_at": None,
        "cannot_apply": None,
    }

    try:
        now_dt = _parse_datetime(now)
    except Exception:
        result["cannot_apply"] = "invalid now"
        return result

    if not observations:
        result["cannot_apply"] = "no potassium observations"
        return result

    candidates = []
    for obs in observations:
        if not isinstance(obs, dict):
            continue

        status = str(obs.get("status") or "").lower()
        if status in ("cancelled", "canceled", "entered-in-error"):
            continue

        try:
            effective_dt = _parse_datetime(obs.get("effectiveDateTime"))
        except Exception:
            continue

        candidates.append((effective_dt, obs))

    if not candidates:
        result["cannot_apply"] = "no potassium observations"
        return result

    max_dt = max(dt for dt, _ in candidates)
    latest = [item for item in candidates if item[0] == max_dt]

    if len(latest) > 1:
        first_obs = latest[0][1]
        first_value = first_obs.get("value")
        first_status = str(first_obs.get("status") or "").lower()
        same = True
        for _, obs in latest[1:]:
            if obs.get("value") != first_value:
                same = False
                break
            if str(obs.get("status") or "").lower() != first_status:
                same = False
                break
        if not same:
            result["cannot_apply"] = "ambiguous most recent potassium"
            return result

    latest_dt, latest_obs = latest[0]
    status = str(latest_obs.get("status") or "").lower()

    if status not in ("final", "amended", "corrected"):
        result["cannot_apply"] = "most recent potassium is not final"
        return result

    value = latest_obs.get("value")
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        result["cannot_apply"] = "most recent potassium has no numeric value"
        return result

    value = float(value)
    threshold = 3.5

    if value >= threshold:
        return result

    difference = threshold - value
    increments = math.ceil(round(difference / 0.1, 10))
    dose = increments * 10

    repeat_dt = (now_dt + timedelta(days=1)).replace(
        hour=8, minute=0, second=0, microsecond=0
    )

    result["order_replacement"] = True
    result["dose_mEq"] = dose
    result["repeat_potassium_at"] = repeat_dt.isoformat()
    return result
