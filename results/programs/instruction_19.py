# Written by deepseek/deepseek-v4.1-flash-1017, condition "instruction", seed 19. Unedited.
from datetime import datetime, timedelta
from decimal import Decimal

def _parse_iso_datetime(value):
    if value is None:
        raise ValueError("missing datetime")
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if text.endswith("Z"):
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
        now_dt = _parse_iso_datetime(now)
    except Exception:
        result["cannot_apply"] = "invalid current time"
        return result

    if now_dt.tzinfo is None:
        result["cannot_apply"] = "current time lacks timezone offset"
        return result

    if not observations:
        result["cannot_apply"] = "no potassium observations"
        return result

    invalid_statuses = {"cancelled", "entered-in-error", "registered", "unknown"}
    usable = []

    for index, obs in enumerate(observations):
        if not isinstance(obs, dict):
            continue

        status = str(obs.get("status", "")).lower()
        if status in invalid_statuses:
            continue

        if obs.get("value") is None:
            continue

        try:
            effective_dt = _parse_iso_datetime(obs.get("effectiveDateTime"))
            if effective_dt.tzinfo is None:
                continue
            value = Decimal(str(obs["value"]))
        except Exception:
            continue

        usable.append((effective_dt, index, value))

    if not usable:
        result["cannot_apply"] = "no usable potassium observations"
        return result

    _, _, most_recent_value = max(usable, key=lambda item: (item[0], item[1]))
    threshold = Decimal("3.5")

    if most_recent_value < threshold:
        try:
            repeat_dt = (now_dt + timedelta(days=1)).replace(
                hour=8, minute=0, second=0, microsecond=0
            )
            dose_value = (threshold - most_recent_value) * Decimal("100")
            if dose_value == dose_value.to_integral_value():
                dose = int(dose_value)
            else:
                dose = float(dose_value)
        except Exception:
            result["cannot_apply"] = "could not calculate replacement"
            return result

        result["order_replacement"] = True
        result["dose_mEq"] = dose
        result["repeat_potassium_at"] = repeat_dt.isoformat()

    return result
