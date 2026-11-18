# Written by deepseek/deepseek-v4.1-flash-1017, condition "instruction", seed 16. Unedited.
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

    _, obs = max(candidates, key=lambda x: x[0])

    value = obs.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return result(reason="most recent potassium value missing")

    if not unit_ok(obs.get("unit")):
        return result(reason="unsupported potassium unit")

    level = Decimal(str(value))
    threshold = Decimal("3.5")

    if level >= threshold:
        return result()

    now_dt = parse_dt(now)
    if now_dt is None or now_dt.tzinfo is None:
        return result(reason="invalid now")

    diff = threshold - level
    increments = (diff / Decimal("0.1")).to_integral_value(rounding=ROUND_CEILING)
    dose = int(increments * Decimal("10"))

    next_day = now_dt.date() + timedelta(days=1)
    repeat_dt = datetime.combine(next_day, time(8, 0, 0)).replace(tzinfo=now_dt.tzinfo)

    return result(order=True, dose=dose, repeat=repeat_dt.isoformat())
