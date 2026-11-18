# Written by deepseek/deepseek-v4.1-flash-1017: "instruction" seed 3, then 2 round(s) of counterexample feedback. Unedited.
def plan(observations, now):
    from datetime import datetime, timedelta
    from decimal import Decimal, ROUND_CEILING

    def parse_dt(s):
        if not isinstance(s, str):
            raise ValueError
        t = s.strip()
        if t.endswith("Z") or t.endswith("z"):
            t = t[:-1] + "+00:00"
        return datetime.fromisoformat(t)

    def no_action(cannot_apply=None):
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": cannot_apply,
        }

    try:
        now_dt = parse_dt(now)
    except Exception:
        return no_action("invalid current time")

    if now_dt.tzinfo is None or now_dt.utcoffset() is None:
        return no_action("current time has no offset")

    if not isinstance(observations, list) or not observations:
        return no_action("no potassium observations")

    valid = []
    bad_statuses = {
        "cancelled",
        "canceled",
        "entered-in-error",
    }

    for idx, obs in enumerate(observations):
        if not isinstance(obs, dict):
            continue

        status = obs.get("status")
        if isinstance(status, str):
            normalized_status = (
                status.strip().lower().replace("_", "-").replace(" ", "-")
            )
            if normalized_status in bad_statuses:
                continue

        unit = obs.get("unit")
        if unit is not None:
            u = str(unit).strip().lower().replace(" ", "")
            if u not in {"mmol/l", "meq/l"}:
                continue

        edt = obs.get("effectiveDateTime")
        val = obs.get("value")
        if edt is None or val is None:
            continue

        try:
            dt = parse_dt(edt)
        except Exception:
            continue

        if dt.tzinfo is None or dt.utcoffset() is None:
            continue

        try:
            v = Decimal(str(val).strip())
        except Exception:
            continue

        if not v.is_finite():
            continue

        valid.append((dt, idx, v))

    if not valid:
        return no_action("no usable potassium observations")

    past_valid = [item for item in valid if item[0] <= now_dt]
    if not past_valid:
        return no_action("no potassium observations at or before current time")

    latest_dt = max(item[0] for item in past_valid)
    latest_items = [item for item in past_valid if item[0] == latest_dt]
    latest_values = {item[2] for item in latest_items}

    if len(latest_values) > 1:
        return no_action("ambiguous most recent potassium observation")

    value = next(iter(latest_values))
    goal = Decimal("3.5")

    if value >= goal:
        return no_action(None)

    deficit = goal - value
    steps = (deficit / Decimal("0.1")).to_integral_value(rounding=ROUND_CEILING)
    dose = int(steps) * 10

    repeat_dt = (now_dt + timedelta(days=1)).replace(
        hour=8, minute=0, second=0, microsecond=0
    )

    return {
        "order_replacement": True,
        "dose_mEq": dose,
        "repeat_potassium_at": repeat_dt.isoformat(),
        "cannot_apply": None,
    }
