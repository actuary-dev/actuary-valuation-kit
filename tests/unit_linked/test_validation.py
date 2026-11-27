"""Unit-linked policy, holdings, table and cap validation."""

from dataclasses import replace

import numpy as np
import polars as pl
import pytest
from conftest import VALUATION, holding

from avk.products.unit_linked.validation import (
    UnitLinkedPolicyValidator,
    check_policies_against_tables,
    check_tables,
)

VALIDATOR = UnitLinkedPolicyValidator()


def errors(policies, holdings=None):
    issues = VALIDATOR.validate_at(policies, VALUATION)
    if holdings is not None and not issues:
        issues = VALIDATOR.validate_companions(policies, {"policy_funds_ul": holdings}, VALUATION)
    return [i.message for i in issues if i.severity == "error"]


def setting(frame, number, column, value):
    return frame.with_columns(
        pl.when(pl.col("Policy Number") == number)
        .then(pl.lit(value))
        .otherwise(pl.col(column))
        .alias(column)
    )


def holdings_setting(frame, number, fund, column, value):
    target = (pl.col("Policy Number") == number) & (pl.col("Fund Code") == fund)
    return frame.with_columns(
        pl.when(target).then(pl.lit(value)).otherwise(pl.col(column)).alias(column)
    )


def assert_one(messages, fragment):
    assert any(fragment in m for m in messages), messages


def test_valid_book_passes(book, ul_tables):
    policies, holdings = book
    assert errors(policies, holdings) == []
    assert check_tables(ul_tables) == []
    assert check_policies_against_tables(policies, holdings, ul_tables) == []


# Policy rows ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("number", "column", "value", "fragment"),
    [
        ("UL1", "Product Code", "TERM", "policies_ul: Product Code must be UNIT_LINKED"),
        (
            "UL1",
            "Valuation Date",
            "2025-12-30",
            "policies_ul: Valuation Date must equal the run's valuation date 2025-12-31",
        ),
        ("UL1", "Policy Status", 3, "policies_ul: Policy Status must be one of [0, 1, 2]"),
        (
            "UL1",
            "Premium Frequency",
            3,
            "policies_ul: Premium Frequency must be one of [0, 1, 2, 4, 12]",
        ),
        (
            "UL1",
            "Premium Frequency",
            0,
            "policies_ul: Premium Frequency 0 (single premium) if and only if",
        ),
        (
            "UL6",
            "Premium Payment Term (Years)",
            5,
            "policies_ul: Premium Frequency 0 (single premium) if and only if",
        ),
        ("UL1", "Gender", "X", "policies_ul: Gender must be one of ['M', 'F', 'T']"),
        ("UL1", "Smoking Status", "Y", "policies_ul: Smoking Status must be one of ['NS', 'S']"),
        (
            "UL1",
            "Status Date",
            "2019-01-01",
            "policies_ul: dates must satisfy Policy Start Date <= Status Date <= valuation date",
        ),
        (
            "UL1",
            "Status Date",
            "2026-01-01",
            "policies_ul: dates must satisfy Policy Start Date <= Status Date <= valuation date",
        ),
        (
            "UL1",
            "Age at Policy Start",
            35,
            "policies_ul: Age at Policy Start must equal completed years",
        ),
        ("UL1", "Mortality Charges To Date", -1.0, "policies_ul: amounts must be nonnegative"),
        (
            "UL1",
            "Paid Up Sum Assured",
            10.0,
            "policies_ul: Paid Up Sum Assured > 0 if and only if Policy Status is 2",
        ),
        (
            "UL5",
            "Paid Up Sum Assured",
            0.0,
            "policies_ul: Paid Up Sum Assured > 0 if and only if Policy Status is 2",
        ),
        ("UL1", "Currency", "USD", "policies_ul: a run holds a single Currency"),
        ("UL2", "Policy Number", "UL1", "policies_ul: duplicate Policy Number"),
        ("UL1", "Date of Birth", "not a date", "policies_ul: unparseable date(s)"),
        ("UL1", "Sum Assured", float("nan"), "policies_ul: non-numeric or non-finite"),
        ("UL1", "Measurement Model", "PAA", "policies_ul: Measurement Model must be one of"),
    ],
)
def test_policy_rules(book, number, column, value, fragment):
    policies, _ = book
    assert_one(errors(setting(policies, number, column, value)), fragment)


def test_policy_columns_required_and_non_null(book):
    policies, _ = book
    assert_one(errors(policies.drop("Legal Entity")), "policies_ul: missing required column(s)")
    assert_one(errors(setting(policies, "UL3", "Portfolio", None)), "policies_ul: missing value(s)")


# Holding rows --------------------------------------------------------------------------


def test_holding_columns_required_and_non_null(book):
    policies, holdings = book
    assert_one(
        errors(policies, holdings.drop("Switches In To Date")),
        "policy_funds_ul: missing required column(s)",
    )
    assert_one(
        errors(policies, holdings_setting(holdings, "UL2", "DT_GILT", "Units", None)),
        "policy_funds_ul: missing value(s)",
    )


@pytest.mark.parametrize(
    ("number", "fund", "column", "value", "fragment"),
    [
        (
            "UL2",
            "DT_GILT",
            "Fund Code",
            "EQ_INDEX",
            "policy_funds_ul: Policy Number + Fund Code must be unique",
        ),
        (
            "UL1",
            "EQ_LARGE_CAP",
            "Product Code",
            "TERM",
            "policy_funds_ul: Product Code and Valuation Date must equal the policy's",
        ),
        (
            "UL1",
            "EQ_LARGE_CAP",
            "Valuation Date",
            "2025-11-30",
            "policy_funds_ul: Product Code and Valuation Date must equal the policy's",
        ),
        ("UL1", "EQ_LARGE_CAP", "Units", -1.0, "policy_funds_ul: values must be nonnegative"),
        (
            "UL5",
            "MM_LIQUID",
            "Premium Allocation",
            1.5,
            "policy_funds_ul: Premium Allocation must lie in [0, 1]",
        ),
        (
            "UL2",
            "DT_GILT",
            "Premium Allocation",
            0.3999999,
            "policy_funds_ul: allocations of a premium-paying policy must sum to 1",
        ),
        (
            "UL1",
            "EQ_LARGE_CAP",
            "Premiums Allocated To Fund",
            700000.0,
            "policies_ul: Premiums Paid To Date must be at least the sum of Premiums Allocated",
        ),
    ],
)
def test_holding_rules(book, number, fund, column, value, fragment):
    policies, holdings = book
    assert_one(errors(policies, holdings_setting(holdings, number, fund, column, value)), fragment)


def test_allocation_tolerance(book):
    policies, holdings = book
    within = holdings_setting(holdings, "UL2", "DT_GILT", "Premium Allocation", 0.4 + 5e-10)
    assert errors(policies, within) == []
    outside = holdings_setting(holdings, "UL1", "EQ_LARGE_CAP", "Premium Allocation", 0.9999999)
    assert_one(errors(policies, outside), "allocations of a premium-paying policy must sum to 1")


def test_allocation_after_premium_term_not_checked(book):
    policies, holdings = book
    paid_up = holdings_setting(holdings, "UL5", "MM_LIQUID", "Premium Allocation", 0.1)
    assert errors(policies, paid_up) == []


def test_every_policy_holds_a_fund(book):
    policies, holdings = book
    assert_one(
        errors(policies, holdings.filter(pl.col("Policy Number") != "UL1")),
        "policy_funds_ul: 1 policy(ies) hold no fund",
    )


def test_orphan_holdings(book):
    policies, holdings = book
    extra = pl.concat([holdings, pl.DataFrame([holding("UL9", "EQ_INDEX", 1.0, 1.0)])])
    known = set(policies["Policy Number"])
    issues = VALIDATOR.companion_orphans(
        lambda values: values.is_in(list(known)), {"policy_funds_ul": extra}
    )
    assert [i.message for i in issues] == [
        "policy_funds_ul: 1 holding row(s) for 1 Policy Number(s) absent from policies_ul"
    ]


# Policies against tables ---------------------------------------------------------------


def test_more_than_max_fund_slots(book, ul_tables):
    policies, holdings = book
    sixth = pl.DataFrame([holding("UL3", "EQ_GLOBAL", 10.0, 0.0)])
    messages = check_policies_against_tables(policies, pl.concat([holdings, sixth]), ul_tables)
    assert_one(messages, "policy_funds_ul: a policy holds more than MAX_FUND_SLOTS (5)")


@pytest.mark.parametrize("code", ["eq_large_cap", "EQ_LARGE_CAP ", " EQ_LARGE_CAP"])
def test_fund_code_matches_exactly(book, ul_tables, code):
    policies, holdings = book
    changed = holdings_setting(holdings, "UL1", "EQ_LARGE_CAP", "Fund Code", code)
    assert_one(
        check_policies_against_tables(policies, changed, ul_tables),
        "policy_funds_ul: Fund Code must exist in ul_funds (exact match)",
    )


def test_unknown_variant(book, ul_tables):
    policies, holdings = book
    changed = setting(policies, "UL1", "Product Variant", "ULIP_UNKNOWN")
    assert_one(
        check_policies_against_tables(changed, holdings, ul_tables),
        "policies_ul: Product Variant must exist in ul_variants",
    )


def test_dpf_rules(book, ul_tables):
    policies, holdings = book
    extra = pl.DataFrame([holding("UL4", "MM_LIQUID", 10.0, 0.0)])
    assert_one(
        check_policies_against_tables(policies, pl.concat([holdings, extra]), ul_tables),
        "policy_funds_ul: a Policy Status 1 policy holds exactly one row, in the DPF",
    )
    moved = holdings_setting(holdings, "UL4", "DPF", "Fund Code", "MM_LIQUID")
    assert_one(
        check_policies_against_tables(policies, moved, ul_tables),
        "a Policy Status 1 policy holds exactly one row, in the DPF",
    )
    dpf = pl.DataFrame([holding("UL1", "DPF", 10.0, 0.0)])
    assert_one(
        check_policies_against_tables(policies, pl.concat([holdings, dpf]), ul_tables),
        "policy_funds_ul: only Policy Status 1 policies hold the DPF",
    )
    allocated = holdings_setting(holdings, "UL4", "DPF", "Premium Allocation", 0.5)
    assert_one(
        check_policies_against_tables(policies, allocated, ul_tables),
        "policy_funds_ul: Premium Allocation must be 0 for non-selectable funds",
    )


def test_minimum_sum_assured(book, ul_tables):
    policies, holdings = book
    regular = setting(policies, "UL1", "Sum Assured", 699999.0)
    assert_one(
        check_policies_against_tables(regular, holdings, ul_tables),
        "policies_ul: Sum Assured below the regime's minimum multiple",
    )
    single = setting(policies, "UL6", "Sum Assured", 600000.0)
    assert_one(
        check_policies_against_tables(single, holdings, ul_tables),
        "policies_ul: Sum Assured below the regime's minimum multiple",
    )
    old = setting(
        setting(
            setting(policies, "UL1", "Sum Assured", 500000.0), "UL1", "Age at Policy Start", 50
        ),
        "UL1",
        "Date of Birth",
        "1969-07-15",
    )
    assert check_policies_against_tables(old, holdings, ul_tables) == []


def test_single_premium_variant_needs_frequency_zero(book, ul_tables):
    policies, holdings = book
    changed = setting(policies, "UL1", "Product Variant", "ULIP_SINGLE")
    assert_one(
        check_policies_against_tables(changed, holdings, ul_tables),
        "policies_ul: Premium Frequency 0 if and only if the variant is single premium",
    )


# Tables --------------------------------------------------------------------------------


def changed(tables, name, key, field, value):
    table = tables[name]
    values = np.array(table.values)
    values[table.axes[0].keys.index(key), table.axes[1].keys.index(field)] = value
    return {**tables, name: replace(table, values=values)}


def changed_year(tables, name, year, key, value):
    table = tables[name]
    values = np.array(table.values)
    values[year - 1, table.axes[1].keys.index(key)] = value
    return {**tables, name: replace(table, values=values)}


@pytest.mark.parametrize(
    ("name", "key", "field", "value", "fragment"),
    [
        (
            "ul_funds",
            "EQ_INDEX",
            "w_eq_large",
            0.97,
            "ul_funds: asset weights of a fund must sum to 1",
        ),
        ("ul_funds", "EQ_INDEX", "is_dpf", 1.0, "ul_funds: exactly one fund has is_dpf 1"),
        ("ul_funds", "DPF", "selectable", 1.0, "ul_funds: exactly one fund has is_dpf 1"),
        ("ul_funds", "EQ_INDEX", "fmc", 1.0, "ul_funds: fmc must be below 1"),
        ("ul_funds", "EQ_INDEX", "unit_price", 0.0, "ul_funds: unit_price must exceed 0"),
        ("ul_variants", "ULIP_SINGLE", "variant_id", 0.0, "ul_variants: variant_id must be unique"),
        ("ul_variants", "ULIP_SINGLE", "regime_id", 7.0, "ul_variants: regime_id must exist"),
        ("ul_variants", "ULIP_SINGLE", "rpu_mode", 3.0, "ul_variants: rpu_mode must be one of"),
        (
            "ul_variants",
            "ULIP_LIMITED_PAY_ROC",
            "admin_escalation",
            0.06,
            "variant ULIP_LIMITED_PAY_ROC breaches IRDAI_2024: admin_escalation above",
        ),
        (
            "ul_variants",
            "ULIP_MATURITY_GUARANTEE",
            "guarantee_charge",
            0.006,
            "breaches IRDAI_2024: guarantee_charge above guarantee_charge_max",
        ),
        (
            "ul_variants",
            "ULIP_CLASSIC",
            "min_db_premium_multiple",
            1.0,
            "breaches IRDAI_2024: min_db_premium_multiple below",
        ),
        (
            "ul_variants",
            "ULIP_CLASSIC",
            "lock_in_months",
            36.0,
            "breaches IRDAI_2024: lock_in_months below lock_in_months_min",
        ),
        ("ul_regulatory_caps", "UNCAPPED", "caps_apply", 2.0, "caps_apply must be one of [0, 1]"),
    ],
)
def test_table_rules(ul_tables, name, key, field, value, fragment):
    assert_one(check_tables(changed(ul_tables, name, key, field, value)), fragment)


def test_uncapped_variant_not_checked(ul_tables):
    tables = changed(ul_tables, "ul_variants", "UL_INVESTMENT_BOND", "admin_escalation", 0.2)
    assert check_tables(tables) == []


@pytest.mark.parametrize(
    ("field", "year", "value", "fragment"),
    [
        ("premium_allocation_rate", 7, 0.13, "premium_allocation_rate above pac_max"),
        ("premium_allocation_rate", 2, 0.019, "first-five-year allocation ratio"),
        ("premium_allocation_rate", 3, 0.0, "first-five-year allocation ratio"),
        ("admin_charge_monthly", 12, 501.0, "admin_charge_monthly above admin_max_monthly"),
        ("disc_pct_low", 2, 0.16, "disc_pct_low above ul_disc_charge_caps"),
        ("disc_cap_high", 6, 1.0, "disc_cap_high above ul_disc_charge_caps"),
    ],
)
def test_scale_caps(ul_tables, field, year, value, fragment):
    tables = changed_year(ul_tables, f"ul_charge_scales/{field}", year, 0, value)
    assert_one(check_tables(tables), f"variant ULIP_CLASSIC breaches IRDAI_2024: {fragment}")


def test_all_zero_first_years_pass_ratio(ul_tables):
    tables = ul_tables
    for year in range(1, 6):
        tables = changed_year(tables, "ul_charge_scales/premium_allocation_rate", year, 4, 0.0)
    assert check_tables(tables) == []


def test_scale_keys_match_variants(ul_tables):
    table = ul_tables["ul_charge_scales/loyalty_rate"]
    axis = replace(table.axes[1], keys=(0, 1, 2, 3, 4, 9))
    tables = {
        **ul_tables,
        "ul_charge_scales/loyalty_rate": replace(table, axes=(table.axes[0], axis)),
    }
    assert_one(check_tables(tables), "ul_charge_scales: keys of loyalty_rate must be exactly")


def test_regime_keys_match_caps(ul_tables):
    table = ul_tables["ul_riy_caps"]
    axis = replace(table.axes[1], keys=(0, 5))
    tables = {**ul_tables, "ul_riy_caps": replace(table, axes=(table.axes[0], axis))}
    assert_one(check_tables(tables), "ul_riy_caps: keys must be exactly the regime_ids")


def test_fmc_cap_of_held_funds(book, ul_tables):
    policies, holdings = book
    tables = changed(ul_tables, "ul_funds", "EQ_LARGE_CAP", "fmc", 0.014)
    assert_one(
        check_policies_against_tables(policies, holdings, tables),
        "ul_funds: fmc of a fund held under a capped regime above its cap",
    )
    tables = changed(ul_tables, "ul_funds", "DPF", "fmc", 0.006)
    assert_one(
        check_policies_against_tables(policies, holdings, tables),
        "fmc of a fund held under a capped regime above its cap",
    )


def test_dpf_fmc_cap_applies_before_any_projected_transfer(ul_tables):
    tables = changed(ul_tables, "ul_funds", "DPF", "fmc", 0.006)
    messages = check_tables(tables)
    assert any(
        "variant ULIP_CLASSIC breaches IRDAI_2024: DPF fmc above dpf_fmc_max" in m for m in messages
    )
    assert all("UL_INVESTMENT_BOND" not in m for m in messages)
