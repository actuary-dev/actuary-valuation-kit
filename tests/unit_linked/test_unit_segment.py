"""Reconcile the unit segment on every basis and verify fund return sources."""

from dataclasses import replace

import numpy as np
import polars as pl
import pytest

from avk.assumptions.lowering import lower
from avk.demo.generate import generate
from avk.model.executor import OutputRequest, project
from avk.products.unit_linked.bindings import MAX_FUND_SLOTS
from avk.products.unit_linked.formulas import UnitLinked
from avk.runs.cases import case_parameters
from avk.runs.check import check
from avk.runs.compile import product_kernel
from avk.testing.parity import compare

SLOTS = range(1, MAX_FUND_SLOTS + 1)
ROLL_COLUMNS = (
    "A_begin",
    "additions_pp",
    "allocated_pp",
    "disc_charge_income",
    "dpf_credited_return",
    "dpf_fmc",
    "lives_end",
    "rpu_deduction_total",
    "rpu_fmc_total",
    "unit_exit_benefits",
    "unit_reserve",
    *(f"{item}_pp" for item in ("admin", "mc", "gc", "pw")),
    *(
        pattern.format(i=i)
        for i in SLOTS
        for pattern in (
            "fund_{i}_after_charges",
            "fund_{i}_additions",
            "fund_{i}_growth_rate",
            "fund_{i}_fmc",
            "rpu_{i}_after_charges",
        )
    ),
)


def unit_roll(data):
    active = data("A_begin")
    allocate = data("allocated_pp") * active
    from_active = active * sum(data(f"{item}_pp") for item in ("admin", "mc", "gc"))
    from_rpu = data("rpu_deduction_total")
    fmc = (
        sum(data(f"fund_{i}_fmc") for i in SLOTS) * active + data("rpu_fmc_total") + data("dpf_fmc")
    )
    active_growth = active * sum(
        (data(f"fund_{i}_after_charges") + data(f"fund_{i}_additions"))
        * data(f"fund_{i}_growth_rate")
        for i in SLOTS
    )
    paid_up_growth = sum(
        data(f"rpu_{i}_after_charges") * data(f"fund_{i}_growth_rate") for i in SLOTS
    )
    net_movement = (
        allocate
        - from_active
        - from_rpu
        - data("pw_pp") * active
        + active_growth
        + paid_up_growth
        - fmc
        + data("additions_pp") * active
        - data("unit_exit_benefits")
        - data("disc_charge_income")
        + data("dpf_credited_return")
    )
    unit_charges = from_active + from_rpu + fmc + data("disc_charge_income")
    return net_movement, unit_charges


def opening_units(frame):
    return frame["DPF_Value"].to_numpy() + sum(frame[f"Fund_{i}_Value"].to_numpy() for i in SLOTS)


def test_unit_segment_reconciles_every_policy_and_month(ul_projection, tmp_path):
    model, frame = ul_projection()
    expected, actual = {}, {}
    for basis in UnitLinked.BASES:
        data = model[basis]
        net_movement, unit_charges = unit_roll(data)
        np.testing.assert_allclose(
            data("charge_income"),
            data("premium_income") - data("allocated_pp") * data("A_begin") + unit_charges,
            rtol=1e-12,
            atol=1e-10,
        )
        opening = opening_units(frame)
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


@pytest.mark.slow
def test_10k_demo_funds_and_lives_end_at_maturity_and_reconcile(tmp_path):
    path = generate(tmp_path / "book", "UNIT_LINKED", 10_000, 209)
    report = check(path)
    assert report.points is not None and report.scenarios is not None
    frame = report.points.frame
    assert frame.height == 10_000
    kernel = product_kernel(UnitLinked)
    months = next(iter(report.scenarios.variables.values())).shape[1]
    inputs = lower(
        report.contexts, report.points, report.scenarios, kernel, case_parameters(None, months)
    )
    labels = {
        basis: {
            name: f"{name}@{basis}" if f"{name}@{basis}" in kernel.columns else name
            for name in ROLL_COLUMNS
        }
        for basis in UnitLinked.BASES
    }
    grids = tuple(dict.fromkeys(label for fields in labels.values() for label in fields.values()))
    maturity = frame["Policy_Term"].to_numpy() * 12 - frame["Duration_in_Months"].to_numpy()
    assert (maturity == 0).any() and maturity.max() < months
    maturity = np.maximum(maturity, 1)
    opening = opening_units(frame)
    steps = np.arange(months)
    candidate, expected = tmp_path / "unit_close.parquet", tmp_path / "unit_roll.parquet"

    def check_batch(batch):
        columns = dict(zip(batch.columns, batch.grids[0], strict=True))
        rows = slice(batch.start, batch.stop)
        settled = steps >= maturity[rows, None]
        keys = {
            "Policy_Number": np.repeat(frame["Policy_Number"].to_numpy()[rows], months - 1),
            "Projection_Step": np.tile(steps[1:], batch.stop - batch.start),
        }
        actual_values, expected_values = {}, {}
        for basis, fields in labels.items():
            data = {name: columns[label] for name, label in fields.items()}.__getitem__
            reserve = data("unit_reserve")
            net_movement, _ = unit_roll(data)
            assert np.isfinite(reserve).all() and np.isfinite(net_movement).all()
            np.testing.assert_array_equal(reserve[:, 0], opening[rows])
            np.testing.assert_array_equal(net_movement[:, 0], 0)
            context = f"{basis}, policy rows {batch.start}:{batch.stop}"
            np.testing.assert_array_equal(reserve[settled], 0, err_msg=context)
            np.testing.assert_array_equal(data("lives_end")[settled], 0, err_msg=context)
            actual_values[basis] = reserve[:, 1:].ravel()
            expected_values[basis] = (reserve[:, :-1] + net_movement[:, 1:]).ravel()
        pl.DataFrame({**keys, **actual_values}).write_parquet(candidate)
        pl.DataFrame({**keys, **expected_values}).write_parquet(expected)
        compare(
            candidate,
            expected,
            classes={
                "Policy_Number": "identifier",
                "Projection_Step": "identifier",
                **dict.fromkeys(UnitLinked.BASES, "value"),
            },
        ).assert_ok()

    project(kernel, inputs, OutputRequest(grids=grids, batch_size=1024), on_batch=check_batch)


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
