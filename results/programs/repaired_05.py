# Written by deepseek/deepseek-v4.1-flash-1017: "instruction" seed 5, then 2 round(s) of counterexample feedback. Unedited.
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_CEILING


def plan(observations, now):
    valid_statuses = {"final", "amended", "corrected"}

    def parse_dt(s):
        if not isinstance(s, str):
            return None
        try:
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            return datetime.fromisoformat(s)
        except Exception:
            return None

    now_dt = parse_dt(now)
    if now_dt is None:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "Invalid now"
        }

    valid_observations = []

    for obs in observations or []:
        if not isinstance(obs, dict):
            continue

        if obs.get("status") not in valid_statuses:
            continue

        dt = parse_dt(obs.get("effectiveDateTime"))
        if dt is None:
            continue

        if now_dt.tzinfo is None and dt.tzinfo is not None:
            dt_cmp = dt.replace(tzinfo=None)
        elif now_dt.tzinfo is not None and dt.tzinfo is None:
            dt_cmp = dt.replace(tzinfo=now_dt.tzinfo)
        else:
            dt_cmp = dt

        valid_observations.append((dt_cmp, obs))

    if not valid_observations:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "No valid potassium observations"
        }

    applicable = [
        (dt, obs)
        for dt, obs in valid_observations
        if dt <= now_dt
    ]

    if not applicable:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": None
        }

    applicable.sort(key=lambda item: item[0])
    latest_dt = applicable[-1][0]
    latest = [(dt, obs) for dt, obs in applicable if dt == latest_dt]

    def value_key(obs):
        value = obs.get("value")
        try:
            return ("number", Decimal(str(value)))
        except Exception:
            return ("invalid", repr(value))

    def unit_key(obs):
        unit = obs.get("unit")
        if unit is None:
            return None
        if not isinstance(unit, str):
            return ("invalid", repr(unit))
        return unit.replace(" ", "").lower()

    if len(latest) > 1:
        first_key = (value_key(latest[0][1]), unit_key(latest[0][1]))
        for _, obs in latest[1:]:
            if (value_key(obs), unit_key(obs)) != first_key:
                return {
                    "order_replacement": False,
                    "dose_mEq": None,
                    "repeat_potassium_at": None,
                    "cannot_apply": "Multiple conflicting most recent potassium observations"
                }

    most_recent = latest[0][1]

    value = most_recent.get("value")
    try:
        potassium = Decimal(str(value))
    except Exception:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "Most recent potassium value is not numeric"
        }

    unit = most_recent.get("unit")
    if unit is not None:
        if not isinstance(unit, str):
            return {
                "order_replacement": False,
                "dose_mEq": None,
                "repeat_potassium_at": None,
                "cannot_apply": "Unsupported potassium unit"
            }

        normalized_unit = unit.replace(" ", "").lower()
        if normalized_unit not in {"mmol/l", "meq/l"}:
            return {
                "order_replacement": False,
                "dose_mEq": None,
                "repeat_potassium_at": None,
                "cannot_apply": "Unsupported potassium unit"
            }

    threshold = Decimal("3.5")
    if potassium >= threshold:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": None
        }

    deficit = threshold - potassium
    step = Decimal("0.1")
    units_needed = (deficit / step).to_integral_value(rounding=ROUND_CEILING)
    dose_mEq = int(units_needed * 10)

    repeat_dt = (now_dt + timedelta(days=1)).replace(
        hour=8, minute=0, second=0, microsecond=0
    )

    return {
        "order_replacement": True,
        "dose_mEq": dose_mEq,
        "repeat_potassium_at": repeat_dt.isoformat(),
        "cannot_apply": None
    }
