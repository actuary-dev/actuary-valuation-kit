"""The explicit-input executor: arrays in, projections out.

`project(kernel, inputs, request)` reads only its arguments. It packs the named inputs in the
kernel's layout order, runs the drivers over work items (scenario, logical block of `BLOCK`
policies in input order) batch by batch, and adds the blocks in block order. Every month of
every policy is computed. Threads, batch sizes and tiles never change a bit.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

import numpy as np
import numpy.typing as npt

from avk.model.data import Table
from avk.model.emit.common import BLOCK
from avk.model.kernel import Kernel

Array = npt.NDArray[np.float64]
# Scratch per thread for scenario-dependent columns that sizes the default scenario tile.
TILE_BYTES = 4 * 1024 * 1024


def _floats(value: npt.ArrayLike) -> Array:
    array = np.array(value, dtype=np.float64, order="C", copy=True)
    array.flags.writeable = False
    return array


def _indices(value: npt.ArrayLike) -> npt.NDArray[np.int64]:
    array = np.array(value, dtype=np.int64, order="C", copy=True)
    array.flags.writeable = False
    return array


@dataclass(frozen=True)
class KernelInputs:
    """Everything a kernel reads, as read-only arrays named by the kernel's layout.

    `fields` are per-policy float64 vectors; `keys` the dense keymap indices per
    `(table, axis)`; `tables` the loaded tables; `params` one float64 vector per basis, in the
    layout's order for that basis; `scenarios` the reached `(S, M)` scenario variables;
    `run_params` the run type's parameters by name (the kernel reads those its layout lists);
    `curves` the monthly schedules by name, each a nonempty float64 vector.
    """

    fields: Mapping[str, Array]
    keys: Mapping[tuple[str, int], npt.NDArray[np.int64]]
    tables: Mapping[str, Table]
    params: Mapping[str, Array]
    scenarios: Mapping[str, Array]
    policies: int
    paths: int
    months: int
    run_params: Mapping[str, float] = field(default_factory=dict)
    curves: Mapping[str, Array] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.policies < 0 or self.paths < 1 or self.months < 1:
            raise ValueError("KernelInputs need policies >= 0, paths >= 1 and months >= 1")
        fields = {name: _floats(value) for name, value in self.fields.items()}
        keys = {name: _indices(value) for name, value in self.keys.items()}
        shapes = [(name, value.shape) for name, value in fields.items()]
        shapes += [(f"{table}/{axis}", value.shape) for (table, axis), value in keys.items()]
        for label, shape in shapes:
            if shape != (self.policies,):
                raise ValueError(f"{label}: expected one value per policy")
        scenarios = {name: _floats(value) for name, value in self.scenarios.items()}
        for name, value in scenarios.items():
            if value.shape != (self.paths, self.months):
                raise ValueError(f"{name}: expected shape {(self.paths, self.months)}")
        params = {name: _floats(value) for name, value in self.params.items()}
        curves = {name: _floats(value) for name, value in self.curves.items()}
        for name, value in curves.items():
            if value.ndim != 1 or not value.size:
                raise ValueError(f"{name}: a curve is a nonempty vector")
        object.__setattr__(self, "curves", MappingProxyType(curves))
        object.__setattr__(self, "fields", MappingProxyType(fields))
        object.__setattr__(self, "keys", MappingProxyType(keys))
        object.__setattr__(self, "tables", MappingProxyType(dict(self.tables)))
        object.__setattr__(self, "params", MappingProxyType(params))
        object.__setattr__(self, "scenarios", MappingProxyType(scenarios))
        run_params = {name: float(value) for name, value in self.run_params.items()}
        object.__setattr__(self, "run_params", MappingProxyType(run_params))


@dataclass(frozen=True)
class OutputRequest:
    """What a projection returns: aggregates by column label, one-value-per-policy slices at
    `(label, step)`, per-policy-month grids by label (every column when `diagnostics`), and
    the policies per `on_batch` call (None: one batch; it never changes a number)."""

    aggregate: tuple[str, ...] = ()
    slices: tuple[tuple[str, int], ...] = ()
    grids: tuple[str, ...] = ()
    diagnostics: bool = False
    batch_size: int | None = None


@dataclass(frozen=True)
class Batch:
    """One batch's per-policy-month grids `(S, len(columns), stop - start, M)`."""

    start: int
    stop: int
    columns: tuple[str, ...]
    grids: Array


@dataclass(frozen=True)
class Projection:
    aggregate: Array  # (S, len(request.aggregate), M)
    slices: Array  # (S, len(request.slices), P)
    grid_columns: tuple[str, ...] = ()
    grids: Array | None = field(default=None)  # (S, ngrid, P, M) when no on_batch is given


def _grid_columns(kernel: Kernel, request: OutputRequest) -> tuple[str, ...]:
    if not request.diagnostics:
        return request.grids
    return request.grids + tuple(c for c in kernel.columns if c not in request.grids)


def _rows(kernel: Kernel, labels: tuple[str, ...], what: str) -> npt.NDArray[np.int64]:
    unknown = [label for label in labels if label not in kernel.columns]
    if unknown:
        raise ValueError(f"{what}: unknown kernel columns {unknown}")
    return np.array([kernel.columns.index(label) for label in labels], dtype=np.int64)


def _pack(kernel: Kernel, inputs: KernelInputs) -> tuple[object, ...]:
    layout, n = kernel.layout, inputs.policies
    missing = [name for name in layout.fields if name not in inputs.fields]
    missing += [name for name, _ in layout.tables if name not in inputs.tables]
    missing += [name for name in layout.scen_vars if name not in inputs.scenarios]
    missing += [f"{t}/{a}" for t, a in layout.keymaps if (t, a) not in inputs.keys]
    missing += [basis for basis in layout.bases if basis not in inputs.params]
    missing += [name for name in layout.run_params if name not in inputs.run_params]
    missing += [name for name, _ in layout.curves if name not in inputs.curves]
    if missing:
        raise ValueError(f"inputs lack {missing}")
    for name in layout.monthly_params:
        values = inputs.curves[name]
        if values.shape != (inputs.months,) or not np.isfinite(values).all():
            raise ValueError(f"{name}: monthly run parameter needs {inputs.months} finite values")
    fld = np.empty((len(layout.fields), n))
    for j, name in enumerate(layout.fields):
        fld[j] = inputs.fields[name]
    key = np.empty((len(layout.keymaps), n), dtype=np.int64)
    for j, keymap in enumerate(layout.keymaps):
        key[j] = inputs.keys[keymap]
    ist = np.array(
        [inputs.tables[name].axes[axis].start for name, axis in layout.starts], dtype=np.int64
    )
    prm = np.concatenate(
        [np.empty(0), *(inputs.params[basis] for basis in layout.bases)], dtype=np.float64
    )
    if prm.shape != (len(layout.params),):
        raise ValueError(f"expected {len(layout.params)} parameters, got {prm.shape[0]}")
    run = np.array([inputs.run_params[name] for name in layout.run_params], dtype=np.float64)
    prm = np.concatenate([prm, run])
    scn = np.empty((len(layout.scen_vars), inputs.paths, inputs.months))
    for j, name in enumerate(layout.scen_vars):
        scn[j] = inputs.scenarios[name]
    tables = tuple(np.array(inputs.tables[name].values, order="C") for name, _ in layout.tables)
    curves = tuple(inputs.curves[name] for name, _ in layout.curves)
    return (fld, key, ist, prm, scn, *tables, *curves, inputs.months)


def project(
    kernel: Kernel,
    inputs: KernelInputs,
    request: OutputRequest,
    *,
    tile: int | None = None,
    on_batch: Callable[[Batch], None] | None = None,
    scenario_tile: int | None = None,
    aggregate: Array | None = None,
) -> Projection:
    """Project every policy and scenario; aggregates are summed in logical blocks.

    On the CPU one physical tile is one policy per thread; `tile` is reserved for the GPU
    driver and must be None or positive. Scenario-dependent columns are computed for
    `scenario_tile` scenarios at a time (default: as many as `TILE_BYTES` of scratch per
    thread holds); neither tile changes a number. `on_batch` receives each batch's grids as
    new arrays; without it the grids of the whole book are returned.
    An optional writable float64 aggregate is continued in place, adding each logical
    block in order. Callers must pass consecutive input chunks starting on BLOCK
    boundaries (only the last chunk may end in a partial block).
    """
    if tile is not None and tile < 1:
        raise ValueError("tile must be None or a positive number of policies")
    if scenario_tile is not None and scenario_tile < 1:
        raise ValueError("scenario_tile must be None or a positive number of scenarios")
    if request.batch_size is not None and request.batch_size < 1:
        raise ValueError("batch_size must be None or positive")
    out_idx = _rows(kernel, request.aggregate, "aggregate")
    grid_columns = _grid_columns(kernel, request)
    grid_idx = _rows(kernel, grid_columns, "grids")
    sel_idx = _rows(kernel, tuple(label for label, _ in request.slices), "slices")
    sel_step = np.array([step for _, step in request.slices], dtype=np.int64)
    S, M, P = inputs.paths, inputs.months, inputs.policies
    if ((sel_step < 0) | (sel_step >= M)).any():
        raise ValueError("slice steps must lie inside the projection")
    if aggregate is not None and (
        aggregate.shape != (S, len(out_idx), M)
        or aggregate.dtype != np.float64
        or not aggregate.flags.writeable
    ):
        raise ValueError("aggregate must be writable float64 with shape (S, outputs, M)")
    args = _pack(kernel, inputs)
    dependent = len(kernel.columns) - kernel.layout.independent
    st = min(S, scenario_tile or max(1, TILE_BYTES // max(1, dependent * M * 8)))
    part = np.zeros((S, -(-P // BLOCK), len(out_idx), M))
    sel_out = np.full((S, len(sel_idx), P), np.nan)
    rows_wanted = len(grid_idx) > 0 or len(sel_idx) > 0
    size = request.batch_size or max(P, 1)
    whole = (
        None if on_batch is not None or not len(grid_idx) else np.empty((S, len(grid_idx), P, M))
    )
    for lo in range(0, P, size):
        hi = min(P, lo + size)
        if not rows_wanted:
            kernel.run_aggregate(lo, hi, *args, st, out_idx, part)
            continue
        grid_out = np.empty((S, len(grid_idx), hi - lo, M))
        kernel.run_rows(
            lo, hi, *args, st, out_idx, part, grid_idx, grid_out, sel_idx, sel_step, sel_out
        )
        if whole is not None:
            whole[:, :, lo:hi] = grid_out
        if on_batch is not None and len(grid_idx):
            on_batch(Batch(lo, hi, grid_columns, grid_out))
    if aggregate is None:
        aggregate = np.zeros((S, len(out_idx), M))
    for block in range(part.shape[1]):  # blocks in order: the fixed summation order
        aggregate += part[:, block]
    return Projection(aggregate, sel_out, grid_columns, whole)
