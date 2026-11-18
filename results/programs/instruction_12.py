# Written by deepseek/deepseek-v4.1-flash-1017, condition "instruction", seed 12. Unedited.
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
        if effective is None:
            continue

        candidates.append((effective, index, obs))

    if not candidates:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "No usable final potassium observations",
        }

    latest = max(candidates, key=lambda item: (item[0], item[1]))[2]
    value = latest.get("value")

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "Most recent potassium value is missing or invalid",
        }

    if not math.isfinite(value):
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "Most recent potassium value is not finite",
        }

    unit = latest.get("unit")
    if not isinstance(unit, str):
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "Most recent potassium unit is missing",
        }

    normalized_unit = unit.strip().lower()
    if normalized_unit not in {"mmol/l", "meq/l"}:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "Most recent potassium unit is not mmol/L or mEq/L",
        }

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
