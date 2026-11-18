# Written by deepseek/deepseek-v4.1-flash-1017, condition "instruction", seed 9. Unedited.
import math
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_CEILING

def plan(observations, now):
    def parse_dt(value):
        if isinstance(value, datetime):
            return value
        if not isinstance(value, str):
            return None
        s = value.strip()
        if s.endswith("Z") or s.endswith("z"):
            s = s[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(s)
        except ValueError:
            return None

    def cannot(msg):
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": msg,
        }

    if not observations:
        return cannot("no potassium observations")

    now_dt = parse_dt(now)
    if now_dt is None:
        return cannot("invalid current time")
    if now_dt.tzinfo is None:
        return cannot("current time has no offset")

    candidates = []
    for i, obs in enumerate(observations):
        if not isinstance(obs, dict):
            continue
        status = str(obs.get("status") or "").strip().lower()
        if status in {"cancelled", "canceled", "entered-in-error"}:
            continue
        eff = parse_dt(obs.get("effectiveDateTime"))
        if eff is None or eff.tzinfo is None:
            continue
        candidates.append((eff, i, obs))

    if not candidates:
        return cannot("no usable potassium observations")

    eff, i, obs = max(candidates, key=lambda x: (x[0], x[1]))
    status = str(obs.get("status") or "").strip().lower()
    if status not in {"final", "amended", "corrected", "preliminary"}:
        return cannot("most recent potassium observation is not a usable result")

    unit = obs.get("unit")
    if unit is not None:
        u = str(unit).strip().lower()
        if u not in {"mmol/l", "meq/l"}:
            return cannot("unsupported potassium unit")

    try:
        val = Decimal(str(obs.get("value")))
    except Exception:
        return cannot("invalid potassium value")
    if not val.is_finite():
        return cannot("invalid potassium value")

    threshold = Decimal("3.5")
    if val >= threshold:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": None,
        }

    steps = ((threshold - val) / Decimal("0.1")).to_integral_value(rounding=ROUND_CEILING)
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
