"""Strict readers for versioned public table formats."""

import re

import numpy as np
import polars as pl

from avk.inputs.formats import (
    FormatSpec,
    integer_axis,
    key_axis,
    table,
    unique,
)
from avk.model.data import Table
from avk.runtime.errors import InputError


def field_name(name: str) -> str:
    """Stable public field spelling for a definition-layer binding."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def exact(frame: pl.DataFrame, columns: tuple[str, ...], spec: FormatSpec) -> None:
    if set(frame.columns) != set(columns):
        raise InputError(f"{spec.name}: require exactly {columns}")
    if frame.is_empty() or frame.null_count().to_numpy().any():
        raise InputError(f"{spec.name}: empty table or missing value")


def numbers(frame: pl.DataFrame, columns: tuple[str, ...], spec: FormatSpec) -> np.ndarray:
    if any(frame.schema[c] == pl.Boolean for c in columns):
        raise InputError(f"{spec.name}: numbers cannot be Boolean")
    values = frame.select(pl.col(c).cast(pl.Float64) for c in columns).to_numpy()
    if not np.isfinite(values).all():
        raise InputError(f"{spec.name}: numbers must be finite")
    return values


def consecutive(frame: pl.DataFrame, key: str, start: int, spec: FormatSpec) -> np.ndarray:
    values = numbers(frame, (key,), spec).ravel()
    keys = np.unique(values)
    if not np.array_equal(keys, np.arange(start, keys[-1] + 1)):
        raise InputError(f"{spec.name}: {key} must be consecutive integers from {start}")
    return keys


def wide(frame: pl.DataFrame, key: str, spec: FormatSpec) -> tuple[pl.DataFrame, np.ndarray]:
    unique(frame, [key, "field"], spec)
    numbers(frame, ("value",), spec)
    fields = tuple(field_name(c) for c in spec.columns)
    selected = frame.filter(pl.col("field").is_in(fields))
    keys = frame[key].unique()
    if selected.height != len(keys) * len(fields):
        raise InputError(f"{spec.name}: missing key/field combination")
    pivoted = selected.pivot(on="field", index=key, values="value").sort(key)
    values = numbers(pivoted, fields, spec)
    if spec.units == "probability" and ((values < 0) | (values > 1)).any():
        raise InputError(f"{spec.name}: probability must be between 0 and 1")
    if spec.units == "annual_effective" and (values <= -1).any():
        raise InputError(f"{spec.name}: annual rates must exceed -1")
    return pivoted, values


def age_rates(frame: pl.DataFrame, spec: FormatSpec) -> Table:
    exact(frame, ("age", "field", "value"), spec)
    numbers(frame, ("age",), spec)
    frame = frame.with_columns(pl.col("age").cast(pl.Float64))
    pivoted, values = wide(frame, "age", spec)
    ages = consecutive(pivoted, "age", int(pivoted["age"].to_numpy().min()), spec)
    if ages[0] < 0 or (values < 0).any():
        raise InputError(f"{spec.name}: ages and rates must be nonnegative")
    return table(
        spec,
        values,
        (
            integer_axis("age", int(ages[0]), len(ages), spec.axes[0]),
            key_axis("sex", tuple(range(len(spec.columns)))),
        ),
    )


def year_channel(frame: pl.DataFrame, spec: FormatSpec) -> Table:
    exact(frame, ("year", "channel", "value"), spec)
    numbers(frame, ("year", "channel"), spec)
    frame = frame.with_columns(pl.col("year", "channel").cast(pl.Float64))
    unique(frame, ["year", "channel"], spec)
    years = consecutive(frame, "year", 1, spec)
    channels = np.unique(numbers(frame, ("channel",), spec))
    if (channels < 0).any() or not np.equal(channels, np.floor(channels)).all():
        raise InputError(f"{spec.name}: channel must be a nonnegative integer")
    if frame.height != len(years) * len(channels):
        raise InputError(f"{spec.name}: missing year/channel combination")
    values = numbers(frame.sort("year", "channel"), ("value",), spec)
    if ((values < 0) | (values > 1)).any():
        raise InputError(f"{spec.name}: probability must be between 0 and 1")
    return table(
        spec,
        values.reshape(len(years), len(channels)),
        (
            integer_axis("policy_year", 1, len(years), spec.axes[0]),
            key_axis("channel", tuple(int(c) for c in channels)),
        ),
    )


def expenses(frame: pl.DataFrame, spec: FormatSpec) -> Table:
    exact(frame, ("section", "index", "field", "value"), spec)
    unique(frame, ["section", "index", "field"], spec)
    numbers(frame, ("index", "value"), spec)
    section = (
        "initial" if len(spec.columns) == 4 else "renewal" if len(spec.columns) == 3 else "schedule"
    )
    selected = frame.filter(pl.col("section") == section).drop("section")
    pivoted, values = wide(selected, "index", spec)
    if (values < 0).any():
        raise InputError(f"{spec.name}: expenses must be nonnegative")
    if section == "renewal":
        if pivoted["index"].to_list() != [0]:
            raise InputError(f"{spec.name}: renewal index must be 0")
        return table(spec, values.ravel(), (key_axis("category", spec.columns),))
    if section == "schedule":
        consecutive(pivoted, "index", 1, spec)
        if pivoted.height * 12 < spec.projection_months:
            raise InputError(f"{spec.name}: missing schedule years")
        return table(
            spec,
            values,
            (
                integer_axis("year", 1, pivoted.height, spec.axes[0]),
                key_axis("field", spec.columns),
            ),
        )
    if not np.array_equal(values[:, 0], pivoted["index"].to_numpy()):
        raise InputError(f"{spec.name}: initial sa field must equal index")
    return table(
        spec,
        values,
        (
            key_axis("knot", tuple(range(pivoted.height))),
            key_axis("field", spec.columns),
        ),
    )


def curves(frame: pl.DataFrame, spec: FormatSpec) -> Table:
    if "cohort" in frame.columns:
        exact(frame, ("cohort", "month", "value"), spec)
        frame = frame.with_columns(
            pl.col("cohort").cast(pl.String),
            (pl.col("month").cast(pl.String) + "-01").str.to_date("%Y-%m-%d").alias("date"),
        ).sort("cohort", "month")
        unique(frame, ["cohort", "month"], spec)
        values = numbers(frame, ("value",), spec)
        if (values <= -1).any():
            raise InputError(f"{spec.name}: monthly rates must exceed -1")
        keys = tuple(frame.select("cohort", "month").iter_rows())
        if any("|" in v for row in keys for v in row):
            raise InputError(f"{spec.name}: curve labels cannot contain |")
        return table(
            spec,
            values,
            (
                key_axis("cohort_month", tuple("|".join(row) for row in keys)),
                key_axis("field", ("rate",)),
            ),
        )
    exact(frame, ("year", "field", "value"), spec)
    numbers(frame, ("year",), spec)
    frame = frame.with_columns(pl.col("year").cast(pl.Float64))
    pivoted, values = wide(frame, "year", spec)
    consecutive(pivoted, "year", 1, spec)
    if pivoted.height * 12 < spec.projection_months:
        raise InputError(f"{spec.name}: missing curve years")
    return table(
        spec,
        values,
        (
            integer_axis("year", 1, pivoted.height, spec.axes[0]),
            key_axis("field", spec.columns),
        ),
    )


def parameters(frame: pl.DataFrame, spec: FormatSpec) -> Table:
    exact(frame, ("product", "parameter", "value"), spec)
    unique(frame, ["product", "parameter"], spec)
    numbers(frame, ("value",), spec)
    selected = frame.filter(pl.col("product") == spec.product).sort("parameter")
    if selected.is_empty():
        raise InputError(f"{spec.name}: missing product {spec.product}")
    return table(
        spec,
        numbers(selected, ("value",), spec),
        (
            key_axis("parameter", tuple(selected["parameter"])),
            key_axis("field", (spec.product,)),
        ),
    )


def bands(frame: pl.DataFrame, spec: FormatSpec) -> Table:
    exact(frame, ("lower", "upper", "smoker", "value"), spec)
    unique(frame, ["lower", "smoker"], spec)
    frame = frame.sort("smoker", "lower")
    values = numbers(frame, ("lower", "upper", "smoker", "value"), spec)
    if (values < 0).any() or (values[:, 1] <= values[:, 0]).any():
        raise InputError(f"{spec.name}: invalid loading bands")
    if not set(frame["smoker"]) <= {0, 1}:
        raise InputError(f"{spec.name}: smoker must be 0 or 1")
    return table(
        spec,
        values,
        (
            key_axis("band", tuple(range(frame.height))),
            key_axis("field", spec.columns),
        ),
    )


def frequencies(frame: pl.DataFrame, spec: FormatSpec) -> Table:
    exact(frame, ("frequency", "field", "value"), spec)
    pivoted, values = wide(frame, "frequency", spec)
    keys = numbers(pivoted, ("frequency",), spec).ravel()
    if (keys <= 0).any() or not np.equal(keys, np.floor(keys)).all() or (values <= 0).any():
        raise InputError(f"{spec.name}: frequencies and factors must be positive")
    return table(spec, values[:, 0], (key_axis("Frequency", tuple(int(k) for k in keys)),))


def correlations(frame: pl.DataFrame, spec: FormatSpec) -> Table:
    exact(frame, ("risk", "other", "value"), spec)
    unique(frame, ["risk", "other"], spec)
    labels = tuple(sorted(frame["risk"].unique()))
    if set(frame["other"]) != set(labels) or frame.height != len(labels) ** 2:
        raise InputError(f"{spec.name}: missing correlation pairs")
    values = numbers(frame.sort("risk", "other"), ("value",), spec).reshape(len(labels), -1)
    if (
        (np.abs(values) > 1).any()
        or not np.array_equal(values, values.T)
        or not np.array_equal(np.diag(values), np.ones(len(labels)))
        or np.linalg.eigvalsh(values).min() < -1e-12
    ):
        raise InputError(f"{spec.name}: invalid correlation matrix")
    return table(spec, values, (key_axis("risk", labels), key_axis("other", labels)))


STRESS_COLUMNS = (
    "additive",
    "multiplier",
    "start_month",
    "end_month",
    "maximum_decrease",
    "factor",
)


def stresses(frame: pl.DataFrame, spec: FormatSpec) -> Table:
    exact(frame, ("risk", "target", "method", *STRESS_COLUMNS), spec)
    unique(frame, ["risk", "target", "start_month", "end_month"], spec)
    values = numbers(frame, STRESS_COLUMNS, spec)
    windows: dict[tuple[str, str], list[tuple[float, float]]] = {}
    for row in frame.iter_rows(named=True):
        start, end = float(row["start_month"]), float(row["end_month"])
        if start != int(start) or end != int(end) or start < 0 or end < 0:
            raise InputError(f"{spec.name}: stress windows require nonnegative integer months")
        lo, hi = (0.0, float("inf")) if start == end == 0 else (start, end)
        if lo > hi:
            raise InputError(f"{spec.name}: stress window start exceeds end")
        previous = windows.setdefault((row["risk"], row["target"]), [])
        if any(lo <= b and a <= hi for a, b in previous):
            raise InputError(f"{spec.name}: overlapping stress windows")
        previous.append((lo, hi))
    if not set(frame["method"]) <= {"revaluation", "mass_lapse", "catastrophe"}:
        raise InputError(f"{spec.name}: unknown stress method")
    keys = tuple(frame.select("risk", "target", "method").iter_rows())
    # Table axis keys are strings; composite metadata has a reversible separator.
    if any("|" in str(v) for key in keys for v in key):
        raise InputError(f"{spec.name}: stress labels cannot contain |")
    return table(
        spec,
        values,
        (
            key_axis("stress", tuple("|".join(k) + f"|{i}" for i, k in enumerate(keys))),
            key_axis("field", STRESS_COLUMNS),
        ),
    )


def opening_balances(frame: pl.DataFrame, spec: FormatSpec) -> Table:
    keys = ("product", "portfolio", "cohort", "profitability")
    columns = ("csm", "loss_component", "ri_csm", "loss_recovery_component")
    exact(frame, (*keys, *columns), spec)
    frame = frame.with_columns(pl.col(k).cast(pl.String) for k in keys)
    unique(frame, list(keys), spec)
    values = numbers(frame, columns, spec)
    if (
        (values[:, [0, 1, 3]] < 0).any()
        or ((values[:, 0] > 0) & (values[:, 1] > 0)).any()
        or (values[:, 3] > values[:, 1]).any()
    ):
        raise InputError(f"{spec.name}: invalid opening balances")
    rows = tuple(frame.select(keys).iter_rows())
    if any("|" in v for row in rows for v in row):
        raise InputError(f"{spec.name}: group labels cannot contain |")
    return table(
        spec,
        values,
        (
            key_axis("group", tuple("|".join(row) for row in rows)),
            key_axis("field", columns),
        ),
    )


def keyed(frame: pl.DataFrame, spec: FormatSpec) -> Table:
    """Unit-linked tables keyed by a code: one value per key and declared field.

    Keys are exact strings (no stripping or case folding), sorted; the file holds exactly
    the declared fields."""
    exact(frame, ("key", "field", "value"), spec)
    frame = frame.with_columns(pl.col("key").cast(pl.String), pl.col("field").cast(pl.String))
    unique(frame, ["key", "field"], spec)
    numbers(frame, ("value",), spec)
    fields = tuple(field_name(c) for c in spec.columns)
    present = set(frame["field"])
    if present != set(fields):
        unknown = sorted(present - set(fields))
        if unknown:
            raise InputError(f"{spec.name}: unknown field(s) {unknown}; require exactly {fields}")
        raise InputError(f"{spec.name}: require exactly fields {fields}")
    keys = tuple(sorted(frame["key"].unique()))
    if frame.height != len(keys) * len(fields):
        raise InputError(f"{spec.name}: missing key/field combination")
    pivoted = frame.pivot(on="field", index="key", values="value").sort("key")
    values = numbers(pivoted, fields, spec)
    return table(spec, values, (key_axis("key", keys), key_axis("field", spec.columns)))


def year_key(frame: pl.DataFrame, spec: FormatSpec) -> Table:
    """Unit-linked tables by policy year and integer key: the one declared field."""
    if len(spec.columns) != 1:
        raise InputError(f"{spec.name}: a year-key binding must select exactly one field")
    exact(frame, ("year", "key", "field", "value"), spec)
    numbers(frame, ("year", "key"), spec)
    frame = frame.with_columns(
        pl.col("year", "key").cast(pl.Float64), pl.col("field").cast(pl.String)
    )
    unique(frame, ["year", "key", "field"], spec)
    numbers(frame, ("value",), spec)
    keys = np.unique(numbers(frame, ("key",), spec))
    if (keys < 0).any() or not np.equal(keys, np.floor(keys)).all():
        raise InputError(f"{spec.name}: key must be a nonnegative integer")
    years = consecutive(frame, "year", 1, spec)
    selected = frame.filter(pl.col("field") == field_name(spec.columns[0]))
    if selected.height != len(years) * len(keys):
        raise InputError(f"{spec.name}: missing year/key combination")
    values = numbers(selected.sort("year", "key"), ("value",), spec)
    return table(
        spec,
        values.reshape(len(years), len(keys)),
        (
            integer_axis("policy_year", 1, len(years), spec.axes[0]),
            key_axis("key", tuple(int(k) for k in keys)),
        ),
    )


PUBLIC_READERS = {
    "avk_ul_keyed_v1": keyed,
    "avk_ul_year_key_v1": year_key,
    "avk_mortality_v1": age_rates,
    "avk_morbidity_v1": age_rates,
    "avk_lapse_v1": year_channel,
    "avk_commission_v1": year_channel,
    "avk_expenses_v1": expenses,
    "avk_curves_v1": curves,
    "avk_parameters_v1": parameters,
    "avk_correlations_v1": correlations,
    "avk_stresses_v1": stresses,
    "avk_opening_v1": opening_balances,
    "avk_bands_v1": bands,
    "avk_frequencies_v1": frequencies,
}
