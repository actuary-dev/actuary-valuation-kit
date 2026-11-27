"""Unit and general-fund shares of insured benefits."""

import numpy as np
import pytest

from avk.products.unit_linked.bindings import MAX_FUND_SLOTS
from avk.products.unit_linked.formulas import UnitLinked
from avk.runs.cases import Case


@pytest.mark.parametrize("death_type", [1, 2])
@pytest.mark.parametrize("sa", [1e6, 2e5])
def test_active_death_benefit_uses_the_closing_fund(ul_projection, death_type, sa):
    model, _ = ul_projection(0, V_death_benefit_type=death_type, Sum_Assured=sa)
    be = model["be"]
    fund = be("fund_close_total")[1]
    floor = be("floor_db")[1]
    expected = max(sa, fund, floor) if death_type == 1 else max(sa + fund, floor)
    assert be("deaths_A")[1] > 0
    assert be("death_unit_A")[1] == pytest.approx(be("deaths_A")[1] * fund)
    assert be("death_non_unit_A")[1] == pytest.approx(be("deaths_A")[1] * (expected - fund))


@pytest.mark.parametrize("death_type", [1, 2])
def test_paid_up_death_and_maturity_benefits(ul_projection, death_type):
    model, _ = ul_projection(
        4,
        V_death_benefit_type=death_type,
        Duration_in_Months=119,
        Policy_Term=10,
        V_rpu_mode=1,
        V_gmmb_on=1,
        V_gmmb_premium_multiple=10,
    )
    be = model["be"]
    pre_exit = be("rpu_after_fmc_total")[1]
    cover = be("pusa_open")[1]
    floor = be("rpu_floor_db")[1]
    expected = max(cover, pre_exit, floor) if death_type == 1 else max(cover + pre_exit, floor)
    assert be("death_unit_R")[1] == pytest.approx(pre_exit * be("q")[1])
    assert be("death_non_unit_R")[1] == pytest.approx((expected - pre_exit) * be("q")[1])
    assert be("maturity_unit_R")[1] == pytest.approx(pre_exit * be("maturities_R")[1])
    assert be("maturity_guarantee_R")[1] == pytest.approx(
        10 * be("rpu_tpp_open")[1] * be("maturities_R")[1] - be("maturity_unit_R")[1]
    )


def test_maturity_pays_fund_charges_return_and_guarantee_shortfall(ul_projection):
    model, _ = ul_projection(
        0,
        Duration_in_Months=119,
        Policy_Term=10,
        Premium_Payment_Term=10,
        Premium_Frequency=12,
        Instalment_Premium=100000 / 12,
        V_romc_fraction=0.8,
        V_ropac_fraction=0.2,
        V_roadmin_fraction=0.5,
        V_gmmb_on=1,
        V_gmmb_premium_multiple=5.0,
    )
    be = model["be"]
    fund = be("fund_close_total")[1]
    roc = 0.8 * be("mc_cum_pp")[1] + 0.2 * be("pac_cum_pp")[1] + 0.5 * be("admin_cum_pp")[1]
    gmmb = 5 * be("tpp_pp")[1] - fund - roc
    maturities = be("maturities_A")[1]
    assert gmmb > 0 and roc > 0 and maturities > 0
    assert be("maturity_unit_A")[1] == pytest.approx(maturities * fund)
    assert be("return_of_charges")[1] == pytest.approx(maturities * roc)
    assert be("maturity_guarantee_A")[1] == pytest.approx(maturities * gmmb)
    assert be("premium_pp")[1] > 0
    assert be("to_rpu")[1] == 0
    assert not be("unit_reserve")[1:].any()
    assert not be("fund_close_total")[2:].any()


@pytest.mark.parametrize(
    ("policy", "exit_column", "unit_payment"),
    [
        (0, "maturities_A", "maturity_unit_A"),
        (4, "maturities_R", "maturity_unit_R"),
        (3, "lockin_exits_D", "dpf_lockin_paid"),
    ],
    ids=["active", "paid-up", "discontinued"],
)
def test_policy_matured_at_valuation_settles_at_step_one(
    ul_projection, policy, exit_column, unit_payment
):
    model, frame = ul_projection(
        policy,
        Duration_in_Months=120,
        Policy_Term=10,
        Premium_Payment_Term=10,
        Premium_Frequency=12,
        V_rpu_mode=2,
        V_auto_rebalance=1,
        V_romc_fraction=0.8,
        V_ropac_fraction=0.2,
        V_roadmin_fraction=0.5,
        V_gmmb_on=1,
        V_gmmb_premium_multiple=5.0,
        V_guaranteed_addition_rate=0.01,
        case=Case("mass_lapse", {}, mass_lapse=0.5),
    )
    row = frame.row(0, named=True)
    slots = range(1, MAX_FUND_SLOTS + 1)
    opening = row["DPF_Value"] + sum(row[f"Fund_{i}_Value"] for i in slots)
    refund = 0.0
    top_up = 0.0
    if policy == 0:
        refund = 0.8 * row["MC_To_Date"] + 0.2 * row["PAC_To_Date"] + 0.5 * row["Admin_To_Date"]
        assert refund > 0
    if policy != 3:
        top_up = 5 * row["Premiums_Paid_To_Date"] - opening - refund
        assert top_up > 0
    assert opening > 0

    for basis in UnitLinked.BASES:
        data = model[basis]
        assert data("unit_reserve")[0] == opening
        assert data("lives_end")[0] == 1
        assert data(exit_column)[0] == data(unit_payment)[0] == 0
        assert data(exit_column)[1] == 1, basis
        assert data(unit_payment)[1] == opening
        assert data("return_of_charges")[1] == pytest.approx(refund)
        guarantee = data("maturity_guarantee_A")[1] + data("maturity_guarantee_R")[1]
        assert guarantee == pytest.approx(top_up)
        assert data("unit_benefit_outgo")[1] + data("non_unit_benefit_outgo")[1] == (
            pytest.approx(opening + refund + top_up)
        )
        for name in (
            "live",
            "premium_income",
            "charge_income",
            "addition_outgo",
            "partial_withdrawal_outgo",
            "dpf_credited_return",
            "q",
            "surrenders_A",
            "cessations_A",
            "surrenders_R",
            "expiries_R",
            "rebalance",
        ):
            assert data(name)[1] == 0, (name, basis)
        for i in slots:
            assert data(f"fund_{i}_growth_rate")[1] == 0
        np.testing.assert_array_equal(data("lives_end")[1:], 0)
        np.testing.assert_array_equal(data("unit_reserve")[1:], 0)
        assert data("unit_reserve")[1] == data("unit_reserve")[0] - data("unit_exit_benefits")[1]
