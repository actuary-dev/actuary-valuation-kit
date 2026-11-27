"""Format computed projection values for output.

Column names and order come only from the factory's `OutputSchema`; the values arrive by
output name, already computed (aggregates summed in the kernel, grids per batch, seriatim
values sliced in the kernel). When `scenarios` names the scenarios of a supplied set, each
value has a leading scenario axis and every file gains a leading `Scenario` column, rows
grouped by scenario.
"""

from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np
import numpy.typing as npt
import polars as pl

from avk.outputs.schema import CALENDAR, POLICY, SCENARIO, STEP, OutputSchema
from avk.outputs.sinks import CsvSink, Stream

Array = npt.NDArray[np.float64]


def _labels(scenarios: Sequence[str], each: int) -> pl.Series:
    return pl.Series(SCENARIO, [label for label in scenarios for _ in range(each)], pl.String)


def write_aggregate(
    sink: CsvSink,
    name: str,
    schema: OutputSchema,
    columns: Mapping[str, Array],
    *,
    scenarios: Sequence[str] | None = None,
) -> Path:
    """One row per projection step (per scenario when `scenarios` is given): the step, then
    every entry summed over policies. Values are `(M,)`, or `(S, M)` with `scenarios`."""
    values = {
        output: np.asarray(columns[output], dtype=np.float64) for output, _, _ in schema.entries
    }
    paths = 1 if scenarios is None else len(scenarios)
    months = next(iter(values.values())).shape[-1] if values else 0
    data: dict[str, pl.Series] = {}
    if scenarios is not None:
        data[SCENARIO] = _labels(scenarios, months)
    data[schema.step] = pl.Series(np.tile(np.arange(months, dtype=np.int64), paths))
    for output, value in values.items():
        data[output] = pl.Series(value.reshape(-1))
    return sink.write_table(name, pl.DataFrame(data))


def write_scenario_summary(
    sink: CsvSink,
    name: str,
    schema: OutputSchema,
    columns: Mapping[str, Array],
    statistics: Sequence[str],
) -> Path:
    """Write rows in aggregate column order, then projection step order."""
    names = [output for output, _, _ in schema.entries]
    if names:
        months = columns[names[0]].shape[1]
        values = np.concatenate([columns[output] for output in names], axis=1)
    else:
        months = 0
        values = np.empty((len(statistics), 0))
    return sink.write_table(
        name,
        pl.DataFrame(
            {
                schema.step: np.tile(np.arange(months, dtype=np.int64), len(names)),
                "Output_Column": pl.Series(np.repeat(names, months), dtype=pl.String),
                **{
                    label: pl.Series(series, nan_to_null=True)
                    for label, series in zip(statistics, values, strict=True)
                },
            }
        ),
    )


def write_per_policy_month(
    stream: Stream,
    schema: OutputSchema,
    policy_numbers: Sequence[str] | pl.Series,
    columns: Mapping[str, Array],
    *,
    calendar: npt.ArrayLike | None = None,
    scenarios: Sequence[str] | None = None,
) -> None:
    """Append one batch: a row per policy and month, policy-major, keys then entries (for
    each scenario in turn when `scenarios` is given).

    `columns` holds a `(policies, months)` grid, or `(scenarios, policies, months)` with
    `scenarios`, for every key read from a column and for every entry; `calendar` holds the
    calendar month of each projection step when the schema has a `CALENDAR` key.
    """
    numbers = pl.Series(policy_numbers, dtype=pl.String)
    paths = 1 if scenarios is None else len(scenarios)

    def grid(output: str) -> Array:
        return np.asarray(columns[output], dtype=np.float64).reshape(paths, len(numbers), -1)

    grids = {output: grid(output) for output, _, _ in schema.entries}
    months = next(iter(grids.values())).shape[2] if grids else 0
    each = len(numbers) * months
    data: dict[str, pl.Series] = {}
    if scenarios is not None:
        data[SCENARIO] = _labels(scenarios, each)
    for output, source, _ in schema.keys:
        if source == POLICY:
            policies = np.repeat(numbers.to_numpy(), months)
            data[output] = pl.Series(np.tile(policies, paths), dtype=pl.String)
        elif source == STEP:
            data[output] = pl.Series(
                np.tile(np.arange(months, dtype=np.int64), len(numbers) * paths)
            )
        elif source == CALENDAR:
            if calendar is None:
                raise ValueError(f"{output}: the calendar months were not given")
            months_of_year = np.asarray(calendar, dtype=np.int64)
            data[output] = pl.Series(np.tile(months_of_year, len(numbers) * paths))
        elif output in schema.integer_keys:
            values = grid(output).reshape(-1)
            if not np.array_equal(values, np.floor(values)):
                raise ValueError(f"{output}: an integer key holds a fractional value")
            data[output] = pl.Series(values.astype(np.int64))
        else:
            data[output] = pl.Series(grid(output).reshape(-1))
    for output, values in grids.items():
        data[output] = pl.Series(values.reshape(-1))
    stream.append(pl.DataFrame(data))


def write_seriatim(
    sink: CsvSink,
    name: str,
    schema: OutputSchema,
    policy_numbers: Sequence[str] | pl.Series,
    columns: Mapping[str, Array],
    *,
    scenarios: Sequence[str] | None = None,
    batch_size: int | None = None,
) -> Path:
    """One row per policy in input order (per scenario when `scenarios` is given): the policy
    number, then every seriatim entry. Values are `(P,)`, or `(S, P)` with `scenarios`."""
    policy = schema.policy
    if policy is None:
        raise ValueError("The seriatim file needs the schema's policy number key")
    numbers = (
        pl.Series(policy_numbers)
        if batch_size is not None
        else pl.Series(policy_numbers, dtype=pl.String)
    )
    paths = 1 if scenarios is None else len(scenarios)
    size = batch_size or max(len(numbers), 1)
    with sink.open_stream(name) as stream:
        for scenario in range(paths):
            for lo in range(0, len(numbers), size):
                hi = min(lo + size, len(numbers))
                data: dict[str, pl.Series] = {}
                if scenarios is not None:
                    data[SCENARIO] = _labels((scenarios[scenario],), hi - lo)
                data[policy] = numbers[lo:hi].cast(pl.String)
                for output, _, _, _ in schema.seriatim:
                    values = np.asarray(columns[output], dtype=np.float64).reshape(
                        paths, len(numbers)
                    )
                    data[output] = pl.Series(values[scenario, lo:hi])
                stream.append(pl.DataFrame(data))
    return sink.path(name)
