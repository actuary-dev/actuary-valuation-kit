"""Strict measurement settings, declared groups and calendar-keyed cohort curves."""

import calendar
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any

import numpy as np
import polars as pl

from avk.inputs.formats import FormatSpec, read
from avk.model.measures.stress import Array
from avk.model.regimes import GeneralMeasurementModel
from avk.runs.capital_settings import discount_curve
from avk.runs.numbers import finite_number
from avk.runtime.errors import AvkError, ConfigError

if TYPE_CHECKING:
    from avk.runs.check import CheckReport


def month_date(serial: int, *, end: bool = False) -> date:
    year, month = serial // 12, serial % 12 + 1
    return date(year, month, calendar.monthrange(year, month)[1] if end else 1)


def serial(value: date) -> int:
    return value.year * 12 + value.month - 1


@dataclass(frozen=True)
class MeasurementSettings:
    reporting_months: int
    current_curve: str
    ra_method: str
    ra_ratio: float
    ri_ratio: float
    groups: pl.DataFrame
    curves: dict[str, dict[int, float]]
    stress_set: dict[str, Any] | str | None

    def locked_rates(self, cohorts: list[str], when: date, months: int) -> Array:
        start = serial(when)
        labels, inverse = np.unique(np.asarray(cohorts), return_inverse=True)
        try:
            curves = np.array(
                [[self.curves[c][start + t] for t in range(months)] for c in labels],
                dtype=np.float64,
            )
            return curves[inverse]
        except KeyError as exc:
            raise ConfigError(f"IFRS17: missing locked-in cohort/calendar month {exc}") from exc


def measurement_settings(report: "CheckReport") -> MeasurementSettings:
    from avk.runs.check import run_factory

    cfg = report.config
    if report.scenarios is None or report.scenarios.measure != "deterministic":
        raise ConfigError("IFRS17 currently requires deterministic curves")
    raw = cfg.ifrs17
    required = {
        "Reporting_Months",
        "Locked_In_Curves",
        "Current_Curve",
        "Profitability_Field",
        "RA_Method",
        "RI_RA_Ratio",
    }
    optional = {"RA_Ratio", "Portfolio_Field", "Cohort_Field", "Stress_Set"}
    if not isinstance(raw, dict) or required - raw.keys() or raw.keys() - required - optional:
        raise ConfigError(f"IFRS17 requires {sorted(required)} and only declared settings")
    applicability = GeneralMeasurementModel().applicability(
        frozenset(dir(run_factory(cfg).definition()))
    )
    if not applicability.supported:
        raise ConfigError(f"IFRS17 GMM unsupported capabilities: {applicability.unsupported}")
    months = raw["Reporting_Months"]
    if type(months) is not int or not 1 <= months <= 120:
        raise ConfigError("IFRS17.Reporting_Months must be an integer from 1 to 120")
    method = raw["RA_Method"]
    if method not in ("ratio", "cost_of_capital"):
        raise ConfigError("IFRS17.RA_Method must be ratio or cost_of_capital")
    if (method == "ratio" and ("RA_Ratio" not in raw or "Stress_Set" in raw)) or (
        method == "cost_of_capital" and ("Stress_Set" not in raw or "RA_Ratio" in raw)
    ):
        raise ConfigError("IFRS17: ratio requires RA_Ratio; cost_of_capital requires Stress_Set")
    ratio = finite_number(raw["RA_Ratio"], "IFRS17.RA_Ratio") if method == "ratio" else 0.0
    ri_ratio = finite_number(raw["RI_RA_Ratio"], "IFRS17.RI_RA_Ratio")
    if ratio < 0:
        raise ConfigError("IFRS17.RA_Ratio must be nonnegative")
    # Reinsurance-held RA is signed: the old input uses a negative ratio (a benefit).
    name = raw["Current_Curve"]
    if not isinstance(name, str) or not name:
        raise ConfigError("IFRS17.Current_Curve must name a curve")
    if name != "onerous":
        try:
            rates = discount_curve(report, name)
            if not np.isfinite(rates).all() or (rates <= -1).any():
                raise ConfigError("IFRS17 current rates must be finite and exceed -1")
        except AvkError as exc:
            raise ConfigError(f"IFRS17.Current_Curve: {exc}") from exc
    assert report.points is not None
    frame = report.points.frame
    fields = [
        raw[k] for k in ("Portfolio_Field", "Cohort_Field", "Profitability_Field") if k in raw
    ]
    if any(not isinstance(k, str) or not k or k not in frame.columns for k in fields):
        raise ConfigError("IFRS17 group fields must name existing policy columns")
    profitability = raw["Profitability_Field"]
    opening = month_date(serial(cfg.valuation_date) - months, end=True)
    start_field = (
        "Policy_start_date" if cfg.products_to_run == ("CREDIT_LIFE",) else "Policy Start Date"
    )
    groups = frame.select(
        "Policy_Number",
        pl.col(start_field).alias("start"),
        (
            pl.col(raw["Portfolio_Field"]).cast(pl.String)
            if "Portfolio_Field" in raw
            else pl.lit(cfg.products_to_run[0])
        ).alias("portfolio"),
        (
            pl.col(raw["Cohort_Field"]).cast(pl.String)
            if "Cohort_Field" in raw
            else pl.col(start_field).dt.year().cast(pl.String)
        ).alias("cohort"),
        pl.col(profitability).cast(pl.String).alias("profitability"),
    ).with_columns(
        ((pl.col("start") > opening) & (pl.col("start") <= cfg.valuation_date)).alias(
            "recognised_new_business"
        ),
        (pl.col("start") <= cfg.valuation_date).alias("recognised"),
    )
    for key in ("portfolio", "cohort"):
        if groups[key].null_count() or (groups[key].str.strip_chars() == "").any():
            raise ConfigError(f"IFRS17: missing {key} group key")
    existing = groups.filter(~pl.col("recognised_new_business"))
    if (
        existing["profitability"].null_count()
        or (~existing["profitability"].is_in(["onerous", "other"])).any()
    ):
        raise ConfigError("IFRS17: in-force/future profitability must be onerous or other")
    logical = raw["Locked_In_Curves"]
    if not isinstance(logical, str) or not logical:
        raise ConfigError("IFRS17.Locked_In_Curves must name a logical input table")
    try:
        table = report.inputs.read(logical)
        if report.inputs.location(logical).format is None:
            raise ConfigError("IFRS17 locked-in curves require an explicit Format")
        if report.inputs.location(logical).format is not None:
            loaded = read(
                report.inputs.format_of(logical),
                table,
                FormatSpec(logical, {}, (), (), "", 0, "mixed"),
            )
            keys = [str(k).split("|") for k in loaded.axes[0].keys]
            table = pl.DataFrame(
                keys, schema=["Cohort", "Calendar_Month"], orient="row"
            ).with_columns(pl.Series("Monthly_Rate", loaded.values[:, 0]))
        if set(table.columns) != {"Cohort", "Calendar_Month", "Monthly_Rate"}:
            raise ConfigError("IFRS17 curves need Cohort, Calendar_Month, Monthly_Rate")
        table = table.with_columns(
            pl.col("Cohort").cast(pl.String),
            pl.col("Monthly_Rate").cast(pl.Float64),
            (pl.col("Calendar_Month").cast(pl.String) + "-01")
            .str.to_date("%Y-%m-%d")
            .alias("date"),
        )
        if table.null_count().row(0) != (0,) * len(table.columns):
            raise ConfigError("IFRS17 curves contain missing values")
        if table.select(pl.struct("Cohort", "date").n_unique()).item() != table.height:
            raise ConfigError("IFRS17 curves contain duplicate cohort/month keys")
        values = table["Monthly_Rate"].to_numpy()
        if not np.isfinite(values).all() or (values <= -1).any():
            raise ConfigError("IFRS17 locked rates must be finite and exceed -1")
        curves: dict[str, dict[int, float]] = {}
        for cohort, when, value in table.select("Cohort", "date", "Monthly_Rate").iter_rows():
            curves.setdefault(cohort, {})[serial(when)] = value
    except (AvkError, pl.exceptions.PolarsError, ValueError) as exc:
        raise ConfigError(f"IFRS17 locked-in curves: {exc}") from exc
    result = MeasurementSettings(
        months, name, method, ratio, ri_ratio, groups, curves, raw.get("Stress_Set")
    )
    cohorts = groups["cohort"].unique().to_list()
    result.locked_rates(cohorts, cfg.valuation_date, cfg.projection_term * 12)
    # Prove recognition dates' curve coverage before any projection/output.
    for issue in (
        groups.filter(pl.col("recognised_new_business"))["start"].dt.truncate("1mo").unique()
    ):
        result.locked_rates(
            cohorts, month_date(serial(issue) - 1, end=True), cfg.projection_term * 12
        )
    return result
