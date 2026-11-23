"""Shared number parsing for run-file values."""

import math

from avk.runtime.errors import ConfigError


def finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ConfigError(f"{label}: expected a finite number")
    try:
        number = float(value)
    except ValueError as exc:
        raise ConfigError(f"{label}: expected a finite number") from exc
    if not math.isfinite(number):
        raise ConfigError(f"{label}: expected a finite number")
    return number
