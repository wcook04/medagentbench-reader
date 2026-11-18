# Written by deepseek/deepseek-v4.1-flash-1017: "instruction" seed 15, then 3 round(s) of counterexample feedback. Unedited.
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_CEILING, InvalidOperation


def _parse_dt(value):
    if not isinstance(value, str):
        raise ValueError("not a string")
    text = value.strip()
    if text.endswith("Z") or text.endswith("z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def _status_priority(obs):
    status = str(obs.get("status", "")).strip().lower()
    if status in ("amended", "corrected"):
        return 3
    if status == "final":
        return 2
    return 1


def _parse_value_and_unit(obs):
    raw_value = obs.get("value")
    if raw_value is None or isinstance(raw_value, bool):
        raise ValueError("missing value")

    try:
        value = Decimal(str(raw_value))
        if not value.is_finite():
            raise InvalidOperation
    except Exception:
        raise ValueError("invalid value")

    unit = obs.get("unit")
    if unit is not None:
        normalized_unit = str(unit).strip().lower().replace(" ", "")
        if normalized_unit not in ("mmol/l", "meq/l", "mmol/liter", "meq/liter"):
            raise ValueError("unsupported unit")

    return value


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

    if not isinstance(observations, list):
        result["cannot_apply"] = "invalid observations"
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

        if effective_dt.tzinfo is None:
            continue
        if effective_dt > now_dt:
            continue

        candidates.append((effective_dt, obs))

    if not candidates:
        result["cannot_apply"] = "no usable potassium observations"
        return result

    latest_dt = max(dt for dt, _ in candidates)
    latest = [obs for dt, obs in candidates if dt == latest_dt]

    max_priority = max(_status_priority(obs) for obs in latest)
    latest = [obs for obs in latest if _status_priority(obs) == max_priority]

    if len(latest) > 1:
        values = []
        for obs in latest:
            try:
                values.append(_parse_value_and_unit(obs))
            except Exception:
                result["cannot_apply"] = "ambiguous latest potassium observations"
                return result

        if any(value != values[0] for value in values[1:]):
            result["cannot_apply"] = "conflicting latest potassium observations"
            return result

        value = values[0]
    else:
        try:
            value = _parse_value_and_unit(latest[0])
        except ValueError as exc:
            msg = str(exc)
            if msg == "missing value":
                result["cannot_apply"] = "latest potassium missing value"
            elif msg == "unsupported unit":
                result["cannot_apply"] = "unsupported potassium unit"
            else:
                result["cannot_apply"] = "invalid potassium value"
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
