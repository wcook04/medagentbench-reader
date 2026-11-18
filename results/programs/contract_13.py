# Written by deepseek/deepseek-v4.1-flash-1017, condition "contract", seed 13. Unedited.
from datetime import datetime, time, timedelta
from decimal import Decimal


def _parse_dt(value):
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith("Z") or text.endswith("z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def plan(observations, now):
    now_dt = _parse_dt(now)
    if now_dt is None:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "invalid now timestamp",
        }

    counted = []
    for obs in observations or []:
        if obs.get("status") != "final":
            continue

        specimen_dt = _parse_dt(obs.get("effectiveDateTime"))
        if specimen_dt is None:
            continue
        if specimen_dt > now_dt:
            continue

        try:
            value = Decimal(str(obs.get("value")))
        except Exception:
            continue

        counted.append((specimen_dt, value))

    if not counted:
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "no eligible final potassium results at or before now",
        }

    latest_dt = max(dt for dt, _ in counted)
    latest_values = [value for dt, value in counted if dt == latest_dt]

    first_value = latest_values[0]
    if any(value != first_value for value in latest_values[1:]):
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": "ambiguous most recent potassium results",
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

    dose_dec = (threshold - value) * Decimal("100")
    if dose_dec == dose_dec.to_integral_value():
        dose = int(dose_dec)
    else:
        dose = float(dose_dec)

    next_date = now_dt.date() + timedelta(days=1)
    repeat_dt = datetime.combine(next_date, time(8, 0, 0), tzinfo=now_dt.tzinfo)

    return {
        "order_replacement": True,
        "dose_mEq": dose,
        "repeat_potassium_at": repeat_dt.isoformat(),
        "cannot_apply": None,
    }
