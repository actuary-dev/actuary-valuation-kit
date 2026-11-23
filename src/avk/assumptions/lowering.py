"""Lowering: validated contexts, prepared model points and scenarios into kernel arrays.

Names, keys and rules are resolved here, once per run and vectorised over policies; the
kernel receives only numbers in its layout. Product-generic: everything
comes from the kernel's layout and the binding rules in its IR.
"""

from collections.abc import Mapping

import numpy as np
import numpy.typing as npt
import polars as pl

from avk.assumptions.context import AssumptionContext
from avk.model.data import Axis, ModelPoints, ScenarioSet, Table
from avk.model.executor import KernelInputs
from avk.model.kernel import Kernel
from avk.model.lang import AxisRule
from avk.runtime.errors import InputError, KernelError


def _field(frame: pl.DataFrame, name: str) -> npt.NDArray[np.float64]:
    if name not in frame.columns:
        raise InputError(f"model points lack the field {name}")
    column = frame[name]
    if not column.dtype.is_numeric() or column.null_count():
        raise InputError(f"model-point field {name} must be numeric and present for every policy")
    return np.asarray(column.cast(pl.Float64).to_numpy(), dtype=np.float64)


def _dense(
    values: npt.NDArray[np.float64], axis: Axis, rule: AxisRule, table: str
) -> npt.NDArray[np.int64]:
    """Each policy's key as the table's dense index; unmatched keys follow the binding rule."""
    raw = np.asarray(axis.keys)
    if raw.dtype.kind not in "iuf":
        raise KernelError(f"{table}: keymap axis '{axis.name}' has non-numeric keys")
    keys = raw.astype(np.float64)
    order = np.argsort(keys, kind="stable")
    position = np.searchsorted(keys[order], values).clip(0, len(keys) - 1)
    index: npt.NDArray[np.int64] = order[position].astype(np.int64)
    matched = keys[index] == values
    if matched.all():
        return index
    above = values > keys.max()
    if rule.above == "clamp":
        index = np.where(above, int(np.argmax(keys)), index)
    elif rule.above == "zero":
        index = np.where(above, -1, index)
    handled = matched | (above & (rule.above != "error"))
    if rule.unknown == "first":
        index = np.where(handled, index, 0)
        handled[:] = True
    if not handled.all():
        missing = sorted(set(values[~handled].tolist()))
        raise InputError(f"{table}: {rule.field} values {missing} are not keys of the table")
    return index


def _table(
    name: str, rules: tuple[AxisRule, ...], contexts: Mapping[str, AssumptionContext]
) -> Table:
    held = [ctx.tables[name].table for ctx in contexts.values() if name in ctx.tables]
    if not held:
        raise KernelError(f"no assumption context holds the table {name}")
    table = held[0]
    if any(
        other is not table
        and (other.axes != table.axes or not np.array_equal(other.values, table.values))
        for other in held
    ):
        raise KernelError(f"{name}: per-basis table values differ; one table per kernel")
    kinds = tuple(axis.kind for axis in table.axes)
    if kinds != tuple(rule.kind for rule in rules):
        raise KernelError(f"{name}: loaded axes {kinds} do not match the formula binding")
    return table


def lower(
    contexts: Mapping[str, AssumptionContext],
    points: ModelPoints[pl.DataFrame],
    scenarios: ScenarioSet,
    kernel: Kernel,
    run_params: Mapping[str, float | npt.NDArray[np.float64]],
) -> KernelInputs:
    """`run_params` are the run type's parameters; the kernel takes those its formulas read."""
    layout = kernel.layout
    frame = points.frame
    missing = [basis for basis in layout.bases if basis not in contexts]
    if missing:
        raise KernelError(f"no assumption context for bases {missing}")
    unset = [name for name in layout.run_params if name not in run_params]
    if unset:
        raise KernelError(f"the run type sets no value for the run parameters {unset}")
    tables = {name: _table(name, rules, contexts) for name, rules in layout.tables}
    rules = dict(layout.tables)
    keys = {}
    for name, axis in layout.keymaps:
        rule = rules[name][axis]
        keys[(name, axis)] = _dense(_field(frame, rule.field), tables[name].axes[axis], rule, name)
    params = {
        basis: np.array(
            [contexts[basis].params[name] for owner, name in layout.params if owner == basis],
            dtype=np.float64,
        )
        for basis in layout.bases
    }
    paths, months = next(iter(scenarios.variables.values())).shape
    curves = {}
    for name, _ in layout.curves:
        if name in layout.monthly_params:
            if name not in run_params:
                raise KernelError(f"the run type sets no value for monthly run parameter {name}")
            values = np.asarray(run_params[name], dtype=np.float64)
            if values.shape != (months,) or not np.isfinite(values).all():
                raise KernelError(f"{name}: monthly run parameter needs {months} finite values")
            curves[name] = values
            continue
        held = [ctx.curves[name] for ctx in contexts.values() if name in ctx.curves]
        if not held:
            raise KernelError(f"no assumption context holds the curve {name}")
        curves[name] = held[0].schedule(months)
        if any(not np.array_equal(item.schedule(months), curves[name]) for item in held[1:]):
            raise KernelError(f"{name}: per-basis curve values differ; one curve per kernel")
    return KernelInputs(
        fields={name: _field(frame, name) for name in layout.fields},
        keys=keys,
        tables=tables,
        params=params,
        scenarios={name: scenarios.variables[name] for name in layout.scen_vars},
        policies=frame.height,
        paths=paths,
        months=months,
        run_params={name: float(run_params[name]) for name in layout.run_params},
        curves=curves,
    )
