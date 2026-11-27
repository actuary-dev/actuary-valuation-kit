"""Deterministic scenario overlays and the supplied-scenario Parquet writer."""

import math
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from tempfile import NamedTemporaryFile

import numpy as np
import numpy.typing as npt
import polars as pl

from avk.esg.supplied import KEYS, WEIGHT, validate_weights
from avk.inputs.formats import FormatSpec
from avk.inputs.public_formats import numbers
from avk.model.data import ScenarioSet
from avk.runtime.errors import InputError, OutputError, reader_failure

type Placement = Mapping[str, npt.NDArray[np.bool_]]


def _names(base: ScenarioSet, variables: Sequence[str]) -> tuple[str, ...]:
    if (
        isinstance(variables, str)
        or not variables
        or any(not isinstance(name, str) or not name for name in variables)
    ):
        raise InputError("Variables must list one or more scenario variable names")
    names = tuple(variables)
    unknown = sorted(set(names) - base.variables.keys())
    if unknown:
        raise InputError(f"Unknown scenario variables {unknown}")
    if len(set(names)) != len(names):
        raise InputError("Variables must be unique")
    return names


def _finite(value: float, field: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise InputError(f"{field} must be a finite number")
    try:
        if math.isfinite(value):
            return float(value)
    except OverflowError:
        pass
    raise InputError(f"{field} must be a finite number")


def _valid_rates(values: npt.NDArray[np.float64], field: str) -> None:
    if not np.isfinite(values).all() or (values <= -1).any():
        raise InputError(f"{field}: effective rates must be finite and exceed -1")


def _placed(placement: Placement | None, name: str) -> slice | npt.NDArray[np.bool_]:
    # Without product timing information, months 1 onward are explicit rates.
    return slice(1, None) if placement is None else placement[name]


def flat(
    base: ScenarioSet,
    variables: Sequence[str],
    annual: float,
    *,
    placement: Placement | None = None,
) -> ScenarioSet:
    """Set a constant annual-effective rate on the selected projection months."""
    annual = _finite(annual, "Annual")
    if annual <= -1:
        raise InputError("Annual must exceed -1")
    monthly = math.expm1(math.log1p(annual) / 12)
    paths = dict(base.variables)
    for name in _names(base, variables):
        paths[name] = paths[name].copy()
        paths[name][:, _placed(placement, name)] = monthly
    return replace(base, variables=paths)


def shift(
    base: ScenarioSet,
    variables: Sequence[str],
    annual_change: float,
    *,
    placement: Placement | None = None,
) -> ScenarioSet:
    """Add the change in annual-effective space and restore monthly rates."""
    annual_change = _finite(annual_change, "Annual_Change")
    paths = dict(base.variables)
    for name in _names(base, variables):
        months = _placed(placement, name)
        rates = paths[name][:, months]
        _valid_rates(rates, f"Annual_Change for {name}")
        if annual_change:
            with np.errstate(over="ignore"):
                annual = np.expm1(12 * np.log1p(rates)) + annual_change
            _valid_rates(annual, f"Annual_Change for {name}")
            paths[name] = paths[name].copy()
            paths[name][:, months] = np.expm1(np.log1p(annual) / 12)
    return replace(base, variables=paths)


def shock(base: ScenarioSet, variables: Sequence[str], month: int, factor: float) -> ScenarioSet:
    """Multiply one month's gross return on the selected variables."""
    horizon = next(iter(base.variables.values())).shape[1]
    if isinstance(month, bool) or not isinstance(month, int) or not 0 <= month < horizon:
        raise InputError(f"Month must be an integer from 0 to {horizon - 1}")
    factor = _finite(factor, "Factor")
    if factor <= 0:
        raise InputError("Factor must be positive")
    paths = dict(base.variables)
    for name in _names(base, variables):
        if factor != 1:
            with np.errstate(over="ignore"):
                rates = (1 + paths[name][:, month]) * factor - 1
            _valid_rates(rates, f"Factor for {name}")
            paths[name] = paths[name].copy()
            paths[name][:, month] = rates
    return replace(base, variables=paths)


def custom(base: ScenarioSet, path: Path) -> ScenarioSet:
    """Replace the CSV's variable columns on every path, keyed by projection month."""
    where = f"Custom path {path}"
    try:
        frame = pl.read_csv(path, infer_schema_length=None)
        if "Month" not in frame.columns or not frame.schema["Month"].is_integer():
            raise InputError(f"{where}: Month must be an integer column")
        names = _names(base, [name for name in frame.columns if name != "Month"])
        frame = frame.sort("Month")
        count, horizon = next(iter(base.variables.values())).shape
        if (
            frame.height != horizon
            or frame["Month"].null_count()
            or not np.array_equal(frame["Month"].to_numpy(), np.arange(horizon))
        ):
            raise InputError(f"{where}: require months 0 to {horizon - 1}, once each")
        spec = FormatSpec(where, {"path": str(path)}, (), names, "", horizon, "mixed")
        rates = numbers(frame, names, spec)
        _valid_rates(rates, where)
    except (OSError, ValueError, pl.exceptions.PolarsError) as exc:
        raise InputError(reader_failure("Custom path", path, exc)) from exc
    updated = {
        name: np.broadcast_to(rates[:, column], (count, horizon))
        for column, name in enumerate(names)
    }
    return replace(base, variables={**base.variables, **updated})


def _integer_column(values: tuple[int, ...], name: str) -> npt.NDArray[np.integer]:
    try:
        dtype = np.int64 if min(values) < 0 else np.uint64
        return np.asarray(values, dtype=dtype)
    except OverflowError as exc:
        raise InputError(f"{name} values do not fit in a Parquet integer column") from exc


def write_parquet(scenarios: ScenarioSet, path: Path) -> Path:
    """Write a rectangular scenario set for SuppliedScenarios."""
    count, horizon = next(iter(scenarios.variables.values())).shape
    validate_weights(scenarios.weights, "Scenario Parquet")
    reserved = (*KEYS, WEIGHT)
    if scenarios.variables.keys() & set(reserved):
        raise InputError(f"Scenario variables cannot use the reserved Parquet columns {reserved}")
    ids: tuple[int, ...]
    if scenarios.ids == ("deterministic",):
        ids = (1,)
    else:
        try:
            ids = tuple(int(label) for label in scenarios.ids)
        except ValueError as exc:
            raise InputError("Scenario Parquet requires integer ids") from exc
        if tuple(map(str, sorted(ids))) != scenarios.ids:
            raise InputError("Scenario Parquet requires canonical integer ids in ascending order")
    seeds = scenarios.seeds
    if not seeds:
        if scenarios.ids != ("deterministic",):
            raise InputError("Scenario Parquet requires one Seed per scenario")
        seeds = (0,)
    weights = (
        {}
        if np.all(scenarios.weights == 1 / count)
        else {WEIGHT: np.repeat(scenarios.weights, horizon)}
    )
    frame = pl.DataFrame(
        {
            "Scenario": np.repeat(_integer_column(ids, "Scenario"), horizon),
            "Seed": np.repeat(_integer_column(seeds, "Seed"), horizon),
            "Month": np.tile(np.arange(horizon, dtype=np.int64), count),
            **weights,
            **{name: values.ravel() for name, values in scenarios.variables.items()},
        }
    )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=path.parent, prefix=".avk-", delete=False) as stream:
            temporary = Path(stream.name)
        try:
            frame.write_parquet(temporary)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    except (OSError, pl.exceptions.PolarsError) as exc:
        raise OutputError(f"Cannot write scenario file {path}: {exc}") from exc
    return path
