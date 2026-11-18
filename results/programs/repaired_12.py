# Written by deepseek/deepseek-v4.1-flash-1017: "instruction" seed 12, then 2 round(s) of counterexample feedback. Unedited.
from datetime import datetime, timedelta
import math


def _parse_datetime(value):
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _normalize_potassium(obs):
    value = obs.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None, "Most recent potassium value is missing or invalid"
    if not math.isfinite(value):
        return None, "Most recent potassium value is not finite"

    unit = obs.get("unit")
    if unit is None:
        normalized_unit = "mmol/l"
    elif isinstance(unit, str):
        normalized_unit = unit.strip().lower()
        if normalized_unit == "":
            normalized_unit = "mmol/l"
        elif normalized_unit not in {"mmol/l", "meq/l"}:
            return None, "Most recent potassium unit is not mmol/L or mEq/L"
    else:
        return None, "Most recent potassium unit is missing or invalid"

    return (value, normalized_unit), None


def plan(observations, now):
    now_dt = _parse_datetime(now)
    if now_dt is None or now_dt.tzinfo is None:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "Invalid or offset-less current time",
        }

    usable_statuses = {"final", "amended", "corrected"}
    candidates = []

    for index, obs in enumerate(observations or []):
        if not isinstance(obs, dict):
            continue

        status = obs.get("status")
        if not isinstance(status, str) or status.strip().lower() not in usable_statuses:
            continue

        effective = _parse_datetime(obs.get("effectiveDateTime"))
        if effective is None or effective.tzinfo is None:
            continue

        if effective > now_dt:
            continue

        candidates.append((effective, index, obs))

    if not candidates:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "No usable final potassium observations",
        }

    latest_effective = max(item[0] for item in candidates)
    latest_candidates = [item for item in candidates if item[0] == latest_effective]

    if len(latest_candidates) > 1:
        normalized_values = []
        for _, _, obs in latest_candidates:
            normalized, error = _normalize_potassium(obs)
            if error is not None:
                return {
                    "order_replacement": False,
                    "dose_mEq": None,
                    "repeat_potassium_at": None,
                    "cannot_apply": error,
                }
            normalized_values.append(normalized)

        first_value = normalized_values[0][0]
        for value, _ in normalized_values[1:]:
            if value != first_value:
                return {
                    "order_replacement": False,
                    "dose_mEq": None,
                    "repeat_potassium_at": None,
                    "cannot_apply": "Multiple conflicting most recent potassium observations",
                }

    latest_obs = latest_candidates[0][2]
    normalized, error = _normalize_potassium(latest_obs)
    if error is not None:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": error,
        }

    value, _ = normalized
    goal = 3.5

    if value >= goal:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": None,
        }

    deficit = goal - value
    increments = math.ceil((deficit / 0.1) - 1e-9)
    if increments < 1:
        increments = 1

    dose_mEq = increments * 10

    next_day = now_dt.date() + timedelta(days=1)
    repeat_dt = datetime(
        next_day.year,
        next_day.month,
        next_day.day,
        8,
        0,
        0,
        tzinfo=now_dt.tzinfo,
    )

    return {
        "order_replacement": True,
        "dose_mEq": dose_mEq,
        "repeat_potassium_at": repeat_dt.isoformat(),
        "cannot_apply": None,
    }
