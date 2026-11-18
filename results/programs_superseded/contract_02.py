# Written by deepseek/deepseek-v4.1-flash-1017, condition "contract", seed 2. Unedited.
import datetime as _dt
from decimal import Decimal


def plan(observations, now):
    def parse_iso(value):
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return _dt.datetime.fromisoformat(value)

    now_dt = parse_iso(now)

    counted = []
    for obs in observations:
        if obs.get("status") != "final":
            continue
        effective = parse_iso(obs["effectiveDateTime"])
        if effective <= now_dt:
            counted.append((effective, Decimal(str(obs["value"]))))

    if not counted:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "no final potassium result at or before now",
        }

    latest_time = max(effective for effective, _ in counted)
    latest_values = [value for effective, value in counted if effective == latest_time]

    first_value = latest_values[0]
    if any(value != first_value for value in latest_values[1:]):
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "conflicting potassium values at most recent specimen time",
        }

    potassium = first_value

    if potassium >= Decimal("3.5"):
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": None,
        }

    dose_decimal = (Decimal("3.5") - potassium) * Decimal("100")
    if dose_decimal == dose_decimal.to_integral_value():
        dose_mEq = int(dose_decimal)
    else:
        dose_mEq = float(dose_decimal)

    next_date = now_dt.date() + _dt.timedelta(days=1)
    repeat_dt = _dt.datetime.combine(
        next_date,
        _dt.time(8, 0, 0),
        tzinfo=now_dt.tzinfo,
    )

    return {
        "order_replacement": True,
        "dose_mEq": dose_mEq,
        "repeat_potassium_at": repeat_dt.isoformat(),
        "cannot_apply": None,
    }
