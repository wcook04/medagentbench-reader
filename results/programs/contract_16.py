# Written by deepseek/deepseek-v4.1-flash-1017, condition "contract", seed 16. Unedited.
from datetime import datetime, timedelta, timezone
from decimal import Decimal

def _parse_dt(value):
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)

def _is_mmol_unit(unit):
    if unit is None:
        return True
    if isinstance(unit, str):
        u = unit.strip().lower().replace(" ", "")
        if u == "":
            return True
        return u in ("mmol/l", "mmol", "mmoll", "meq/l", "meq", "meql")
    return False

def plan(observations, now):
    now_dt = _parse_dt(now)
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=timezone.utc)

    counted = []
    for obs in observations:
        if obs.get("status") != "final":
            continue

        eff_str = obs.get("effectiveDateTime")
        if not eff_str:
            continue

        try:
            eff = _parse_dt(eff_str)
        except Exception:
            continue

        if eff.tzinfo is None:
            continue

        if eff > now_dt:
            continue

        if not _is_mmol_unit(obs.get("unit")):
            continue

        try:
            val = Decimal(str(obs.get("value")))
        except Exception:
            continue

        counted.append((eff, val))

    if not counted:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "no final potassium result at or before now",
        }

    latest_time = max(t for t, _ in counted)
    latest_values = [v for t, v in counted if t == latest_time]
    first_value = latest_values[0]

    if any(v != first_value for v in latest_values):
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "conflicting potassium values at most recent specimen time",
        }

    value = first_value
    threshold = Decimal("3.5")

    if value >= threshold:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": None,
        }

    dose = float((threshold - value) / Decimal("0.1") * Decimal("10"))

    offset = now_dt.utcoffset()
    tz = timezone(offset) if offset is not None else now_dt.tzinfo
    repeat_dt = datetime(
        now_dt.year,
        now_dt.month,
        now_dt.day,
        8,
        0,
        0,
        tzinfo=tz,
    ) + timedelta(days=1)

    return {
        "order_replacement": True,
        "dose_mEq": dose,
        "repeat_potassium_at": repeat_dt.isoformat(),
        "cannot_apply": None,
    }
