# Written by deepseek/deepseek-v4.1-flash-1017, condition "instruction", seed 13. Unedited.
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_CEILING


def plan(observations, now):
    def parse_dt(s):
        if not isinstance(s, str):
            return None
        try:
            s = s.strip()
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                return None
            return dt
        except Exception:
            return None

    def cannot(msg):
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": msg,
        }

    now_dt = parse_dt(now)
    if now_dt is None:
        return cannot("Invalid or missing current time")

    usable = []
    for obs in observations or []:
        if not isinstance(obs, dict):
            continue
        status = str(obs.get("status", "")).lower()
        if status in ("cancelled", "entered-in-error"):
            continue
        dt = parse_dt(obs.get("effectiveDateTime"))
        if dt is None or dt > now_dt:
            continue
        usable.append((dt, obs))

    if not usable:
        return cannot("No usable potassium observation at or before now")

    latest_dt, latest = max(usable, key=lambda item: item[0])
    status = str(latest.get("status", "")).lower()
    if status not in ("final", "amended", "corrected"):
        return cannot("Most recent potassium observation is not final")

    raw_value = latest.get("value")
    try:
        value = Decimal(str(raw_value))
        if not value.is_finite():
            return cannot("Most recent potassium value is not finite")
    except Exception:
        return cannot("Most recent potassium value is invalid")

    threshold = Decimal("3.5")
    if value >= threshold:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": None,
        }

    deficit = threshold - value
    tenths = (deficit / Decimal("0.1")).to_integral_value(rounding=ROUND_CEILING)
    dose = int(tenths) * 10
    repeat_dt = (now_dt + timedelta(days=1)).replace(
        hour=8, minute=0, second=0, microsecond=0
    )

    return {
        "order_replacement": True,
        "dose_mEq": dose,
        "repeat_potassium_at": repeat_dt.isoformat(),
        "cannot_apply": None,
    }
