"""Check deduction funding and policy-year-end additions."""

import numpy as np
import pytest
from test_unit_fund import monthly_charge

from avk.products.unit_linked.bindings import MAX_FUND_SLOTS
from avk.products.unit_linked.formulas import UnitLinked


@pytest.mark.parametrize("opening", [1e-14, 25.0])
def test_exhausted_fund_scales_every_deduction(ul_projection, opening):
    model, _ = ul_projection(
        0,
        Duration_in_Months=73,
        Fund_1_Value=opening,
        Sum_Assured=1e9,
        V_guarantee_charge=0.005,
        V_pw_start_year=1,
    )
    be = model["be"]
    requests = np.array([be(f"{name}_req")[1] for name in ("pw", "admin", "gc", "mc")])
    paid = np.array([be(f"{name}_pp")[1] for name in ("pw", "admin", "gc", "mc")])
    assert min(requests) > 0
    np.testing.assert_allclose(paid, requests * opening / requests.sum(), rtol=1e-12, atol=0)
    assert paid.sum() == pytest.approx(opening, rel=1e-12, abs=0)
    assert be("fund_after_charges_total")[1] == 0
    assert be("fund_close_total")[1] == 0


def test_admin_escalation_and_monthly_guarantee_charge(ul_projection):
    model, frame = ul_projection(
        0, Duration_in_Months=24, V_admin_escalation=0.03, V_guarantee_charge=0.005
    )
    be = model["be"]
    admin_scale = model.table(
        "ul_charge_scales/admin_charge_monthly", 3, frame["Variant_Id"].item()
    )
    assert be("admin_req")[1] == pytest.approx(admin_scale * 1.03**2)
    assert be("gc_req")[1] == pytest.approx(
        be("fund_after_premium_total")[1] * monthly_charge(0.005)
    )


@pytest.mark.parametrize("basis", [1, 2])
def test_classic_loyalty_anniversaries_and_basis(ul_projection, basis):
    model, frame = ul_projection(
        0, Duration_in_Months=107, V_loyalty_basis=basis, V_loyalty_requires_full_premiums=0
    )
    be = model["be"]
    assert be("loyalty_pp")[1] == 0
    for step, rate in ((13, 0.0025), (25, 0.003)):
        avg = (
            sum(be("fund_close_total")[step - 11 : step]) + be("fund_after_charges_total")[step]
        ) / 12
        assert be("average_fund")[step] == pytest.approx(avg)
        value = avg if basis == 1 else frame["Annualised_Premium"].item()
        assert be("loyalty_pp")[step] == pytest.approx(rate * value)
        assert be("loyalty_pp")[step + 1] == 0


def test_full_premium_loyalty_condition(ul_projection):
    model, _ = ul_projection(
        0, Duration_in_Months=119, Instalments_Paid=9, V_loyalty_requires_full_premiums=1
    )
    assert model["be"]("loyalty_pp")[1] == 0
    model, _ = ul_projection(
        0, Duration_in_Months=119, Instalments_Paid=10, V_loyalty_requires_full_premiums=1
    )
    assert model["be"]("loyalty_pp")[1] > 0


def test_booster_and_guaranteed_additions_allocated_pro_rata(ul_projection):
    model, frame = ul_projection(
        1, Duration_in_Months=118, V_loyalty_on=0, V_guaranteed_addition_rate=0.01
    )
    be = model["be"]
    assert be("booster_pp")[1] == be("guaranteed_addition_pp")[1] == 0
    assert be("booster_pp")[2] == pytest.approx(0.01 * be("average_fund")[2])
    assert be("guaranteed_addition_pp")[2] == pytest.approx(
        0.01 * frame["Annualised_Premium"].item()
    )
    for k in (1, 2):
        share = be(f"fund_{k}_after_charges")[2] / be("fund_after_charges_total")[2]
        assert be(f"fund_{k}_additions")[2] == pytest.approx(be("additions_pp")[2] * share)
    assert be("fund_3_additions")[2] == 0


def test_addition_uses_allocation_if_charges_exhaust_fund(ul_projection):
    model, _ = ul_projection(
        0,
        Duration_in_Months=119,
        Fund_1_Value=1.0,
        Sum_Assured=1e9,
        V_loyalty_on=0,
        V_guaranteed_addition_rate=0.01,
    )
    be = model["be"]
    assert be("fund_after_charges_total")[1] == 0
    assert be("fund_1_additions")[1] == be("guaranteed_addition_pp")[1] > 0


def test_anniversary_addition_has_no_credit_or_cost_without_a_destination(ul_projection):
    model, _ = ul_projection(
        0,
        Duration_in_Months=119,
        Premium_Payment_Term=5,
        Instalments_Paid=5,
        Instalments_Payable=5,
        Fund_1_Allocation=0.0,
        Fund_1_Value=1.0,
        Sum_Assured=1e9,
        V_guaranteed_addition_rate=0.01,
    )
    for basis in UnitLinked.BASES:
        data = model[basis]
        assert data("anniversary")[1] == data("A_begin")[1] == data("full_premiums")[1] == 1
        assert data("premium_income")[1] == data("allocation_total")[1] == 0
        assert data("fund_after_premium_total")[1] == 1
        assert data("fund_after_charges_total")[1] == 0
        assert data("additions_pp")[1] == data("addition_outgo")[1] == 0
        for i in range(1, MAX_FUND_SLOTS + 1):
            assert data(f"fund_{i}_additions")[1] == 0
        assert data("non_unit_benefit_outgo")[1] == pytest.approx(data("death_non_unit_A")[1])
