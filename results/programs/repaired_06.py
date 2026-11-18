# Written by deepseek/deepseek-v4.1-flash-1017: "instruction" seed 6, then 2 round(s) of counterexample feedback. Unedited.
def plan(observations, now):
    from datetime import datetime, timedelta, time
    from decimal import Decimal, ROUND_CEILING, InvalidOperation

    def cannot(msg):
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

    def parse_dt(s):
        if not isinstance(s, str):
            return None
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None
        if dt.tzinfo is None:
            return None
        return dt

    def valid_status(status):
        return status in (None, "final", "amended", "corrected", "preliminary")

    now_dt = parse_dt(now)
    if now_dt is None:
        return cannot("current time is invalid")

    usable = []
    for idx, obs in enumerate(observations or []):
        if not isinstance(obs, dict):
            continue
        if not valid_status(obs.get("status")):
            continue

        eff = parse_dt(obs.get("effectiveDateTime"))
        if eff is None:
            continue
        if eff > now_dt:
            continue

        usable.append((eff, idx, obs))

    if not usable:
        return cannot("no usable potassium observations")

    latest_eff = max(item[0] for item in usable)
    latest = [item for item in usable if item[0] == latest_eff]

    values = []
    for _, _, obs in latest:
        val = obs.get("value")
        if isinstance(val, bool) or not isinstance(val, (int, float, Decimal)):
            return cannot("most recent potassium value is not numeric")

        try:
            k = Decimal(str(val))
        except (InvalidOperation, ValueError):
            return cannot("most recent potassium value is not numeric")

        if not k.is_finite():
            return cannot("most recent potassium value is not finite")

        unit = obs.get("unit")
        if unit is not None:
            norm = str(unit).strip().casefold().replace(" ", "")
            if norm not in ("mmol/l", "meq/l"):
                return cannot("most recent potassium unit is not mmol/L or mEq/L")

        values.append(k)

    if not values:
        return cannot("no usable potassium observations")

    first_value = values[0]
    if any(value != first_value for value in values[1:]):
        return cannot("conflicting most recent potassium observations")

    k = first_value
    threshold = Decimal("3.5")

    if k >= threshold:
        return no_order()

    try:
        steps = ((threshold - k) / Decimal("0.1")).to_integral_value(
            rounding=ROUND_CEILING
        )
        dose = int(steps) * 10
    except Exception:
        return cannot("could not calculate potassium dose")

    next_date = now_dt.date() + timedelta(days=1)
    repeat_dt = datetime.combine(next_date, time(8, 0, 0)).replace(
        tzinfo=now_dt.tzinfo
    )

    return {
        "order_replacement": True,
        "dose_mEq": dose,
        "repeat_potassium_at": repeat_dt.isoformat(),
        "cannot_apply": None,
    }
