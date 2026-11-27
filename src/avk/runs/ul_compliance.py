"""UNIT_LINKED compliance layer: reduction in yield, residual additions, the pricing-time
demonstration and the benefit illustration.

This module reads a run through the normal input gate (`check`), builds single-life cases
from the prepared book or from the variant, fund and charge tables, and calls the pure
projection in `avk.products.unit_linked.illustration`.
"""

from collections.abc import Mapping
from typing import Any

from avk.model.data import Table
from avk.products.unit_linked.bindings import MAX_FUND_SLOTS
from avk.products.unit_linked.illustration import FEATURES, Case, ChargeSchedule
from avk.runtime.errors import InputError

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
