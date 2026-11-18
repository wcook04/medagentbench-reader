# Written by deepseek/deepseek-v4.1-flash-1017: "instruction" seed 19, then 2 round(s) of counterexample feedback. Unedited.
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


def _is_compatible_potassium_unit(unit):
    if unit is None:
        return True
    text = str(unit).strip().lower().replace(" ", "")
    if text == "":
        return True
    return text in {"mmol/l", "meq/l"}


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
    timed = []
    usable = []

    for obs in observations:
        if not isinstance(obs, dict):
            continue

        try:
            effective_dt = _parse_iso_datetime(obs.get("effectiveDateTime"))
            if effective_dt.tzinfo is None:
                continue
        except Exception:
            continue

        timed.append(effective_dt)

        status = str(obs.get("status", "")).strip().lower()
        if status in invalid_statuses:
            continue

        if obs.get("value") is None:
            continue

        if not _is_compatible_potassium_unit(obs.get("unit")):
            continue

        try:
            value = Decimal(str(obs["value"]))
            if not value.is_finite():
                continue
        except Exception:
            continue

        usable.append((effective_dt, value))

    if not timed:
        result["cannot_apply"] = "no usable potassium observations"
        return result

    usable = [item for item in usable if item[0] <= now_dt]

    if not usable:
        result["cannot_apply"] = "no usable potassium observations"
        return result

    latest_dt = max(item[0] for item in usable)
    latest_items = [item for item in usable if item[0] == latest_dt]
    latest_values = {item[1] for item in latest_items}
    if len(latest_values) > 1:
        result["cannot_apply"] = "ambiguous most recent potassium observations"
        return result

    most_recent_value = latest_items[0][1]
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
