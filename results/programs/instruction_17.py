# Written by deepseek/deepseek-v4.1-flash-1017, condition "instruction", seed 17. Unedited.
def plan(observations, now):
    from datetime import datetime, timedelta
    import math

    def cannot_apply(reason):
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": reason,
        }

    if not observations:
        return cannot_apply("no potassium observations")

    try:
        now_dt = datetime.fromisoformat(now.replace("Z", "+00:00"))
    except Exception:
        return cannot_apply("invalid current time")

    candidates = []
    for index, obs in enumerate(observations):
        if not isinstance(obs, dict):
            continue

        status = obs.get("status")
        if status in ("cancelled", "entered-in-error"):
            continue

        effective = obs.get("effectiveDateTime")
        if not isinstance(effective, str):
            continue

        try:
            effective_dt = datetime.fromisoformat(effective.replace("Z", "+00:00"))
        except Exception:
            continue

        if effective_dt.tzinfo is None and now_dt.tzinfo is not None:
            effective_dt = effective_dt.replace(tzinfo=now_dt.tzinfo)

        candidates.append((effective_dt, index, obs))

    if not candidates:
        return cannot_apply("no usable potassium observation")

    latest = max(candidates, key=lambda item: (item[0], item[1]))[2]
    value = latest.get("value")

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return cannot_apply("most recent potassium value is not numeric")

    value = float(value)
    threshold = 3.5

    if value < threshold:
        deficit = threshold - value
        increments = math.ceil(deficit / 0.1 - 1e-9)
        if increments < 1:
            increments = 1
        dose = increments * 10

        repeat_dt = (now_dt + timedelta(days=1)).replace(
            hour=8, minute=0, second=0, microsecond=0
        )

        return {
            "order_replacement": True,
            "dose_mEq": dose,
            "repeat_potassium_at": repeat_dt.isoformat(),
            "cannot_apply": None,
        }

    return {
        "order_replacement": False,
        "dose_mEq": None,
        "repeat_potassium_at": None,
        "cannot_apply": None,
    }
