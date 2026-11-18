# Written by deepseek/deepseek-v4.1-flash-1017: "instruction" seed 2, then 2 round(s) of counterexample feedback. Unedited.
from datetime import datetime, timedelta
import math


def _parse_iso(value):
    if isinstance(value, str) and value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def _unit_ok(unit):
    if unit is None:
        return True
    if not isinstance(unit, str):
        return False
    u = unit.strip().lower()
    return u in {"mmol/l", "meq/l"}


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

    past_candidates = []
    any_usable = False

    for obs in observations or []:
        if not isinstance(obs, dict):
            continue

        status = obs.get("status")
        if not isinstance(status, str):
            continue
        status = status.lower()
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

        if not math.isfinite(numeric_value):
            continue

        if not _unit_ok(obs.get("unit")):
            continue

        any_usable = True
        if effective_dt <= now_dt:
            past_candidates.append((effective_dt, numeric_value, status))

    if not past_candidates:
        if not any_usable:
            result["cannot_apply"] = "no usable final potassium observations"
        else:
            result["cannot_apply"] = "no past potassium observations"
        return result

    latest_dt = max(item[0] for item in past_candidates)
    latest_items = [item for item in past_candidates if item[0] == latest_dt]

    priority = {"final": 1, "amended": 2, "corrected": 3}
    max_priority = max(priority.get(item[2], 0) for item in latest_items)
    resolved_items = [
        item for item in latest_items
        if priority.get(item[2], 0) == max_priority
    ]

    values = {item[1] for item in resolved_items}
    if len(values) > 1:
        result["cannot_apply"] = "ambiguous most recent potassium observations"
        return result

    most_recent_value = next(iter(values))

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
