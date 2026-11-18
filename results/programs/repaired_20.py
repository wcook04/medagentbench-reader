# Written by deepseek/deepseek-v4.1-flash-1017: "instruction" seed 20, then 2 round(s) of counterexample feedback. Unedited.
def plan(observations, now):
    from datetime import datetime, timedelta
    from decimal import Decimal, ROUND_CEILING
    import math

    def fail(msg):
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": msg,
        }

    def no_order():
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": None,
        }

    if not isinstance(observations, list) or not observations:
        return fail("no potassium observations")

    if not isinstance(now, str):
        return fail("invalid now")

    now_text = now[:-1] + "+00:00" if now.endswith("Z") else now
    try:
        now_dt = datetime.fromisoformat(now_text)
    except Exception:
        return fail("invalid now")

    if now_dt.tzinfo is None:
        return fail("now lacks offset")

    usable_statuses = {"final", "amended", "corrected", "preliminary"}
    usable_candidates = []

    for index, obs in enumerate(observations):
        if not isinstance(obs, dict):
            continue
        if obs.get("status") not in usable_statuses:
            continue

        effective_text = obs.get("effectiveDateTime")
        if not isinstance(effective_text, str):
            return fail("invalid effective time")

        effective_text = effective_text[:-1] + "+00:00" if effective_text.endswith("Z") else effective_text
        try:
            effective_dt = datetime.fromisoformat(effective_text)
        except Exception:
            return fail("invalid effective time")

        if effective_dt.tzinfo is None:
            return fail("effective time lacks offset")

        usable_candidates.append((effective_dt, index, obs))

    if not usable_candidates:
        return fail("no usable potassium observations")

    current_candidates = [
        item for item in usable_candidates
        if item[0] <= now_dt
    ]

    if not current_candidates:
        return fail("no potassium observations at or before now")

    max_effective_time = max(item[0] for item in current_candidates)
    latest_items = [
        item for item in current_candidates
        if item[0] == max_effective_time
    ]

    latest_values = []

    for _, _, latest in latest_items:
        value = latest.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return fail("invalid potassium value")

        if not math.isfinite(float(value)):
            return fail("invalid potassium value")

        unit = latest.get("unit")
        if unit is not None:
            normalized_unit = str(unit).strip().lower().replace(" ", "")
            if normalized_unit not in ("mmol/l", "meq/l"):
                return fail("unsupported potassium unit")

        latest_values.append(Decimal(str(value)))

    first_value = latest_values[0]
    if any(v != first_value for v in latest_values[1:]):
        return fail("conflicting most recent potassium observations")

    potassium = first_value
    threshold = Decimal("3.5")

    if potassium < threshold:
        deficit = threshold - potassium
        tenths_below = (deficit / Decimal("0.1")).to_integral_value(rounding=ROUND_CEILING)
        if tenths_below < 1:
            tenths_below = Decimal(1)

        dose = int(tenths_below) * 10
        repeat_dt = (now_dt + timedelta(days=1)).replace(
            hour=8, minute=0, second=0, microsecond=0
        )

        return {
            "order_replacement": True,
            "dose_mEq": dose,
            "repeat_potassium_at": repeat_dt.isoformat(),
            "cannot_apply": None,
        }

    return no_order()
