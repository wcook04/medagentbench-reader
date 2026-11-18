# Written by deepseek/deepseek-v4.1-flash-1017, condition "instruction", seed 15. Unedited.
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_CEILING, InvalidOperation


def _parse_dt(value):
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
        now_dt = _parse_dt(now)
    except Exception:
        result["cannot_apply"] = "invalid now"
        return result

    if now_dt.tzinfo is None:
        result["cannot_apply"] = "now missing offset"
        return result

    if not observations:
        result["cannot_apply"] = "no potassium observations"
        return result

    candidates = []
    for obs in observations:
        if not isinstance(obs, dict):
            continue

        status = str(obs.get("status", "")).strip().lower()
        if status in ("cancelled", "entered-in-error", "registered"):
            continue

        try:
            effective_dt = _parse_dt(obs.get("effectiveDateTime"))
        except Exception:
            continue

        candidates.append((effective_dt, obs))

    if not candidates:
        result["cannot_apply"] = "no usable potassium observations"
        return result

    _, latest = max(candidates, key=lambda item: item[0])

    raw_value = latest.get("value")
    if raw_value is None or isinstance(raw_value, bool):
        result["cannot_apply"] = "latest potassium missing value"
        return result

    try:
        value = Decimal(str(raw_value))
        if not value.is_finite():
            raise InvalidOperation
    except Exception:
        result["cannot_apply"] = "invalid potassium value"
        return result

    unit = latest.get("unit")
    if unit is not None:
        normalized_unit = str(unit).strip().lower().replace(" ", "")
        if normalized_unit not in ("mmol/l", "meq/l", "mmol/liter", "meq/liter"):
            result["cannot_apply"] = "unsupported potassium unit"
            return result

    threshold = Decimal("3.5")
    if value < threshold:
        deficit = threshold - value
        increments = deficit / Decimal("0.1")
        dose_units = int(increments.to_integral_value(rounding=ROUND_CEILING))
        dose = dose_units * 10

        repeat_dt = now_dt.replace(hour=8, minute=0, second=0, microsecond=0) + timedelta(days=1)

        result["order_replacement"] = True
        result["dose_mEq"] = dose
        result["repeat_potassium_at"] = repeat_dt.isoformat()

    return result
