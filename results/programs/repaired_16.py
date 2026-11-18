# Written by deepseek/deepseek-v4.1-flash-1017: "instruction" seed 16, then 2 round(s) of counterexample feedback. Unedited.
def plan(observations, now):
    from datetime import datetime, timedelta, time
    from decimal import Decimal, ROUND_CEILING

    def parse_dt(s):
        if not isinstance(s, str):
            return None
        try:
            t = s.strip()
            if t.endswith("Z") or t.endswith("z"):
                t = t[:-1] + "+00:00"
            return datetime.fromisoformat(t)
        except Exception:
            return None

    def unit_ok(unit):
        if unit is None:
            return True
        if not isinstance(unit, str):
            return False
        u = unit.strip().lower().replace(" ", "")
        u = u.replace("µ", "u").replace("μ", "u")
        return u in {
            "mmol/l", "mmol/liter", "mmol",
            "meq/l", "meq/liter", "meq",
        }

    def result(order=False, dose=None, repeat=None, reason=None):
        return {
            "order_replacement": order,
            "dose_mEq": dose,
            "repeat_potassium_at": repeat,
            "cannot_apply": reason,
        }

    if not isinstance(observations, list) or not observations:
        return result(reason="no potassium observations")

    valid_statuses = {"final", "amended", "corrected"}
    candidates = []
    had_dict = False

    for obs in observations:
        if not isinstance(obs, dict):
            continue
        had_dict = True

        status = obs.get("status")
        if not isinstance(status, str) or status.strip().lower() not in valid_statuses:
            continue

        dt = parse_dt(obs.get("effectiveDateTime"))
        if dt is None or dt.tzinfo is None:
            continue

        candidates.append((dt, obs))

    if not candidates:
        return result(
            reason="no final potassium observation" if had_dict else "no potassium observations"
        )

    now_dt = parse_dt(now)
    if now_dt is None or now_dt.tzinfo is None:
        return result(reason="invalid now")

    available = [(dt, obs) for dt, obs in candidates if dt <= now_dt]
    if not available:
        return result(reason="no potassium observation at or before now")

    latest_dt = max(dt for dt, _ in available)
    latest = [(dt, obs) for dt, obs in available if dt == latest_dt]

    latest_levels = []
    latest_bad_reason = None

    for _, obs in latest:
        value = obs.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
            latest_bad_reason = "most recent potassium value missing"
            continue

        if not unit_ok(obs.get("unit")):
            latest_bad_reason = "unsupported potassium unit"
            continue

        try:
            level = Decimal(str(value))
        except Exception:
            latest_bad_reason = "invalid potassium value"
            continue

        if not level.is_finite():
            latest_bad_reason = "invalid potassium value"
            continue

        latest_levels.append(level)

    if len(latest) > 1:
        if len(latest_levels) != len(latest):
            return result(reason="conflicting most recent potassium observations")

        first_level = latest_levels[0]
        if any(level != first_level for level in latest_levels[1:]):
            return result(reason="conflicting most recent potassium observations")
    else:
        if not latest_levels:
            return result(reason=latest_bad_reason or "most recent potassium value missing")

    level = latest_levels[0]
    threshold = Decimal("3.5")

    if level >= threshold:
        return result()

    diff = threshold - level
    increments = (diff / Decimal("0.1")).to_integral_value(rounding=ROUND_CEILING)
    dose = int(increments * Decimal("10"))

    next_day = now_dt.date() + timedelta(days=1)
    repeat_dt = datetime.combine(next_day, time(8, 0, 0)).replace(tzinfo=now_dt.tzinfo)

    return result(order=True, dose=dose, repeat=repeat_dt.isoformat())
