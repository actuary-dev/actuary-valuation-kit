"""Reconcile the entire unit segment on every basis for the valid six-policy book."""

from dataclasses import replace

import numpy as np
import polars as pl
import pytest

from avk.products.unit_linked.bindings import MAX_FUND_SLOTS
from avk.products.unit_linked.formulas import UnitLinked
from avk.testing.parity import compare


def test_unit_segment_reconciles_every_policy_and_month(ul_projection, tmp_path):
    model, frame = ul_projection()
    k = range(1, MAX_FUND_SLOTS + 1)
    expected, actual = {}, {}
    for basis in UnitLinked.BASES:
        data = model[basis]
        allocate = data("allocated_pp") * data("A_begin")
        from_active = data("A_begin") * sum(data(f"{item}_pp") for item in ("admin", "mc", "gc"))
        from_rpu = data("rpu_deduction_total")
        withdrawals = data("pw_pp") * data("A_begin")
        additions = data("additions_pp") * data("A_begin")
        fmc = (
            sum(data(f"fund_{i}_fmc") for i in k) * data("A_begin")
            + data("rpu_fmc_total")
            + data("dpf_fmc")
        )
        active_growth = data("A_begin") * sum(
            (data(f"fund_{i}_after_charges") + data(f"fund_{i}_additions"))
            * data(f"fund_{i}_growth_rate")
            for i in k
        )
        paid_up_growth = sum(
            data(f"rpu_{i}_after_charges") * data(f"fund_{i}_growth_rate") for i in k
        )
        net_movement = (
            allocate
            - from_active
            - from_rpu
            - withdrawals
            + active_growth
            + paid_up_growth
            - fmc
            + additions
            - data("unit_exit_benefits")
            - data("disc_charge_income")
            + data("dpf_credited_return")
        )
        np.testing.assert_allclose(
            data("charge_income"),
            data("premium_income")
            - allocate
            + from_active
            + from_rpu
            + fmc
            + data("disc_charge_income"),
            rtol=1e-12,
            atol=1e-10,
        )
        opening = frame["DPF_Value"].to_numpy() + sum(
            frame[f"Fund_{i}_Value"].to_numpy() for i in k
        )
        reserve = data("unit_reserve")
        assert np.isfinite(reserve).all() and np.isfinite(net_movement).all()
        np.testing.assert_array_equal(reserve[:, 0], opening)
        np.testing.assert_array_equal(net_movement[:, 0], 0)
        assert not data("premium_income")[:, 0].any()
        assert not data("non_unit_benefit_outgo")[:, 0].any()
        for row, pm in enumerate(frame["Duration_in_Months"]):
            assert not reserve[row, frame["Policy_Term"][row] * 12 - pm :].any()
        expected[basis] = (reserve[:, :-1] + net_movement[:, 1:]).ravel()
        actual[basis] = reserve[:, 1:].ravel()
    candidate, golden = tmp_path / "unit_close.parquet", tmp_path / "unit_roll.parquet"
    pl.DataFrame(actual).write_parquet(candidate)
    pl.DataFrame(expected).write_parquet(golden)
    compare(candidate, golden, classes=dict.fromkeys(UnitLinked.BASES, "value")).assert_ok()


def test_mc_reference_forward_is_used_for_all_fund_slots(ul_projection):
    model, _ = ul_projection(2)
    data = model["mc"]
    assert model.params("mc")["mc_fund_return_source"] == 0
    for k in range(1, MAX_FUND_SLOTS + 1):
        np.testing.assert_array_equal(
            data(f"fund_{k}_growth_rate"), model.scenario("reference_forward") * data("live")
        )
        assert data(f"fund_{k}_grown")[1] == pytest.approx(
            (data(f"fund_{k}_after_charges")[1] + data(f"fund_{k}_additions")[1])
            * (1 + model.scenario("reference_forward")[1])
        )


def test_supplied_paths_shocked_by_asset_class(ul_projection, projection_inputs):
    report, _ = projection_inputs
    scenarios = replace(
        report.scenarios,
        variables={
            name: np.stack((values[0], values[0] - (0.02 if name == "ret_eq_large" else 0)))
            for name, values in report.scenarios.variables.items()
        },
        ids=("base", "equity_shock"),
        weights=np.array([0.5, 0.5]),
    )
    model, _ = ul_projection(0, scenarios=scenarios)
    assert model["be"]("fund_close_total").shape[0] == 2
    assert model["be"]("fund_close_total")[0, 1] > model["be"]("fund_close_total")[1, 1]
    np.testing.assert_array_equal(
        model["mc"]("fund_close_total")[0], model["mc"]("fund_close_total")[1]
    )


def test_mc_asset_path_switch_uses_be_growth_rates(ul_projection):
    model, _ = ul_projection(2, mc_params={"mc_fund_return_source": 1})
    for i in range(1, MAX_FUND_SLOTS + 1):
        np.testing.assert_array_equal(
            model["mc"](f"fund_{i}_growth_rate"), model["be"](f"fund_{i}_growth_rate")
        )
