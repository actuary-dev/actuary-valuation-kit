"""Registered vectorized readers with explicit lookup rules and no numeric defaults."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import cache
from importlib.metadata import EntryPoint, entry_points
from pathlib import Path
from typing import Literal, cast

import numpy as np
import polars as pl

from avk.model.data import Axis, Table
from avk.runtime.errors import InputError, reader_failure
from avk.runtime.progress import fingerprint


@dataclass(frozen=True)
class FormatSpec:
    name: str
    source: Mapping[str, str]
    axes: tuple[Axis, ...]
    columns: tuple[str, ...]
    product: str
    projection_months: int
    units: Literal["probability", "fraction", "amount", "annual_effective", "mixed"]


READERS: dict[str, Callable[[pl.DataFrame, FormatSpec], Table]] = {}


def register(name: str, reader: Callable[[pl.DataFrame, FormatSpec], Table]) -> None:
    if name in READERS:
        raise ValueError(f"Format already registered: {name}")
    READERS[name] = reader


@cache
def _installed_formats() -> dict[str, tuple[EntryPoint, ...]]:
    """Discover once per process; import only the format selected by the input registry."""
    grouped: dict[str, list[EntryPoint]] = {}
    for point in entry_points(group="avk.formats"):
        grouped.setdefault(point.name, []).append(point)
    return {name: tuple(points) for name, points in grouped.items()}


def _resolve_reader(name: str, spec: FormatSpec) -> Callable[[pl.DataFrame, FormatSpec], Table]:
    from avk.inputs.public_formats import PUBLIC_READERS

    readers = {**READERS, **PUBLIC_READERS}
    candidates = _installed_formats().get(name, ())
    if candidates and name in readers:
        raise InputError(f"{spec.name}: format {name!r} conflicts with a built-in reader")
    if len(candidates) > 1:
        raise InputError(f"{spec.name}: ambiguous installed format {name!r}")
    if candidates:
        try:
            selected = candidates[0].load()
        except Exception as exc:
            raise InputError(f"{spec.name}: cannot load format {name!r}: {exc}") from exc
        if not callable(selected):
            raise InputError(f"{spec.name}: format {name!r} must be callable")
        return cast(Callable[[pl.DataFrame, FormatSpec], Table], selected)
    try:
        return readers[name]
    except KeyError as exc:
        raise InputError(f"{spec.name}: unknown format {name!r}") from exc


def read(name: str, frame: pl.DataFrame, spec: FormatSpec) -> Table:
    reader = _resolve_reader(name, spec)
    try:
        result = reader(frame, spec)
    except (ValueError, TypeError, KeyError, pl.exceptions.PolarsError) as exc:
        raise InputError(
            reader_failure(spec.name, Path(spec.source.get("path", spec.name)), exc)
        ) from exc
    if not isinstance(result, Table):
        raise InputError(f"{spec.name}: format {name!r} must return a Table")
    return result


def numeric(frame: pl.DataFrame, columns: tuple[str, ...], spec: FormatSpec) -> np.ndarray:
    missing = set(columns) - set(frame.columns)
    if missing:
        raise InputError(f"{spec.name}: missing columns {sorted(missing)}")
    values = frame.select(
        pl.col(c).cast(pl.String).str.replace_all(",", "").str.strip_chars_end("%").cast(pl.Float64)
        for c in columns
    ).to_numpy()
    if not np.isfinite(values).all():
        raise InputError(f"{spec.name}: missing or non-finite numeric value")
    if spec.units == "probability" and ((values < 0) | (values > 1)).any():
        raise InputError(
            f"{spec.name}: probability must be between 0 and 1 (100%); invalid table rate"
        )
    if spec.units == "annual_effective" and (values <= -1).any():
        raise InputError(f"{spec.name}: annual interest rates must exceed -1")
    return values


def unique(frame: pl.DataFrame, keys: list[str], spec: FormatSpec) -> None:
    if frame.is_empty() or frame.select(keys).null_count().to_numpy().any():
        raise InputError(f"{spec.name}: empty table or missing key {keys}")
    if frame.select(keys).is_duplicated().any():
        raise InputError(f"{spec.name}: duplicate keys {keys}")


def numeric_keys(frame: pl.DataFrame, keys: list[str], spec: FormatSpec) -> pl.DataFrame:
    """Normalize before grouping/sorting so labels and numeric payloads cannot diverge."""
    frame = frame.with_columns(
        pl.col(key).cast(pl.String).str.replace_all(",", "").cast(pl.Float64) for key in keys
    )
    if not np.isfinite(frame.select(keys).to_numpy()).all():
        raise InputError(f"{spec.name}: numeric keys must be present and finite: {keys}")
    return frame


def key_axis(name: str, keys: tuple[str | int | float, ...]) -> Axis:
    return Axis(name, "keymap", None, len(keys), None, "error", keys, "error")


def integer_axis(name: str, start: int, size: int, rule: Axis) -> Axis:
    return Axis(name, "int", start, size, rule.below, rule.above, (), None)


def table(spec: FormatSpec, values: np.ndarray, axes: tuple[Axis, ...]) -> Table:
    return Table(spec.name, axes, values, spec.source)


def read_csv_format(path: str, format_name: str, name: str) -> Table:
    """Use the same hook for run-level tables as for assumption tables."""
    spec = FormatSpec(name, {"path": path}, (), (), "", 0, "mixed")
    try:
        fingerprint(Path(path))
        return read(format_name, pl.read_csv(path, infer_schema_length=None), spec)
    except (OSError, pl.exceptions.PolarsError) as exc:
        raise InputError(reader_failure(name, Path(path), exc)) from exc
