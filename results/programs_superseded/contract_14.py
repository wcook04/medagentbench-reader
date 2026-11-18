# Written by deepseek/deepseek-v4.1-flash-1017, condition "contract", seed 14. Unedited.
from datetime import datetime, timedelta, time
from decimal import Decimal

def plan(observations, now):
    def parse_iso(value):
        if isinstance(value, str) and value.endswith(("Z", "z")):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)

    now_dt = parse_iso(now)
    counted = []

    for obs in observations:
        if str(obs.get("status", "")).lower() != "final":
            continue
        try:
            effective = parse_iso(obs["effectiveDateTime"])
        except Exception:
            continue
        if effective <= now_dt:
            counted.append((effective, obs.get("value")))

    if not counted:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "no final potassium results at or before now",
        }

    latest_time = max(effective for effective, _ in counted)
    latest_values = [value for effective, value in counted if effective == latest_time]

    if any(value is None for value in latest_values):
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "most recent potassium result has no value",
        }

    if len(set(latest_values)) > 1:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "conflicting values at most recent specimen time",
        }

    value = latest_values[0]

    if value < 3.5:
        difference = Decimal("3.5") - Decimal(str(value))
        dose = difference / Decimal("0.1") * Decimal("10")
        next_date = now_dt.date() + timedelta(days=1)
        repeat_dt = datetime.combine(next_date, time(8, 0, 0)).replace(tzinfo=now_dt.tzinfo)

        return {
            "order_replacement": True,
            "dose_mEq": float(dose),
            "repeat_potassium_at": repeat_dt.isoformat(timespec="seconds"),
            "cannot_apply": None,
        }

    return {
        "order_replacement": False,
        "dose_mEq": None,
        "repeat_potassium_at": None,
        "cannot_apply": None,
    }
