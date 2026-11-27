"""The general fund reserve, its floors, the revival provision and the total reserve."""

import numpy as np
import pytest

from avk.products.unit_linked.formulas import UnitLinked

RATES = {"reserving": "vroi", "be": "roi", "mc": "reference_forward"}
ACTIVE, DPF, PAID_UP = 0, 3, 4


def discounted_sum(cashflows, rates):
    """End-of-month present values by summation with a forward product of discount factors."""
    policies, months = cashflows.shape
    factor = np.ones(months)
    for s in range(1, months):
        factor[s] = factor[s - 1] / (1 + rates[s])
    values = np.zeros((policies, months))
    for t in range(months):
        later = slice(t + 1, months)
        values[:, t] = (cashflows[:, later] * factor[later]).sum(axis=1) / factor[t]
    return values


def test_recursion_equals_discounted_summation(ul_projection, tmp_path, assert_parity):
    model, _ = ul_projection()
    actual, expected = {}, {}
    for basis in UnitLinked.BASES:
        data = model[basis]
        rates = model.scenario(RATES[basis])
        actual[basis] = data("gf_reserve_dcf")
        expected[basis] = discounted_sum(data("net_cashflows"), rates)
    assert_parity(tmp_path, actual, expected)


def test_held_reserve_never_below_zero_or_the_floor(ul_projection):
    model, _ = ul_projection()
    for basis in UnitLinked.BASES:
        data = model[basis]
        held, floor = data("gf_reserve_held"), data("gf_reserve_floor")
        assert (held >= 0).all() and (held >= floor).all() and (floor >= 0).all()
        np.testing.assert_array_equal(
            held, np.maximum(np.maximum(data("gf_reserve_dcf"), 0), floor)
        )


def test_floor_is_fifteen_days_of_annual_mortality_charge(ul_projection):
    model, _ = ul_projection()
    for basis in UnitLinked.BASES:
        data = model[basis]
        days = model.params(basis)["reserve_floor_days"]
        charge = data("mc_income")
        assert (charge[:, 1] > 0).any()
        np.testing.assert_allclose(
            data("gf_reserve_floor")[:, 0], days / 365 * 12 * charge[:, 1], rtol=1e-12, atol=0
        )
        np.testing.assert_allclose(
            data("gf_reserve_floor")[:, :-1], days / 365 * 12 * charge[:, 1:], rtol=1e-12
        )


def test_classic_dcf_is_negative_mid_term_so_a_floor_bites(ul_projection):
    model, frame = ul_projection(ACTIVE)
    assert frame["Duration_in_Months"][0] < frame["Policy_Term"][0] * 6
    data = model["reserving"]
    dcf, held = data("gf_reserve_dcf"), data("gf_reserve_held")
    assert dcf[0] < 0
    assert held[0] == max(0.0, data("gf_reserve_floor")[0]) > 0
    alive = data("lives_end") > 0
    bites = dcf < np.maximum(0.0, data("gf_reserve_floor"))
    assert bites[alive].mean() > 0.5


def test_revival_provision_on_dpf_and_paid_up_funds(ul_projection):
    model, _ = ul_projection()
    for basis in UnitLinked.BASES:
        data = model[basis]
        params = model.params(basis)
        expected = params["revival_strain_dpf"] * data("dpf_close") + params[
            "revival_strain_rpu"
        ] * data("rpu_close_total")
        np.testing.assert_allclose(data("revival_provision"), expected, rtol=1e-12, atol=0)
        assert data("revival_provision")[DPF, 0] > 0 and data("revival_provision")[PAID_UP, 0] > 0


def test_total_reserve_and_per_policy_reserves(ul_projection):
    model, _ = ul_projection()
    for basis in UnitLinked.BASES:
        data = model[basis]
        non_unit = data("gf_reserve_held") + data("revival_provision")
        np.testing.assert_array_equal(data("non_unit_reserve"), non_unit)
        np.testing.assert_array_equal(data("total_reserve"), data("unit_reserve") + non_unit)
        lives = np.maximum(data("lives_end") + data("maturities"), 1e-6)
        np.testing.assert_array_equal(data("reserve_lives"), lives)
        for name in ("gf_reserve", "non_unit_reserve", "total_reserve"):
            total = data("gf_reserve_held") if name == "gf_reserve" else data(name)
            np.testing.assert_allclose(data(f"{name}_pp"), total / lives, rtol=1e-15)


def test_sum_at_risk_on_lives_in_force(ul_projection):
    model, _ = ul_projection()
    data = model["be"]
    expected = data("A_end") * data("sar") + data("rpu_sar") * data("R_survival")
    np.testing.assert_allclose(data("sum_at_risk"), expected, rtol=1e-12, atol=0)
    assert (data("sum_at_risk") >= 0).all()
    assert data("sum_at_risk")[PAID_UP, 0] == pytest.approx(data("rpu_sar")[PAID_UP, 0])
    assert data("sum_at_risk")[ACTIVE, 0] == pytest.approx(data("sar")[ACTIVE, 0])
