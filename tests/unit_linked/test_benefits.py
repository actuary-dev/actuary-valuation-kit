"""Unit and general-fund shares of insured benefits."""

import pytest


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
