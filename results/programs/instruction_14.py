# Written by deepseek/deepseek-v4.1-flash-1017, condition "instruction", seed 14. Unedited.
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_CEILING
import math

def plan(observations, now):
    def _parse_iso(value):
        if not isinstance(value, str):
            return None
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    def _cannot(message):
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": message,
        }

    now_dt = _parse_iso(now)
    if now_dt is None:
        return _cannot("invalid now")

    if not isinstance(observations, list):
        return _cannot("observations not a list")

    candidates = []
    for obs in observations:
        if not isinstance(obs, dict):
            continue
        effective = _parse_iso(obs.get("effectiveDateTime"))
        if effective is None:
            continue
        candidates.append((effective, obs))

    if not candidates:
        return _cannot("no potassium observations")

    _, latest = max(candidates, key=lambda item: item[0])

    status = latest.get("status")
    if not isinstance(status, str) or status.lower() not in {"final", "amended", "corrected"}:
        return _cannot("most recent potassium is not final")

    value = latest.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return _cannot("invalid potassium value")

    unit = latest.get("unit")
    if unit is not None:
        if not isinstance(unit, str):
            return _cannot("invalid potassium unit")
        normalized_unit = unit.strip().lower().replace(" ", "")
        if normalized_unit not in {"mmol/l", "mmol", "meq/l", "meq", "mmol/liter", "meq/liter"}:
            return _cannot("unexpected potassium unit")

    if value >= 3.5:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": None,
        }

    deficit = Decimal("3.5") - Decimal(str(value))
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
