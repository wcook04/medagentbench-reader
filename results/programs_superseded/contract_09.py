# Written by deepseek/deepseek-v4.1-flash-1017, condition "contract", seed 9. Unedited.
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation


def plan(observations, now):
    def parse_dt(s):
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)

    now_dt = parse_dt(now)
    counted = []

    for obs in observations:
        if obs.get("status") != "final":
            continue
        try:
            specimen = parse_dt(obs["effectiveDateTime"])
            value = Decimal(str(obs["value"]))
        except (KeyError, TypeError, ValueError, InvalidOperation):
            continue
        if specimen <= now_dt:
            counted.append((specimen, value))

    if not counted:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "no final potassium result at or before now",
        }

    latest_time = max(t for t, _ in counted)
    latest_values = [v for t, v in counted if t == latest_time]

    if len(set(latest_values)) > 1:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "conflicting values at most recent specimen time",
        }

    value = latest_values[0]
    threshold = Decimal("3.5")

    if value >= threshold:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": None,
        }

    dose = (threshold - value) * Decimal("100")
    repeat_dt = (now_dt + timedelta(days=1)).replace(
        hour=8, minute=0, second=0, microsecond=0
    )

    return {
        "order_replacement": True,
        "dose_mEq": float(dose),
        "repeat_potassium_at": repeat_dt.isoformat(),
        "cannot_apply": None,
    }
