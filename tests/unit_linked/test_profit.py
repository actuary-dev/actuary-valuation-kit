"""Profit signature, the unit/non-unit segment split and solvency capital."""

import numpy as np
import pytest

from avk.products.unit_linked.formulas import UnitLinked

GUARANTEE_VARIANT = "ULIP_MATURITY_GUARANTEE"


def test_unit_segment_profit_is_nil_on_every_basis(ul_projection, tmp_path, assert_parity):
    model, _ = ul_projection()
    actual, expected = {}, {}
    for basis in UnitLinked.BASES:
        data = model[basis]
        profit = data("unit_segment_profit")
        # Nil within the money parity rule, on each policy's own scale of unit reserve.
        actual[f"{basis}_reserve_plus_profit"] = data("unit_reserve") + profit
        expected[f"{basis}_reserve_plus_profit"] = data("unit_reserve")
        assert (data("unit_fund_growth")[:, 1] != 0).any()
    assert_parity(tmp_path, actual, expected)
    be = model["be"]
    np.testing.assert_array_equal(
        be("total_profit"), be("unit_segment_profit") + be("non_unit_segment_profit")
    )
    np.testing.assert_array_equal(be("non_unit_segment_profit"), be("profit_before_tax"))


def test_reserve_roll_forward_ties(ul_projection, tmp_path, assert_parity):
    model, _ = ul_projection()
    be = model["be"]
    reserves = be("be_reserves")
    opening = np.zeros_like(reserves)
    opening[:, 1:] = reserves[:, :-1]
    rolled = opening + be("be_net_cf") + be("interest_on_reserves") - be("profit_before_tax")
    assert_parity(tmp_path, {"be_reserves": reserves}, {"be_reserves": rolled})
    roi = model.scenario("roi")
    np.testing.assert_allclose(be("interest_on_reserves")[:, 1:], opening[:, 1:] * roi[1:])
    reserving = model["reserving"]
    lives = be("lives_end") + be("maturities")
    np.testing.assert_allclose(
        reserves[:, 1:], (reserving("non_unit_reserve_pp") * lives)[:, 1:], rtol=1e-15
    )
    assert not reserves[:, 0].any()
    np.testing.assert_allclose(be("be_net_cf"), -be("net_cashflows"), rtol=0, atol=0)


def test_profit_chain_transfers_before_tax(ul_projection):
    model, _ = ul_projection()
    be = model["be"]
    params = model.params("be")
    pbt = be("profit_before_tax")
    transfer = pbt * params["profit_transfer_rate"]
    tax = (pbt - transfer) * params["Tax Rate"]
    np.testing.assert_allclose(be("profit_transfer"), transfer, rtol=1e-15)
    np.testing.assert_allclose(be("tax"), tax, rtol=1e-15)
    np.testing.assert_allclose(be("net_profit_before_sm"), pbt - transfer - tax, rtol=1e-12)
    interest = be("interest_on_solvency_capital")
    coc = be("increase_in_solvency_capital") - interest * (
        1 - params["Tax Rate"] - params["profit_transfer_rate"]
    )
    np.testing.assert_allclose(be("cost_of_capital"), coc, rtol=1e-12, atol=1e-9)
    np.testing.assert_allclose(
        be("net_profit_after_sm"), be("net_profit_before_sm") - be("cost_of_capital"), rtol=1e-12
    )
    for name in ("profit_before_tax", "tax", "net_profit_after_sm", "cost_of_capital"):
        assert not be(name)[:, 0].any(), name


@pytest.mark.parametrize("basis", ["be", "mc"])
def test_capital_factors_and_formula(ul_projection, basis):
    model, frame = ul_projection()
    data = model[basis]
    params = model.params(basis)
    guaranteed = frame["V_gmmb_on"].to_numpy()[:, None] == 1
    f1 = np.where(
        guaranteed,
        params["reserve_capital_factor_guarantee"],
        params["reserve_capital_factor_no_guarantee"],
    )
    f2 = np.where(
        guaranteed,
        params["sar_capital_factor_guarantee"],
        params["sar_capital_factor_no_guarantee"],
    )
    ratio = params["target_capital_ratio"]
    reserves = model["reserving"]("non_unit_reserve_pp") * (data("lives_end") + data("maturities"))
    in_term = data("policy_month") < frame["Policy_Term"].to_numpy()[:, None] * 12
    capital = np.maximum(
        f1 * (data("unit_reserve") + reserves) * ratio + f2 * data("sum_at_risk") * ratio * in_term,
        0,
    )
    capital[:, 0] = 0
    np.testing.assert_allclose(data("required_solvency_capital"), capital, rtol=1e-12, atol=1e-9)
    rate = model.scenario({"be": "roi", "mc": "reference_forward"}[basis])
    opening = np.zeros_like(capital)
    opening[:, 1:] = capital[:, :-1]
    np.testing.assert_allclose(
        data("interest_on_solvency_capital"), opening * rate, rtol=1e-12, atol=1e-9
    )


def test_guarantee_variant_uses_the_with_guarantee_factors(ul_projection):
    params = None
    for gmmb in (0, 1):
        model, _ = ul_projection(0, V_gmmb_on=gmmb)
        params = model.params("be")
        data = model["be"]
        factor = (
            params["reserve_capital_factor_guarantee"]
            if gmmb
            else params["reserve_capital_factor_no_guarantee"]
        )
        np.testing.assert_allclose(
            data("part1_sm")[1],
            factor
            * (data("unit_reserve")[1] + data("capital_reserves")[1])
            * params["target_capital_ratio"],
            rtol=1e-12,
        )
        assert data("reserve_capital_factor")[1] == factor
    assert params is not None
    assert (
        params["reserve_capital_factor_guarantee"] != params["reserve_capital_factor_no_guarantee"]
    )


def test_capital_is_zero_at_valuation_and_stops_after_maturity(ul_projection):
    model, frame = ul_projection()
    for basis in ("be", "mc"):
        data = model[basis]
        capital = data("required_solvency_capital")
        assert not capital[:, 0].any()
        assert (capital[:, 1] > 0).all()
        for row, pm in enumerate(frame["Duration_in_Months"]):
            after = frame["Policy_Term"][row] * 12 - pm
            assert not capital[row, after + 1 :].any()
            assert not data("part2_sm")[row, after:].any()


def test_demo_guarantee_variant_switches_the_guarantee_on():
    import polars as pl

    from pathlib import Path

    basis = Path(__file__).resolve().parents[2] / "examples/demo/basis"
    variants = pl.read_csv(basis / "ul_variants.csv")
    flags = dict(variants.filter(pl.col("field") == "gmmb_on").select("key", "value").iter_rows())
    assert flags[GUARANTEE_VARIANT] == 1
    assert {key for key, value in flags.items() if value == 1} == {GUARANTEE_VARIANT}
