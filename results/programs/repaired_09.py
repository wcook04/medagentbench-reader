# Written by deepseek/deepseek-v4.1-flash-1017: "instruction" seed 9, then 3 round(s) of counterexample feedback. Unedited.
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

    if observations is None:
        return cannot("no potassium observations")
    if not isinstance(observations, list):
        return cannot("invalid observations")
    if not observations:
        return cannot("no potassium observations")

    now_dt = parse_dt(now)
    if now_dt is None or now_dt.tzinfo is None:
        return cannot("invalid current time")

    candidates = []
    future_candidates = 0

    for i, obs in enumerate(observations):
        if not isinstance(obs, dict):
            return cannot("invalid observation")

        status = str(obs.get("status") or "").strip().lower()
        if status in {"cancelled", "canceled", "entered-in-error"}:
            continue

        eff = parse_dt(obs.get("effectiveDateTime"))
        if eff is None or eff.tzinfo is None:
            return cannot("invalid effectiveDateTime")

        if eff > now_dt:
            future_candidates += 1
            continue

        candidates.append((eff, i, obs, status))

    if not candidates:
        if future_candidates:
            return cannot("no potassium observations at or before current time")
        return cannot("no usable potassium observations")

    max_eff = max(c[0] for c in candidates)
    latest = [c for c in candidates if c[0] == max_eff]

    status_priority = {
        "amended": 2,
        "corrected": 2,
        "final": 1,
        "preliminary": 0,
    }

    usable_latest = [c for c in latest if c[3] in status_priority]
    if not usable_latest:
        return cannot("most recent potassium observation is not a usable result")

    max_priority = max(status_priority[c[3]] for c in usable_latest)
    latest_usable = [
        c for c in usable_latest if status_priority[c[3]] == max_priority
    ]

    parsed_latest = []
    for eff, i, obs, status in latest_usable:
        unit = obs.get("unit")
        if unit is None:
            u = "mmol/l"
        else:
            u = str(unit).strip().lower()
            if u not in {"mmol/l", "meq/l"}:
                return cannot("unsupported potassium unit")

        try:
            val = Decimal(str(obs.get("value")))
        except Exception:
            return cannot("invalid potassium value")
        if not val.is_finite():
            return cannot("invalid potassium value")

        parsed_latest.append((val, u))

    first_val = parsed_latest[0][0]
    for val, _unit in parsed_latest[1:]:
        if val != first_val:
            return cannot("ambiguous most recent potassium observation")

    val = first_val
    threshold = Decimal("3.5")

    if val >= threshold:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": None,
        }

    steps = ((threshold - val) / Decimal("0.1")).to_integral_value(
        rounding=ROUND_CEILING
    )
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
