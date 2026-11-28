"""Unit-linked model points: policy fields, features, the DPF and fund slots."""

from types import SimpleNamespace

import polars as pl
import pytest
from conftest import VALUATION, holding

from avk.products.unit_linked.preparation import (
    PREPARED_FIELDS,
    UnitLinkedModelPointAdapter,
)
from avk.runtime.errors import InputError
from avk.testing.parity import compare

CONFIG = SimpleNamespace(
    valuation_date=VALUATION,
    projection_term=40,
    run_type="Valuation",
    products_to_run=("UNIT_LINKED",),
)


def prepare(tables, policies, holdings):
    adapter = UnitLinkedModelPointAdapter(
        "UNIT_LINKED", "policies_ul", tables, PREPARED_FIELDS, holdings
    )
    return adapter.prepare(policies, CONFIG)


def rows(points):
    frame = points.frame
    return {row["Policy_Number"]: row for row in frame.iter_rows(named=True)}


def test_fields_are_the_contract(book, ul_tables):
    points = prepare(ul_tables, *book)
    assert points.fields == PREPARED_FIELDS
    assert set(PREPARED_FIELDS) <= set(points.frame.columns)
    assert len(PREPARED_FIELDS) == len(set(PREPARED_FIELDS)) == 46 + 31 + 3 + 13 + 5 * 22
    assert points.frame["Policy_Number"].to_list() == ["UL1", "UL2", "UL3", "UL4", "UL5", "UL6"]


def test_slot_fields(book, ul_tables):
    got = rows(prepare(ul_tables, *book))
    # UL3 holds five funds; slots follow the funds' positions in ul_funds keys.
    expected = [
        ("ALT_GOLD", 5000 * 12.84, 0.1),
        ("DT_CORP_BOND", 4000 * 30.95, 0.2),
        ("EQ_LARGE_CAP", 1000 * 42.18, 0.3),
        ("EQ_MID_CAP", 2000 * 58.25, 0.2),
        ("HY_BALANCED", 3000 * 29.81, 0.2),
    ]
    keys = ul_tables["ul_funds"].axes[0].keys
    for k, (fund, value, share) in enumerate(expected, start=1):
        assert got["UL3"][f"Fund_{k}_Present"] == 1
        assert got["UL3"][f"Fund_{k}_Fund_Index"] == keys.index(fund)
        assert got["UL3"][f"Fund_{k}_Value"] == pytest.approx(value, rel=1e-15)
        assert got["UL3"][f"Fund_{k}_Allocation"] == share
    assert [keys.index(f) for f, _, _ in expected] == [0, 3, 11, 12, 18]
    # UL2: DT_GILT before EQ_INDEX; slots 3 to 5 empty.
    assert got["UL2"]["Fund_1_Value"] == pytest.approx(9000 * 26.33, rel=1e-15)
    assert got["UL2"]["Fund_2_Value"] == pytest.approx(12000 * 31.64, rel=1e-15)
    assert (got["UL2"]["Fund_1_Allocation"], got["UL2"]["Fund_2_Allocation"]) == (0.4, 0.6)
    for k in (3, 4, 5):
        assert got["UL2"][f"Fund_{k}_Present"] == 0
        assert got["UL2"][f"Fund_{k}_Fund_Index"] == -1
        assert got["UL2"][f"Fund_{k}_Value"] == 0.0
        assert got["UL2"][f"Fund_{k}_W_eq_large"] == 0.0
    # Fund attributes from ul_funds: DT_GILT 0.90% FMC, 85% long government bonds.
    assert got["UL2"]["Fund_1_FMC"] == 0.009 and got["UL2"]["Fund_1_W_gov_long"] == 0.85
    assert got["UL2"]["Fund_2_Alpha"] == -0.0015
    assert got["UL1"]["Fund_1_Premiums_Allocated"] == 100000.0
    assert got["UL1"]["Fund_1_Guaranteed_Price"] == 0.0


def test_dpf_policy(book, ul_tables):
    got = rows(prepare(ul_tables, *book))
    assert got["UL4"]["DPF_Value"] == pytest.approx(5800 * 14.62, rel=1e-15)
    assert all(got["UL4"][f"Fund_{k}_Present"] == 0 for k in range(1, 6))
    assert got["UL1"]["DPF_Value"] == 0.0
    for row in got.values():
        assert row["DPF_FMC"] == 0.005 and row["DPF_Alpha"] == 0.0
        assert row["DPF_W_gov_short"] == 0.4 and row["DPF_W_money_market"] == 0.6


def test_policy_fields(book, ul_tables):
    policies, holdings = book
    policies = policies.with_columns(
        pl.when(pl.col("Policy Number") == "UL2").then(pl.lit(v)).otherwise(pl.col(c)).alias(c)
        for c, v in (("Gender", "F"), ("Smoking Status", "S"))
    )
    got = rows(prepare(ul_tables, policies, holdings))
    assert (got["UL1"]["Instalment_Premium"], got["UL1"]["Instalments_Payable"]) == (100000.0, 20)
    assert got["UL2"]["Instalment_Premium"] == pytest.approx(100000 / 12, rel=1e-15)
    assert got["UL2"]["Instalments_Payable"] == 240
    assert (got["UL3"]["Instalment_Premium"], got["UL3"]["Instalments_Payable"]) == (25000.0, 40)
    assert (got["UL6"]["Instalment_Premium"], got["UL6"]["Instalments_Payable"]) == (500000.0, 1)
    # Months since the start, counting the start month (Term's Duration_in_Months).
    assert [got[n]["Duration_in_Months"] for n in ("UL1", "UL4", "UL5")] == [70, 31, 120]
    assert (got["UL2"]["Gender_Code"], got["UL2"]["Smoker_Code"]) == (1, 1)
    assert got["UL2"]["Charge_Column"] == 3 and got["UL1"]["Charge_Column"] == 0
    assert got["UL5"]["Policy_Status"] == 2.0 and got["UL5"]["Paid_Up_Sum_Assured"] == 300000.0
    assert got["UL1"]["Flat_Extra_Term_Months"] == 0
    assert got["UL1"]["MC_To_Date"] == 9000.0 and got["UL1"]["FV_Sum_Current_Year"] == 6500000.0


def test_variant_and_regime_fields(book, ul_tables):
    got = rows(prepare(ul_tables, *book))
    assert (got["UL1"]["Variant_Id"], got["UL1"]["Regime_Id"]) == (0, 0)
    assert got["UL2"]["V_death_benefit_type"] == 2 and got["UL1"]["V_death_benefit_type"] == 1
    assert got["UL1"]["V_lock_in_months"] == 60 and got["UL6"]["V_single_premium"] == 1
    assert got["UL3"]["V_ropac_fraction"] == 1.0 and got["UL3"]["V_auto_rebalance"] == 1
    assert got["UL1"]["R_dpf_min_rate"] == 0.04 and got["UL1"]["R_dpf_fmc_max"] == 0.005
    assert got["UL1"]["R_caps_apply"] == 1


def test_batches_give_the_same_points(book, ul_tables, tmp_path):
    policies, holdings = book
    whole = prepare(ul_tables, policies, holdings).frame
    parts = pl.concat(
        prepare(ul_tables, policies.slice(i, 2), holdings).frame for i in range(0, 6, 2)
    )
    whole.select(PREPARED_FIELDS).write_csv(tmp_path / "whole.csv")
    parts.select(PREPARED_FIELDS).write_csv(tmp_path / "parts.csv")
    classes = {name: "identifier" for name in PREPARED_FIELDS}
    compare(tmp_path / "parts.csv", tmp_path / "whole.csv", classes=classes).assert_ok()


def test_table_and_policy_errors_raise_together(book, ul_tables):
    policies, holdings = book
    bad = pl.concat([holdings, pl.DataFrame([holding("UL1", "eq_large_cap ", 1.0, 0.0)])])
    with pytest.raises(InputError, match="Fund Code must exist in ul_funds"):
        prepare(ul_tables, policies, bad)


def test_adapter_without_holdings_only_reads_codes(book, ul_tables):
    policies, _ = book
    adapter = UnitLinkedModelPointAdapter("UNIT_LINKED", "policies_ul", {}, PREPARED_FIELDS)
    assert adapter.product_codes(policies).to_list() == ["UNIT_LINKED"] * 6
    with pytest.raises(Exception, match="needs the policy_funds_ul table"):
        adapter.prepare(policies, CONFIG)
