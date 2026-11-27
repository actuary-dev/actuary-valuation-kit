"""General-fund expenses, commission, interest and the net cashflow."""

import numpy as np
import pytest

from avk.products.unit_linked.formulas import UnitLinked
from avk.runs.cases import Case, Shock

ACTIVE, DPF, PAID_UP, SINGLE = 0, 3, 4, 5


def test_initial_expense_only_in_policy_month_one(ul_projection):
    model, _ = ul_projection(ACTIVE, Duration_in_Months=0, Instalments_Paid=0)
    for basis in UnitLinked.BASES:
        data = model[basis]
        params = model.params(basis)
        margin = params["prudent_margin_expense"] if basis == "reserving" else 0.0
        expected = (
            params["initial_fixed_expense"]
            + params["initial_percent_premium_expense"] * data("premium_pp")[1]
            + params["initial_percent_sa_expense"] * 1e6
        ) * (1 + margin)
        initial = data("initial_expense")
        assert data("policy_month")[1] == 1 and data("premium_pp")[1] > 0
        assert initial[1] == pytest.approx(expected * data("A_begin")[1], rel=1e-12)
        assert not initial[0] and not initial[2:].any()


def test_in_force_policy_pays_no_initial_expense(ul_projection):
    model, _ = ul_projection(ACTIVE)
    assert not model["be"]("initial_expense").any()


@pytest.mark.parametrize("policy", [ACTIVE, DPF, PAID_UP])
def test_renewal_expense_on_every_state_from_year_two(ul_projection, policy):
    model, _ = ul_projection(policy)
    data = model["be"]
    params = model.params("be")
    lives = data("A_begin") + data("R_begin") + data("D_begin")
    months = np.arange(lives.size)
    inflation = (1 + params["Inflation"]) ** ((months - 1) / 12)
    live = data("live").astype(bool)
    expected = params["renewal_fixed_expense"] / 12 * inflation * lives * live
    expected *= data("policy_year") >= 2
    assert live[1] and lives[1] > 0
    np.testing.assert_allclose(data("renewal_expenses"), expected, rtol=1e-12, atol=1e-10)
    assert data("renewal_expenses")[0] == 0


def test_renewal_expense_starts_in_policy_year_two(ul_projection):
    model, _ = ul_projection(ACTIVE, Duration_in_Months=0, Instalments_Paid=0)
    renewal = model["be"]("renewal_expenses")
    assert not renewal[1:13].any()
    assert renewal[13] > 0


def test_expenses_shocked_and_inflated_like_term(ul_projection):
    case = Case(
        "shock",
        {"expense": Shock(120.0, 1.3), "inflation": Shock(0.01, 1.2)},
    )
    base, _ = ul_projection(ACTIVE)
    shocked, _ = ul_projection(ACTIVE, case=case)
    params = base.params("be")
    b, s = base["be"], shocked["be"]
    months = np.arange(b("A_begin").size)
    rate = (params["Inflation"] + 0.01) * 1.2
    inflation = (1 + rate) ** ((months - 1) / 12)
    live = s("live").astype(bool)
    lives = s("A_begin") + s("R_begin") + s("D_begin")
    expected = (params["renewal_fixed_expense"] + 120.0) * 1.3 / 12 * inflation * lives
    np.testing.assert_allclose(s("renewal_expenses")[live], expected[live], rtol=1e-12)
    np.testing.assert_allclose(s("fund_expenses"), 1.3 * b("fund_expenses"), rtol=1e-12)
    np.testing.assert_allclose(
        s("claim_expenses")[live],
        params["claim_expense"]
        * 1.3
        * inflation[live]
        * (s("deaths_A") + s("deaths_R") + s("deaths_D"))[live],
        rtol=1e-12,
    )


def test_reserving_loads_expenses_but_not_commission(ul_projection):
    model, _ = ul_projection(ACTIVE)
    margin = model.params("reserving")["prudent_margin_expense"]
    reserving, be = model["reserving"], model["be"]
    lives = reserving("A_begin") + reserving("R_begin") + reserving("D_begin")
    be_lives = be("A_begin") + be("R_begin") + be("D_begin")
    live = be("live").astype(bool) & (be("policy_year") >= 2)
    np.testing.assert_allclose(
        reserving("renewal_expenses")[live] / lives[live],
        be("renewal_expenses")[live] / be_lives[live] * (1 + margin),
        rtol=1e-12,
    )
    due = reserving("premium_income") > 0
    assert due.any()
    rate = model.table("commissions_ul", int(be("policy_year")[np.argmax(due)]), 0)
    np.testing.assert_allclose(
        reserving("commissions")[due] / reserving("premium_income")[due],
        np.full(due.sum(), rate),
        rtol=1e-12,
    )


def test_fund_expense_on_opening_unit_reserve(ul_projection):
    model, _ = ul_projection()
    for basis in UnitLinked.BASES:
        data = model[basis]
        rate = model.params(basis)["fund_expense_rate"]
        margin = model.params(basis)["prudent_margin_expense"] if basis == "reserving" else 0.0
        reserve = data("unit_reserve")
        expected = np.zeros_like(reserve)
        expected[:, 1:] = rate / 12 * reserve[:, :-1] * (1 + margin)
        np.testing.assert_allclose(data("fund_expenses"), expected, rtol=1e-12, atol=1e-10)


def test_charges_split_start_and_end_of_month(ul_projection):
    model, _ = ul_projection()
    for basis in UnitLinked.BASES:
        data = model[basis]
        np.testing.assert_allclose(
            data("charges_start") + data("charges_end"),
            data("charge_income"),
            rtol=1e-12,
            atol=1e-10,
        )
        np.testing.assert_allclose(
            data("charges_start"),
            data("pac_income") + data("admin_income") + data("mc_income") + data("gc_income"),
            rtol=1e-12,
            atol=1e-10,
        )
        assert not data("residual_additions").any()


@pytest.mark.parametrize("step", [1, 2, 12, 40])
def test_net_cashflow_equals_hand_formula(ul_projection, step):
    model, _ = ul_projection()
    for basis in UnitLinked.BASES:
        data = model[basis]
        rate = {"reserving": "vroi", "be": "roi", "mc": "reference_forward"}[basis]
        i = model.scenario(rate)[step]
        acquisition = data("commissions") + data("initial_expense")
        expense = data("renewal_expenses") + data("fund_expenses")
        start = data("pac_income") + data("admin_income") + data("mc_income") + data("gc_income")
        interest = (start - acquisition - expense) * i
        expected = -(
            data("charge_income")
            - acquisition
            - expense
            - data("claim_expenses")
            - data("non_unit_benefit_outgo")
            + interest
        )
        np.testing.assert_allclose(
            data("net_cashflows")[:, step], expected[:, step], rtol=1e-12, atol=1e-8
        )
        np.testing.assert_allclose(data("acquisition_cost"), acquisition, rtol=1e-12, atol=1e-10)
        np.testing.assert_allclose(data("expense_outgo"), expense, rtol=1e-12, atol=1e-10)


def test_no_cashflow_at_the_valuation_instant(ul_projection):
    model, _ = ul_projection(ACTIVE, Duration_in_Months=1)
    for basis in UnitLinked.BASES:
        data = model[basis]
        for name in (
            "net_cashflows",
            "initial_expense",
            "renewal_expenses",
            "fund_expenses",
            "claim_expenses",
            "commissions",
            "interest_on_cashflows",
        ):
            assert data(name)[0] == 0, name


def test_claim_expense_on_deaths_of_every_state(ul_projection):
    model, _ = ul_projection()
    data = model["be"]
    params = model.params("be")
    months = np.arange(data("A_begin").shape[1])
    inflation = (1 + params["Inflation"]) ** ((months - 1) / 12)
    deaths = data("deaths_A") + data("deaths_R") + data("deaths_D")
    expected = params["claim_expense"] * inflation * deaths
    expected[:, 0] = 0
    np.testing.assert_allclose(data("claim_expenses"), expected, rtol=1e-12, atol=1e-10)
    assert data("deaths_D")[DPF, 1] > 0 and data("deaths_R")[PAID_UP, 1] > 0
