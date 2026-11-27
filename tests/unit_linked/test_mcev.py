"""MCEV on the market-consistent basis: PVFP, frictional cost, CRNHR, VIF and the BEL."""

import numpy as np

from avk.products.unit_linked.bindings import MAX_FUND_SLOTS
from avk.products.unit_linked.formulas import UnitLinked

SLOTS = range(1, MAX_FUND_SLOTS + 1)


def end_of_month_pv(cashflows, rates):
    """Variant A present values at the end of each month by forward discount factors."""
    months = cashflows.shape[1]
    factor = np.ones(months)
    for s in range(1, months):
        factor[s] = factor[s - 1] / (1 + rates[s])
    values = np.zeros_like(cashflows)
    for t in range(months):
        values[:, t] = (cashflows[:, t + 1 :] * factor[t + 1 :]).sum(axis=1) / factor[t]
    return values


def test_mc_funds_grow_at_the_reference_rate(ul_projection):
    model, _ = ul_projection()
    rf = model.scenario("reference_forward")
    mc = model["mc"]
    live = mc("live").astype(bool)
    for k in SLOTS:
        rate = mc(f"fund_{k}_growth_rate")
        np.testing.assert_array_equal(rate[live], np.broadcast_to(rf, rate.shape)[live])
    dpf = mc("dpf_return")
    np.testing.assert_array_equal(dpf[live], np.broadcast_to(rf, dpf.shape)[live])
    be = model["be"]
    assert not np.array_equal(be("fund_1_growth_rate")[live], mc("fund_1_growth_rate")[live])


def test_pvfp_is_computed_from_the_mc_path(ul_projection, tmp_path, assert_parity):
    model, _ = ul_projection()
    mc, be = model["mc"], model["be"]
    rf = model.scenario("reference_forward")
    np.testing.assert_array_equal(mc("mc_net_cf"), -mc("net_cashflows"))
    assert not np.allclose(mc("net_cashflows"), be("net_cashflows"))
    expected = end_of_month_pv(mc("mcev_net_profit"), rf)
    assert_parity(tmp_path, {"pvfp": mc("pvfp")}, {"pvfp": expected})
    premiums = end_of_month_pv(mc("premium_income") * (1 + rf), rf)
    np.testing.assert_allclose(mc("pv_premium"), premiums, rtol=1e-10, atol=1e-6)


def test_frictional_cost_is_the_leakage_on_capital_interest(ul_projection, tmp_path, assert_parity):
    model, _ = ul_projection()
    mc = model["mc"]
    params = model.params("mc")
    rf = model.scenario("reference_forward")
    tax, transfer = params["Tax Rate"], params["profit_transfer_rate"]
    capital = mc("required_solvency_capital")
    opening = np.zeros_like(capital)
    opening[:, 1:] = capital[:, :-1]
    friction = opening * rf * (tax + (1 - tax) * transfer)
    np.testing.assert_allclose(mc("frictional_cost"), friction, rtol=1e-12, atol=1e-12)
    crnhr = params["cost_of_capital_rate"] / 12 * capital
    np.testing.assert_allclose(mc("crnhr_charge"), crnhr, rtol=1e-12, atol=1e-12)
    assert_parity(
        tmp_path,
        {"fcc": mc("fcc"), "crnhr": mc("crnhr")},
        {"fcc": end_of_month_pv(friction, rf), "crnhr": end_of_month_pv(crnhr, rf)},
    )
    assert (mc("fcc")[:, 0] > 0).all()


def test_vif_and_bel(ul_projection):
    model, _ = ul_projection()
    mc = model["mc"]
    np.testing.assert_array_equal(mc("vif"), mc("pvfp") - mc("fcc") - mc("crnhr"))
    np.testing.assert_array_equal(mc("bel")[:, 0], mc("unit_reserve")[:, 0] + mc("gf_bel")[:, 0])
    np.testing.assert_allclose(mc("gf_bel"), mc("gf_reserve_dcf"), rtol=1e-10, atol=1e-6)
    lives = mc("lives_end") + mc("maturities")
    np.testing.assert_allclose(mc("bel_pp")[:, 0], mc("bel")[:, 0] / lives[:, 0], rtol=1e-15)


def test_mc_fund_path_equals_be_path_when_source_is_one(ul_projection):
    model, _ = ul_projection(mc_params={"mc_fund_return_source": 1.0})
    mc, be = model["mc"], model["be"]
    for name in (*(f"fund_{k}_growth_rate" for k in SLOTS), "dpf_return", "unit_reserve"):
        np.testing.assert_array_equal(mc(name), be(name))
    for basis in UnitLinked.BASES:
        assert np.isfinite(model[basis]("unit_reserve")).all()
