# Written by deepseek/deepseek-v4.1-flash-1017, condition "instruction", seed 11. Unedited.
def plan(observations, now):
    from datetime import datetime, timedelta
    from decimal import Decimal, ROUND_CEILING

    def parse_dt(s):
        if not isinstance(s, str):
            return None
        t = s.strip()
        if not t:
            return None
        if t.endswith("Z") or t.endswith("z"):
            t = t[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(t)
        except Exception:
            return None

    now_dt = parse_dt(now)
    if now_dt is None or now_dt.tzinfo is None:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "invalid or offset-less now",
        }

    def status_ok(status):
        if status is None:
            return True
        s = str(status).strip().lower()
        return s not in {"cancelled", "canceled", "entered-in-error", "entered_in_error"}

    usable = []
    for obs in observations or []:
        if not isinstance(obs, dict):
            continue
        if not status_ok(obs.get("status")):
            continue
        dt = parse_dt(obs.get("effectiveDateTime"))
        if dt is None or dt.tzinfo is None:
            continue
        usable.append((dt, obs))

    if not usable:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "no usable potassium observations",
        }

    _, latest = max(usable, key=lambda item: item[0])

    value_raw = latest.get("value")
    if value_raw is None:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "most recent potassium has no value",
        }

    try:
        value = Decimal(str(value_raw))
    except Exception:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "most recent potassium value is not numeric",
        }

    if not value.is_finite():
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "most recent potassium value is not finite",
        }

    unit = latest.get("unit")
    if unit is not None and str(unit).strip() != "":
        normalized_unit = str(unit).strip().lower().replace(" ", "").rstrip(".")
        if normalized_unit not in {"mmol/l", "meq/l"}:
            return {
                "order_replacement": False,
                "dose_mEq": None,
                "repeat_potassium_at": None,
                "cannot_apply": "unsupported potassium unit",
            }

    goal = Decimal("3.5")
    if value >= goal:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": None,
        }

    step = Decimal("0.1")
    increments = ((goal - value) / step).to_integral_value(rounding=ROUND_CEILING)
    dose = int(increments) * 10

    next_date = now_dt.date() + timedelta(days=1)
    repeat_dt = datetime(
        next_date.year,
        next_date.month,
        next_date.day,
        8,
        0,
        0,
        tzinfo=now_dt.tzinfo,
    )

    return {
        "order_replacement": True,
        "dose_mEq": dose,
        "repeat_potassium_at": repeat_dt.isoformat(),
        "cannot_apply": None,
    }
