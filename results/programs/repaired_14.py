# Written by deepseek/deepseek-v4.1-flash-1017: "instruction" seed 14, then 4 round(s) of counterexample feedback. Unedited.
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_CEILING
import math


def plan(observations, now):
    def _parse_iso(value):
        if not isinstance(value, str):
            return None
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    def _cannot(message):
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": message,
        }

    def _no_action():
        return {
            "order_replacement": False,
            "dose_mEq": None,
            "repeat_potassium_at": None,
            "cannot_apply": None,
        }

    now_dt = _parse_iso(now)
    if now_dt is None:
        return _cannot("invalid now")

    if not isinstance(observations, list):
        return _cannot("observations not a list")

    ignored_statuses = {"entered-in-error", "cancelled"}

    parsed = []
    for obs in observations:
        if not isinstance(obs, dict):
            continue

        status = obs.get("status")
        if isinstance(status, str) and status.strip().lower() in ignored_statuses:
            continue

        effective = _parse_iso(obs.get("effectiveDateTime"))
        if effective is None:
            continue

        try:
            if effective > now_dt:
                continue
        except TypeError:
            continue

        parsed.append((effective, obs))

    if not parsed:
        return _cannot("no potassium observations at or before now")

    max_effective = max(effective for effective, _ in parsed)
    latest_group = [obs for effective, obs in parsed if effective == max_effective]

    def _status_ok(obs):
        status = obs.get("status")
        return isinstance(status, str) and status.strip().lower() in {
            "final",
            "amended",
            "corrected",
        }

    acceptable = [obs for obs in latest_group if _status_ok(obs)]
    if not acceptable:
        return _cannot("most recent potassium is not final")

    def _valid_value(obs):
        value = obs.get("value")
        return (
            not isinstance(value, bool)
            and isinstance(value, (int, float))
            and math.isfinite(value)
        )

    value_obs = [obs for obs in acceptable if _valid_value(obs)]
    if not value_obs:
        return _cannot("invalid potassium value")

    def _normalized_unit(obs):
        unit = obs.get("unit")
        if unit is None:
            return "mmol/l"
        if not isinstance(unit, str):
            return None

        normalized = unit.strip().lower().replace(" ", "")
        if normalized in {
            "mmol/l",
            "mmol",
            "meq/l",
            "meq",
            "mmol/liter",
            "meq/liter",
        }:
            return normalized
        return None

    unit_obs = []
    for obs in value_obs:
        normalized = _normalized_unit(obs)
        if normalized is not None:
            unit_obs.append((obs, normalized))

    if not unit_obs:
        return _cannot("missing or invalid potassium unit")

    distinct_values = {}
    for obs, _ in unit_obs:
        try:
            decimal_value = Decimal(str(obs["value"]))
        except Exception:
            continue
        distinct_values[decimal_value] = obs

    if not distinct_values:
        return _cannot("invalid potassium value")

    if len(distinct_values) > 1:
        return _cannot("conflicting most recent potassium observations")

    chosen_value = next(iter(distinct_values.values()))["value"]

    if chosen_value >= 3.5:
        return _no_action()

    deficit = Decimal("3.5") - Decimal(str(chosen_value))
    steps = (deficit / Decimal("0.1")).to_integral_value(rounding=ROUND_CEILING)
    dose = int(steps) * 10

    repeat_dt = (now_dt + timedelta(days=1)).replace(
        hour=8, minute=0, second=0, microsecond=0
    )

    return {
        "order_replacement": True,
        "dose_mEq": dose,
        "repeat_potassium_at": repeat_dt.isoformat(),
        "cannot_apply": None,
    }
