"""UNIT_LINKED compliance layer: reduction in yield, residual additions, the pricing-time
demonstration and the benefit illustration.

This module reads a run through the normal input gate (`check`), builds single-life cases
from the prepared book or from the variant, fund and charge tables, and calls the pure
projection in `avk.products.unit_linked.illustration`.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from avk.esg.library import flat
from avk.model.data import ScenarioSet, Table
from avk.outputs.sinks import CsvSink
from avk.products.unit_linked.bindings import ASSET_CLASSES, CODE, MAX_FUND_SLOTS
from avk.products.unit_linked.illustration import (
    FEATURES,
    FIRST_MEASUREMENT_YEAR,
    Assessment,
    Case,
    ChargeSchedule,
    Gross,
    assess,
)
from avk.runs.check import CheckReport, check
from avk.runs.config import RunConfig, load_run_config
from avk.runtime.errors import InputError

RATES = (0.04, 0.08)
TERMS = (10, 20, 30)
FREQUENCIES = (1, 12)
ENTRY_AGE = 35
SEVERITY = {"pass": 0, "pass_with_additions": 1, "fail": 2, "design_fail": 3}
SCALE_FIELDS = (
    "premium_allocation_rate",
    "admin_charge_monthly",
    "loyalty_rate",
    "booster_rate",
    "disc_pct_low",
    "disc_cap_low",
    "disc_pct_high",
    "disc_cap_high",
)


def _column(table: Table, key: object) -> tuple[float, ...]:
    """The values of a year or age table in the column of `key`."""
    keys = list(table.axes[1].keys)
    if key not in keys:
        raise InputError(f"{table.name}: no column {key!r}")
    return tuple(float(v) for v in table.values[:, keys.index(key)])


def schedule_for(
    tables: Mapping[str, Table], variant_id: int, regime_id: int, charge_column: int
) -> ChargeSchedule:
    """The per-year charge arrays of one variant and regime, and the mortality charges of a
    charge column, from the run's bound tables."""
    scales = {
        name: _column(tables[f"ul_charge_scales/{name}"], variant_id) for name in SCALE_FIELDS
    }
    return ChargeSchedule(
        pac_rate=scales["premium_allocation_rate"],
        admin=scales["admin_charge_monthly"],
        loyalty_rate=scales["loyalty_rate"],
        booster_rate=scales["booster_rate"],
        disc_pct_low=scales["disc_pct_low"],
        disc_cap_low=scales["disc_cap_low"],
        disc_pct_high=scales["disc_pct_high"],
        disc_cap_high=scales["disc_cap_high"],
        riy_cap=_column(tables["ul_riy_caps"], regime_id),
        mortality_per_mille=_column(tables["mortality_charges_ul"], charge_column),
    )


def case_from_row(row: Mapping[str, Any], tables: Mapping[str, Table], label: str = "") -> Case:
    """A case from one prepared model point (the engine's field contract), as sold: the
    contract terms, the variant's features and the funds that receive premiums."""
    slots = [
        (float(row[f"Fund_{k}_Allocation"]), float(row[f"Fund_{k}_FMC"]))
        for k in range(1, MAX_FUND_SLOTS + 1)
        if float(row[f"Fund_{k}_Allocation"]) > 0
    ]
    if not slots:
        raise InputError(f"{label or row.get('Policy_Number')}: no fund receives premiums")
    return Case(
        term_years=int(row["Policy_Term"]),
        payment_years=int(row["Premium_Payment_Term"]),
        frequency=int(row["Premium_Frequency"]),
        instalment=float(row["Instalment_Premium"]),
        annualised_premium=float(row["Annualised_Premium"]),
        instalments_payable=int(row["Instalments_Payable"]),
        sum_assured=float(row["Sum_Assured"]),
        entry_age=int(row["Age_at_Entry"]),
        emr=float(row["EMR"]),
        flat_extra=float(row["Flat_Extra"]),
        flat_extra_months=int(row["Flat_Extra_Term_Months"]),
        features={name: float(row[f"V_{name}"]) for name in FEATURES},
        allocations=tuple(a for a, _ in slots),
        fmcs=tuple(c for _, c in slots),
        schedule=schedule_for(
            tables, int(row["Variant_Id"]), int(row["Regime_Id"]), int(row["Charge_Column"])
        ),
        label=label or str(row.get("Policy_Number", "")),
    )


def library_gross(annual: float) -> Gross:
    """A fixed gross return on every asset class through the scenario library's `flat`
    operation, so the demonstration uses exactly the library's monthly equivalent."""
    names = [f"ret_{asset}" for asset in ASSET_CLASSES]
    base = ScenarioSet(
        variables={name: np.zeros((1, 2)) for name in names},
        ids=("1",),
        weights=np.array([1.0]),
        measure="deterministic",
        provenance={},
    )
    paths = flat(base, names, annual).variables
    monthly = {float(paths[name][0, 1]) for name in names}
    if len(monthly) != 1:
        raise InputError("a gross return must be the same for every asset class")
    return Gross(float(annual), monthly.pop())


def _gross_returns(rates: Sequence[float]) -> tuple[Gross, ...]:
    if not rates:
        raise InputError("at least one gross return is needed")
    if len(set(rates)) != len(rates):
        raise InputError("gross returns must be distinct")
    return tuple(library_gross(float(rate)) for rate in rates)


def _label(rate: float) -> str:
    return f"{rate * 100:g}pct"


def _keyed(table: Table) -> dict[str, dict[str, float]]:
    """A keyed table as `{key: {field: value}}`."""
    fields = list(table.axes[1].keys)
    return {
        str(key): {str(field): float(table.values[i, j]) for j, field in enumerate(fields)}
        for i, key in enumerate(table.axes[0].keys)
    }


def _load(config: str | Path | RunConfig, root: str | Path | None) -> CheckReport:
    cfg = config if isinstance(config, RunConfig) else load_run_config(config)
    if tuple(cfg.products_to_run) != (CODE,) or cfg.run_type != "Valuation":
        raise InputError(f"the compliance layer needs a {CODE} Valuation run")
    return check(cfg, root=root)


def case_for_variant(
    tables: Mapping[str, Table],
    variant: str,
    *,
    term: int,
    frequency: int,
    annualised_premium: float,
    fund: str,
) -> Case:
    """A new policy of a variant for the pricing-time demonstration: a standard life, one
    fund, premiums for the whole term, at inception."""
    variants, funds = _keyed(tables["ul_variants"]), _keyed(tables["ul_funds"])
    if variant not in variants:
        raise InputError(f"unknown product variant {variant!r}")
    if fund not in funds:
        raise InputError(f"unknown fund {fund!r}")
    values = variants[variant]
    single = bool(values["single_premium"])
    modal = 0 if single else frequency
    if not single and modal not in (1, 2, 4, 12):
        raise InputError(f"premium frequency {frequency} must be 1, 2, 4 or 12")
    return Case(
        term_years=term,
        payment_years=0 if single else term,
        frequency=modal,
        instalment=annualised_premium if single else annualised_premium / modal,
        annualised_premium=annualised_premium,
        instalments_payable=1 if single else modal * term,
        sum_assured=(1.25 if single else 10.0) * annualised_premium,
        entry_age=ENTRY_AGE,
        emr=1.0,
        flat_extra=0.0,
        flat_extra_months=0,
        features={name: values[name] for name in FEATURES},
        allocations=(1.0,),
        fmcs=(funds[fund]["fmc"],),
        schedule=schedule_for(tables, int(values["variant_id"]), int(values["regime_id"]), 0),
        label=variant,
    )


def _worst_fund(tables: Mapping[str, Table]) -> str:
    """The selectable fund with the highest management charge: the binding case."""
    funds = _keyed(tables["ul_funds"])
    selectable = {code: v["fmc"] for code, v in funds.items() if v["selectable"] == 1}
    return max(selectable, key=lambda code: (selectable[code], code))


def _levels(frame: pl.DataFrame, variant: str) -> tuple[float, ...]:
    """The lowest and highest annualised premium of the variant's policies (the book's when
    the variant has none): small premiums carry the flat charges hardest."""
    own = frame.filter(pl.col("Product Variant") == variant)["Annualised_Premium"]
    values = own if own.len() else frame["Annualised_Premium"]
    low, high = float(values.min()), float(values.max())  # type: ignore[arg-type]
    return (low,) if low == high else (low, high)


def _ints(values: Sequence[int], name: str, minimum: int) -> tuple[int, ...]:
    if not values or any(v < minimum for v in values):
        raise InputError(f"{name} need at least one value, each at least {minimum}")
    return tuple(dict.fromkeys(int(v) for v in values))


@dataclass(frozen=True)
class ComplianceReport:
    """The pricing-time demonstration: `cases` (one row per variant, case, gross return and
    policy year), `summary` (one row per variant, case and gross return) and `variants` (one
    row per variant with its worst status at each gross return)."""

    cases: pl.DataFrame
    summary: pl.DataFrame
    variants: pl.DataFrame
    files: tuple[Path, ...] = ()

    @property
    def passed(self) -> bool:
        """Whether every case passes at every gross return (with additions where allowed)."""
        return bool(self.summary["Status"].is_in(["pass", "pass_with_additions"]).all())


def _case_rows(rate: float, result: Assessment, key: dict[str, Any]) -> list[dict[str, Any]]:
    design, added = result.design, result.with_additions
    return [
        {
            **key,
            "Gross_Return": rate,
            "Policy_Year": int(year),
            "Net_Yield": float(design.net_yield[i]),
            "RIY": float(design.riy[i]),
            "RIY_Cap": float(design.cap[i]),
            "Excess": float(design.excess[i]),
            "Within_Cap": bool(design.excess[i] <= 1e-12),
            "Residual_Addition": float(added.residual[i]),
            "RIY_With_Additions": float(added.riy[i]),
        }
        for i, year in enumerate(design.years)
    ]


def ul_compliance(
    config: str | Path | RunConfig,
    *,
    root: str | Path | None = None,
    rates: Sequence[float] = RATES,
    terms: Sequence[int] = TERMS,
    frequencies: Sequence[int] = FREQUENCIES,
    premiums: Sequence[float] | None = None,
    fund: str | None = None,
    output: str | Path | None = None,
) -> ComplianceReport:
    """Test every variant of `ul_variants` against the RIY caps at each gross return.

    Cases per variant: each term, each premium frequency (a single premium variant has one
    case), the lowest and highest premium of the book (or `premiums`), in the selectable fund
    with the highest management charge (or `fund`)."""
    grosses = _gross_returns(rates)
    term_list = _ints(terms, "terms", FIRST_MEASUREMENT_YEAR)
    frequency_list = _ints(frequencies, "frequencies", 1)
    report = _load(config, root)
    assert report.points is not None
    tables = report.tables
    chosen = fund or _worst_fund(tables)
    regimes = {int(v["regime_id"]): k for k, v in _keyed(tables["ul_regulatory_caps"]).items()}
    rows: list[dict[str, Any]] = []
    summary: list[dict[str, Any]] = []
    for variant, values in _keyed(tables["ul_variants"]).items():
        levels = tuple(premiums) if premiums else _levels(report.points.frame, variant)
        modes = (0,) if values["single_premium"] else frequency_list
        for term in term_list:
            for frequency in modes:
                for premium in levels:
                    case = case_for_variant(
                        tables,
                        variant,
                        term=term,
                        frequency=frequency,
                        annualised_premium=float(premium),
                        fund=chosen,
                    )
                    key = {
                        "Variant": variant,
                        "Regime": regimes[int(values["regime_id"])],
                        "Policy_Term": term,
                        "Premium_Frequency": frequency,
                        "Annualised_Premium": float(premium),
                        "Fund": chosen,
                    }
                    for gross in grosses:
                        result = assess(case, gross)
                        rows += _case_rows(gross.annual, result, key)
                        summary.append(
                            {
                                **key,
                                "Gross_Return": gross.annual,
                                "Status": result.status,
                                "First_Breach_Year": result.first_breach_year,
                                "Max_RIY": float(result.design.riy.max()),
                                "Worst_Margin": result.worst_margin,
                                "Total_Residual_Additions": float(
                                    result.with_additions.residual.sum()
                                ),
                            }
                        )
    cases = pl.DataFrame(rows)
    table = pl.DataFrame(summary, schema_overrides={"First_Breach_Year": pl.Int64})
    roll = _roll_up(table, [g.annual for g in grosses])
    files: tuple[Path, ...] = ()
    if output is not None:
        sink = CsvSink(Path(output))
        files = (
            sink.write_table("ul_riy_cases", cases),
            sink.write_table("ul_riy_summary", table),
            sink.write_table("ul_riy_variants", roll),
        )
    return ComplianceReport(cases, table, roll, files)


def _roll_up(summary: pl.DataFrame, rates: Sequence[float]) -> pl.DataFrame:
    """Per variant: the worst status over its cases at each gross return."""
    rows = []
    for variant in summary["Variant"].unique(maintain_order=True):
        own = summary.filter(pl.col("Variant") == variant)
        row: dict[str, Any] = {
            "Variant": variant,
            "Regime": own["Regime"][0],
            "Cases": own.height // len(rates),
        }
        for rate in rates:
            found = own.filter(pl.col("Gross_Return") == rate)["Status"].to_list()
            row[f"Status_{_label(rate)}"] = max(found, key=SEVERITY.__getitem__)
        rows.append(row)
    return pl.DataFrame(rows)
