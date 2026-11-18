# Written by deepseek/deepseek-v4.1-flash-1017, condition "contract", seed 16. Unedited.
def plan(observations, now):
    from datetime import datetime, timedelta
    from decimal import Decimal

    def parse_dt(value):
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)

    now_dt = parse_dt(now)

    eligible = []
    for obs in observations:
        if obs.get("status") != "final":
            continue
        try:
            specimen_dt = parse_dt(obs.get("effectiveDateTime"))
            value = obs.get("value")
            if specimen_dt <= now_dt:
                eligible.append((specimen_dt, value))
        except Exception:
            continue

    if not eligible:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "no final potassium result at or before now",
        }

    latest_dt = max(dt for dt, _ in eligible)
    latest_values = [value for dt, value in eligible if dt == latest_dt]

    first_value = Decimal(str(latest_values[0]))
    for value in latest_values[1:]:
        if Decimal(str(value)) != first_value:
            return {
                "order_replacement": False,
                "dose_mEq": None,
                "repeat_potassium_at": None,
                "cannot_apply": "conflicting values at most recent specimen time",
            }

    threshold = Decimal("3.5")
    if first_value >= threshold:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": None,
        }

    dose_decimal = (threshold - first_value) * Decimal("100")
    if dose_decimal == dose_decimal.to_integral_value():
        dose = int(dose_decimal)
    else:
        dose = float(dose_decimal)

    next_day = now_dt + timedelta(days=1)
    repeat_dt = next_day.replace(hour=8, minute=0, second=0, microsecond=0)

    return {
        "order_replacement": True,
        "dose_mEq": dose,
        "repeat_potassium_at": repeat_dt.isoformat(),
        "cannot_apply": None,
    }
