"""Public error taxonomy; stdlib only. Library code raises instead of exiting."""

import re
from pathlib import Path


class AvkError(Exception):
    """Base class for errors reported to a Actuary Valuation Kit user."""


class ConfigError(AvkError):
    """A configuration is missing, unknown or invalid."""


class InputError(AvkError):
    """Input data is invalid; messages identify its table, row and column."""


class FormulaError(AvkError):
    """A formula is invalid; messages identify its component and source location."""


class KernelError(AvkError):
    """Kernel compilation or execution failed."""


class OutputError(AvkError):
    """Writing or publishing projection output failed."""


def reader_failure(name: str, path: Path, error: BaseException, line: int | None = None) -> str:
    """Retain reader coordinates and type, never its data-bearing diagnostic text."""
    coordinate = ""
    for attr, label in (("lineno", "line"), ("line", "line"), ("row", "row")):
        value = getattr(error, attr, None)
        if isinstance(value, int):
            coordinate = f"; {label} {value}"
            break
    if not coordinate:
        mark = getattr(error, "problem_mark", None)
        value = getattr(mark, "line", None)
        if isinstance(value, int):
            coordinate = f"; line {value + 1}"
    if not coordinate:
        match = re.search(r"(?i)\b(?:at|on|in) (line|row)(?: number)?[: ]+(\d+)", str(error))
        if match:
            coordinate = f"; {match[1].lower()} {int(match[2])}"
        elif line is not None:
            coordinate = f"; line {line}"
    return f"{name}: cannot read {path}: {type(error).__name__}{coordinate}"
