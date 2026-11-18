# Written by deepseek/deepseek-v4.1-flash-1017: "instruction" seed 17, then 2 round(s) of counterexample feedback. Unedited.
def plan(observations, now):
    from datetime import datetime, timedelta
    import math

    def make_result(order_replacement, dose_mEq, repeat_potassium_at, cannot_apply):
        return {
            "order_replacement": order_replacement,
            "dose_mEq": dose_mEq,
            "repeat_potassium_at": repeat_potassium_at,
            "cannot_apply": cannot_apply,
        }

    def cannot_apply(reason):
        return make_result(False, None, None, reason)

    def no_order():
        return make_result(False, None, None, None)

    if not observations:
        return cannot_apply("no potassium observations")

    try:
        now_dt = datetime.fromisoformat(now.replace("Z", "+00:00"))
    except Exception:
        return cannot_apply("invalid current time")

    candidates = []

    for index, obs in enumerate(observations):
        if not isinstance(obs, dict):
            continue

        status = obs.get("status")
        if status in ("cancelled", "entered-in-error"):
            continue

        effective = obs.get("effectiveDateTime")
        if not isinstance(effective, str):
            continue

        try:
            effective_dt = datetime.fromisoformat(effective.replace("Z", "+00:00"))
        except Exception:
            continue

        if now_dt.tzinfo is not None:
            if effective_dt.tzinfo is None:
                effective_dt = effective_dt.replace(tzinfo=now_dt.tzinfo)
        else:
            if effective_dt.tzinfo is not None:
                effective_dt = effective_dt.replace(tzinfo=None)

        try:
            if effective_dt > now_dt:
                continue
        except TypeError:
            continue

        candidates.append((effective_dt, index, obs))

    if not candidates:
        return cannot_apply("no usable potassium observation")

    latest_dt = max(item[0] for item in candidates)
    latest_entries = [item for item in candidates if item[0] == latest_dt]

    values = []
    for _, _, obs in latest_entries:
        value = obs.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return cannot_apply("most recent potassium value is not numeric")

        value = float(value)
        if not math.isfinite(value):
            return cannot_apply("most recent potassium value is not finite")

        unit = obs.get("unit")
        if unit is not None:
            if not isinstance(unit, str):
                return cannot_apply("most recent potassium unit is not supported")
            normalized_unit = unit.strip().lower().replace(" ", "")
            if normalized_unit not in ("mmol/l", "meq/l", "mmol/liter", "meq/liter"):
                return cannot_apply("most recent potassium unit is not supported")

        values.append(value)

    if not values:
        return cannot_apply("no usable potassium observation")

    first_value = values[0]
    for value in values[1:]:
        if abs(value - first_value) > 1e-9:
            return cannot_apply("conflicting values at most recent potassium time")

    value = first_value
    threshold = 3.5

    if value < threshold:
        deficit = threshold - value
        increments = math.ceil(deficit / 0.1 - 1e-9)
        if increments < 1:
            increments = 1
        dose = increments * 10

        repeat_dt = (now_dt + timedelta(days=1)).replace(
            hour=8, minute=0, second=0, microsecond=0
        )

        return make_result(True, dose, repeat_dt.isoformat(), None)

    return no_order()
