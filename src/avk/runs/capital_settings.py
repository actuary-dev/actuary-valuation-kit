"""Checked, label-aligned inputs for combined stress capital."""

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import numpy as np
import polars as pl

from avk.assumptions.models import InterestCurveAssumption
from avk.inputs.formats import read_csv_format
from avk.model.measures.stress import Array
from avk.runs.numbers import finite_number
from avk.runtime.errors import ConfigError
from avk.runtime.progress import fingerprint

KEYS = {
    "Aggregation",
    "Cost_of_Capital_Rate",
    "Discount_Curve",
    "Diversification_Floor",
    "Operational_Risk",
    "Cost_Loading",
}
LAPSE = {"lapse up", "lapse down", "mass lapse"}

if TYPE_CHECKING:
    from avk.runs.check import CheckReport


def discount_curve(report: "CheckReport", name: str) -> Array:
    """Scenario names retain timing; Table.Column selects the unshifted input curve."""
    if report.scenarios is not None and name in report.scenarios.variables:
        return cast(Array, report.scenarios.variables[name][0])
    table, separator, column = name.partition(".")
    assumption = report.assumptions.get(table)
    if separator and isinstance(assumption, InterestCurveAssumption):
        try:
            return assumption.monthly(report.config.projection_term * 12)[
                :, assumption.column(column)
            ]
        except (KeyError, ValueError) as exc:
            raise ConfigError(f"Settings.Discount_Curve: unknown curve {name}") from exc
    raise ConfigError(f"Settings.Discount_Curve: unknown curve {name}")


@dataclass(frozen=True)
class CapitalSettings:
    labels: tuple[str, ...]
    correlation: Array
    aggregation: str
    rate: float
    curve: str
    floor: float
    premium_charge: float
    bel_charge: float
    loading: float


def capital_settings(
    raw: dict[str, Any], risks: tuple[str, ...], folder: Path
) -> CapitalSettings | None:
    settings = raw.get("Settings", {})
    if "Correlation" not in raw:
        if set(settings) & KEYS:
            raise ConfigError("Combined capital Settings require Correlation")
        return None
    labels = tuple(dict.fromkeys("lapse" if r.casefold() in LAPSE else r for r in risks))
    matrix = raw["Correlation"]
    if isinstance(matrix, dict) and set(matrix) == {"CSV", "Format"}:
        fingerprint(folder / matrix["CSV"])
        loaded = read_csv_format(str(folder / matrix["CSV"]), matrix["Format"], "correlations")
        matrix = {
            a: {b: float(loaded.values[i, j]) for j, b in enumerate(loaded.axes[1].keys)}
            for i, a in enumerate(loaded.axes[0].keys)
        }
    if isinstance(matrix, str):
        try:
            fingerprint(folder / matrix)
            frame = pl.read_csv(folder / matrix)
            rows = frame[frame.columns[0]].to_list()
            if len(set(rows)) != len(rows):
                raise ConfigError("Correlation: duplicate row labels")
            matrix = {
                row[frame.columns[0]]: {k: v for k, v in row.items() if k != frame.columns[0]}
                for row in frame.iter_rows(named=True)
            }
        except (OSError, pl.exceptions.PolarsError) as exc:
            raise ConfigError(f"Correlation: {exc}") from exc
    if not isinstance(matrix, dict) or set(matrix) != set(labels):
        raise ConfigError(f"Correlation row labels must match exactly {list(labels)}")
    for label, row in matrix.items():
        if not isinstance(row, dict) or set(row) != set(labels):
            raise ConfigError(
                f"Correlation column labels for {label} must match exactly {list(labels)}"
            )
    values = np.array(
        [[finite_number(matrix[a][b], f"Correlation {a}/{b}") for b in labels] for a in labels],
        dtype=np.float64,
    )
    if (np.abs(values) > 1).any() or not np.array_equal(np.diag(values), np.ones(len(labels))):
        raise ConfigError("Correlation must have unit diagonal and coefficients in [-1, 1]")
    if not np.array_equal(values, values.T) or np.linalg.eigvalsh(values).min() < -1e-12:
        raise ConfigError("Correlation must be symmetric and positive semidefinite")
    aggregation = settings.get("Aggregation", "portfolio")
    if aggregation not in ("policy", "portfolio"):
        raise ConfigError("Settings.Aggregation must be policy or portfolio")
    rate = finite_number(settings.get("Cost_of_Capital_Rate"), "Settings.Cost_of_Capital_Rate")
    curve = settings.get("Discount_Curve")
    if rate < 0 or not isinstance(curve, str) or not curve:
        raise ConfigError("Settings needs nonnegative Cost_of_Capital_Rate and Discount_Curve")
    floor = finite_number(
        settings.get("Diversification_Floor", 0), "Settings.Diversification_Floor"
    )
    loading = finite_number(settings.get("Cost_Loading", 1), "Settings.Cost_Loading")
    if not 0 <= floor <= 1 or loading < 0:
        raise ConfigError("Settings: floor must be in [0, 1] and loading nonnegative")
    op = settings.get("Operational_Risk", {})
    if not isinstance(op, dict) or (op and set(op) != {"Premium_Charge", "BEL_Charge"}):
        raise ConfigError("Settings.Operational_Risk needs Premium_Charge and BEL_Charge")
    premium = finite_number(op["Premium_Charge"], "Premium_Charge") if op else 0.0
    bel = finite_number(op["BEL_Charge"], "BEL_Charge") if op else 0.0
    if min(premium, bel) < 0:
        raise ConfigError("Operational risk charges must be nonnegative")
    values.flags.writeable = False
    return CapitalSettings(labels, values, aggregation, rate, curve, floor, premium, bel, loading)
