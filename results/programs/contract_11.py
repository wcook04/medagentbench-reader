# Written by deepseek/deepseek-v4.1-flash-1017, condition "contract", seed 11. Unedited.
def plan(observations, now):
    from datetime import datetime, timedelta
    from decimal import Decimal

    def parse_dt(s):
        if isinstance(s, str) and s[-1:] in ("Z", "z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)

    now_dt = parse_dt(now)

    counted = []
    for obs in observations:
        if obs.get("status") != "final":
            continue
        when = obs.get("effectiveDateTime")
        if when is None:
            continue
        try:
            specimen_dt = parse_dt(when)
        except Exception:
            continue
        if specimen_dt <= now_dt:
            counted.append((specimen_dt, obs.get("value")))

    if not counted:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "no qualifying potassium result",
        }

    latest_time = max(dt for dt, _ in counted)
    latest_values = [value for dt, value in counted if dt == latest_time]

    first_value = latest_values[0]
    for value in latest_values[1:]:
        if value != first_value:
            return {
                "order_replacement": False,
                "dose_mEq": None,
                "repeat_potassium_at": None,
                "cannot_apply": "ambiguous most recent potassium result",
            }

    try:
        value_dec = Decimal(str(first_value))
    except Exception:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "invalid potassium value",
        }

    threshold = Decimal("3.5")
    if value_dec >= threshold:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": None,
        }

    dose_dec = (threshold - value_dec) / Decimal("0.1") * Decimal("10")
    if dose_dec == dose_dec.to_integral_value():
        dose = int(dose_dec)
    else:
        dose = float(dose_dec)

    repeat_dt = (now_dt + timedelta(days=1)).replace(
        hour=8, minute=0, second=0, microsecond=0
    )

    return {
        "order_replacement": True,
        "dose_mEq": dose,
        "repeat_potassium_at": repeat_dt.isoformat(),
        "cannot_apply": None,
    }
