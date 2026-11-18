# Written by deepseek/deepseek-v4.1-flash-1017, condition "contract", seed 15. Unedited.
import datetime as _dt
from decimal import Decimal


def _parse_iso(value):
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return _dt.datetime.fromisoformat(value)


def plan(observations, now):
    now_dt = _parse_iso(now)

    candidates = []
    for obs in observations:
        if obs.get("status") != "final":
            continue

        specimen_dt = _parse_iso(obs["effectiveDateTime"])
        if specimen_dt <= now_dt:
            candidates.append((specimen_dt, obs["value"]))

    def cannot_apply(reason):
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": reason,
        }

    if not candidates:
        return cannot_apply("no final potassium result at or before now")

    most_recent_time = max(specimen_dt for specimen_dt, _ in candidates)
    values = [
        value for specimen_dt, value in candidates
        if specimen_dt == most_recent_time
    ]

    first_value = values[0]
    if any(value != first_value for value in values[1:]):
        return cannot_apply("conflicting values at most recent specimen time")

    level = first_value
    threshold = Decimal("3.5")
    level_dec = Decimal(str(level))

    if level_dec >= threshold:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": None,
        }

    dose = (threshold - level_dec) * Decimal("100")
    repeat_at = (now_dt + _dt.timedelta(days=1)).replace(
        hour=8, minute=0, second=0, microsecond=0
    )

    return {
        "order_replacement": True,
        "dose_mEq": float(dose),
        "repeat_potassium_at": repeat_at.isoformat(),
        "cannot_apply": None,
    }
