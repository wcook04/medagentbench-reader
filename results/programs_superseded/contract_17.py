# Written by deepseek/deepseek-v4.1-flash-1017, condition "contract", seed 17. Unedited.
from datetime import datetime, timedelta, time
from decimal import Decimal


def plan(observations, now):
    def parse_dt(s):
        if s.endswith("Z") or s.endswith("z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)

    now_dt = parse_dt(now)
    counted = []

    for obs in observations:
        if obs.get("status") != "final":
            continue
        try:
            effective = parse_dt(obs["effectiveDateTime"])
            value = obs["value"]
            if effective <= now_dt:
                counted.append((effective, value))
        except Exception:
            continue

    result = {
        "order_replacement": False,
        "dose_mEq": None,
        "repeat_potassium_at": None,
        "cannot_apply": None,
    }

    if not counted:
        result["cannot_apply"] = "no final potassium result at or before now"
        return result

    latest_time = max(effective for effective, _ in counted)
    latest_values = [
        value for effective, value in counted if effective == latest_time
    ]

    value = latest_values[0]
    if any(v != value for v in latest_values[1:]):
        result["cannot_apply"] = "most recent potassium results have different values"
        return result

    value_decimal = Decimal(str(value))
    if value_decimal >= Decimal("3.5"):
        return result

    dose_decimal = (
        (Decimal("3.5") - value_decimal)
        / Decimal("0.1")
        * Decimal("10")
    )
    dose = float(dose_decimal)

    next_day = datetime.combine(
        (now_dt + timedelta(days=1)).date(),
        time(8, 0, 0),
        tzinfo=now_dt.tzinfo,
    )

    return {
        "order_replacement": True,
        "dose_mEq": dose,
        "repeat_potassium_at": next_day.isoformat(),
        "cannot_apply": None,
    }
