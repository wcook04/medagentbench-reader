# Written by deepseek/deepseek-v4.1-flash-1017, condition "instruction", seed 3. Unedited.
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

    try:
        now_dt = parse_dt(now)
    except Exception:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "invalid current time",
        }

    if now_dt.tzinfo is None or now_dt.utcoffset() is None:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "current time has no offset",
        }

    if not isinstance(observations, list) or not observations:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "no potassium observations",
        }

    valid = []
    bad_statuses = {"cancelled", "entered-in-error", "entered in error"}

    for idx, obs in enumerate(observations):
        if not isinstance(obs, dict):
            continue

        status = obs.get("status")
        if isinstance(status, str) and status.strip().lower() in bad_statuses:
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
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "no usable potassium observations",
        }

    _, _, value = max(valid, key=lambda x: (x[0], x[1]))
    goal = Decimal("3.5")

    if value >= goal:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": None,
        }

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
