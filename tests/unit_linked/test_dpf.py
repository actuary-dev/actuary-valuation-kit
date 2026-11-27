"""DPF flows, guarantee and discontinuance charge controls."""

import numpy as np
import pytest
from test_unit_fund import monthly_charge, monthly_return

from avk.products.unit_linked.bindings import SCENARIO_ASSETS
from avk.products.unit_linked.formulas import UnitLinked


@pytest.mark.parametrize(
    ("premium", "fund", "expected"),
    [
        (40_000, 500_000, 3000),
        (60_000, 500_000, 3600),
        (200_000, 500_000, 6000),
        (200_000, 1500, None),
    ],
)
def test_classic_discontinuance_charge_limits(ul_projection, premium, fund, expected):
    model, _ = ul_projection(0, Duration_in_Months=1, Annualised_Premium=premium, Fund_1_Value=fund)
    be = model["be"]
    limit = be("fund_close_total")[1] if expected is None else expected
    assert limit > 0
    assert be("disc_charge_pp")[1] == pytest.approx(limit)
    assert be("disc_charge_income")[1] == pytest.approx(be("to_dpf")[1] * limit)
    assert be("dpf_inflow")[1] == pytest.approx(
        be("to_dpf")[1] * (be("fund_close_total")[1] - limit)
    )
    assert be("dpf_fmc")[1] == 0


@pytest.mark.parametrize("market", [-0.01, 0.02])
def test_dpf_guarantee_credits_deficit_and_keeps_excess(ul_projection, market, projection_inputs):
    report, _ = projection_inputs
    scenarios = {
        name: np.full_like(report.scenarios.variables[name], market) for name in SCENARIO_ASSETS
    }
    model, frame = ul_projection(3, Duration_in_Months=50, scenario_overrides=scenarios)
    row = frame.row(0, named=True)
    be = model["be"]
    guaranteed = monthly_return(row["R_dpf_min_rate"])
    actual = market + monthly_return(row["DPF_Alpha"])
    assert be("dpf_close")[0] == row["DPF_Value"]
    assert be("dpf_fmc")[0] == be("dpf_guarantee_cost")[0] == 0
    for step in range(1, 11):
        opening = be("dpf_close")[step - 1]
        grown = opening * (1 + max(actual, guaranteed))
        deduction = grown * monthly_charge(row["DPF_FMC"])
        assert be("dpf_open")[step] == opening
        assert be("dpf_grown")[step] == pytest.approx(grown)
        assert be("dpf_grown")[step] / opening >= 1 + guaranteed - 1e-12
        assert be("dpf_fmc")[step] == pytest.approx(deduction)
        assert be("dpf_guarantee_cost")[step] == pytest.approx(
            opening * max(guaranteed - actual, 0)
        )
    assert not be("dpf_lockin_paid")[:10].any()
    assert be("dpf_lockin_paid")[10] == pytest.approx(
        be("dpf_after")[10] - be("dpf_death_paid")[10]
    )
    assert not be("dpf_close")[10:].any()


def test_last_lock_in_month_entrant_is_paid_immediately(ul_projection):
    model, _ = ul_projection(0, Duration_in_Months=59)
    be = model["be"]
    assert be("dpf_lockin_paid")[1] == be("dpf_inflow")[1] > 0
    assert be("lockin_exits_D")[1] == be("to_dpf")[1] > 0
    assert be("D_end")[1] == be("dpf_close")[1] == 0


def test_overdue_dpf_at_valuation_is_paid_in_first_projection_month(ul_projection):
    model, _ = ul_projection(3, Duration_in_Months=74)
    be = model["be"]
    assert be("D_end")[0] == 1
    assert be("dpf_close")[0] > 0
    assert be("lockin_exits_D")[0] == be("dpf_lockin_paid")[0] == 0
    assert be("dpf_lockin_paid")[1] > 0
    assert be("lockin_exits_D")[1] == pytest.approx(1 - be("deaths_D")[1])
    assert be("D_end")[1] == be("dpf_close")[1] == 0


def test_dpf_is_released_in_final_term_month_when_lock_in_outlasts_term(ul_projection):
    model, _ = ul_projection(3, Duration_in_Months=58, Policy_Term=5, V_lock_in_months=72)
    for basis in UnitLinked.BASES:
        data = model[basis]
        assert not data("dpf_lockin_paid")[:2].any()
        surviving_fund = data("dpf_after")[2] - data("dpf_death_paid")[2]
        assert surviving_fund > 0
        assert data("dpf_lockin_paid")[2] == surviving_fund, basis
        assert data("lockin_exits_D")[2] == data("D_begin")[2] - data("deaths_D")[2]
        np.testing.assert_array_equal(data("dpf_close")[2:], 0)
        np.testing.assert_array_equal(data("D_end")[2:], 0)


def test_dpf_disabled_still_charges_for_paid_discontinuance_within_lock_in(ul_projection):
    model, _ = ul_projection(0, Duration_in_Months=1, V_dpf_enabled=0)
    be = model["be"]
    assert be("paid_out_A")[1] > 0
    assert be("dpf_inflow")[1] == 0
    assert be("disc_charge_income")[1] == pytest.approx(
        be("paid_out_A")[1] * be("disc_charge_pp")[1]
    )
