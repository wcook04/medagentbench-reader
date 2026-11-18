# Written by deepseek/deepseek-v4.1-flash-1017, condition "instruction", seed 5. Unedited.
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_CEILING

def plan(observations, now):
    valid_statuses = {"final", "amended", "corrected"}
    candidates = []

    for obs in observations or []:
        if obs.get("status") not in valid_statuses:
            continue

        s = obs.get("effectiveDateTime")
        try:
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            dt = datetime.fromisoformat(s)
        except Exception:
            continue

        candidates.append((dt, obs))

    if not candidates:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "No valid potassium observations"
        }

    candidates.sort(key=lambda item: item[0])
    _, most_recent = candidates[-1]

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

    s = now
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        now_dt = datetime.fromisoformat(s)
    except Exception:
        return {
            "order_replacement": True,
            "dose_mEq": dose_mEq,
            "repeat_potassium_at": None,
            "cannot_apply": "Invalid now"
        }

    repeat_dt = (now_dt + timedelta(days=1)).replace(
        hour=8, minute=0, second=0, microsecond=0
    )

    return {
        "order_replacement": True,
        "dose_mEq": dose_mEq,
        "repeat_potassium_at": repeat_dt.isoformat(),
        "cannot_apply": None
    }
