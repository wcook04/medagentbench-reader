# Written by deepseek/deepseek-v4.1-flash-1017, condition "instruction", seed 6. Unedited.
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

    def parse_dt(s):
        if not isinstance(s, str):
            return None
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None

    def valid_status(status):
        return status in (None, "final", "amended", "corrected", "preliminary")

    candidate = None
    for idx, obs in enumerate(observations or []):
        if not isinstance(obs, dict):
            continue
        if not valid_status(obs.get("status")):
            continue
        eff = parse_dt(obs.get("effectiveDateTime"))
        if eff is None:
            continue
        if candidate is None or eff > candidate[0] or (eff == candidate[0] and idx > candidate[2]):
            candidate = (eff, obs, idx)

    if candidate is None:
        return cannot("no usable potassium observations")

    _, obs, _ = candidate
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

    threshold = Decimal("3.5")
    if k >= threshold:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": None,
        }

    try:
        steps = ((threshold - k) / Decimal("0.1")).to_integral_value(rounding=ROUND_CEILING)
        dose = int(steps) * 10
    except Exception:
        return cannot("could not calculate potassium dose")

    now_dt = parse_dt(now)
    if now_dt is None:
        return cannot("current time is invalid")

    next_date = now_dt.date() + timedelta(days=1)
    repeat_dt = datetime.combine(next_date, time(8, 0, 0)).replace(tzinfo=now_dt.tzinfo)

    return {
        "order_replacement": True,
        "dose_mEq": dose,
        "repeat_potassium_at": repeat_dt.isoformat(),
        "cannot_apply": None,
    }
