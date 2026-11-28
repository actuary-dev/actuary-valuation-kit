import json
from dataclasses import replace

import numpy as np
import polars as pl
import pytest

from avk.api import load_run_config
from avk.assumptions.lowering import lower
from avk.demo.generate import generate
from avk.model.data import ModelPoints
from avk.model.executor import OutputRequest, project
from avk.runs.cases import case_parameters
from avk.runtime.errors import ConfigError

OFF = {"Enabled": False, "Slope": 2, "Floor": 0.5, "Cap": 1.5}
ON = {**OFF, "Enabled": True}
SETTINGS = {"reserving": OFF, "be": ON, "mc": OFF}


def _config(path, settings):
    config = json.loads(path.read_text(encoding="utf-8"))
    config["Dynamic_Lapse"] = settings
    path.write_text(json.dumps(config), encoding="utf-8")


@pytest.mark.parametrize(
    "settings",
    [
        {"be": ON},
        {**SETTINGS, "be": {**ON, "Enabled": 1}},
        {**SETTINGS, "be": {**ON, "Slope": -1}},
        {**SETTINGS, "be": {**ON, "Floor": 2}},
        {**SETTINGS, "be": {**ON, "Cap": float("inf")}},
    ],
)
def test_dynamic_lapse_requires_valid_settings_on_all_bases(tmp_path, settings):
    path = generate(tmp_path, "UNIT_LINKED", 6, 209)
    _config(path, settings)
    with pytest.raises(ConfigError, match="Dynamic_Lapse"):
        load_run_config(path)


def test_dynamic_lapse_requires_unit_linked_valuation(tmp_path):
    path = generate(tmp_path, "TERM", 6, 209)
    _config(path, SETTINGS)
    with pytest.raises(ConfigError, match="Dynamic_Lapse requires UNIT_LINKED"):
        load_run_config(path)


@pytest.fixture
def lapse_projection(tmp_path, projection_inputs):
    path = generate(tmp_path, "UNIT_LINKED", 6, 209)
    report, kernel = projection_inputs
    assert report.points is not None and report.scenarios is not None
    columns = (
        "fund_open_total",
        "rpu_open_total",
        "rpu_tpp_open",
        "w_surrender",
        "w_surrender_full",
        "w_cessation",
        "surrenders_A",
        "surrenders_R",
    )

    def calculate(policy, *, settings=None, changes=None, shocked=False):
        parameters = case_parameters(None, report.config.projection_term * 12)
        if settings is not None:
            _config(path, settings)
            config = load_run_config(path)
            parameters = case_parameters(
                None, config.projection_term * 12, dynamic_lapse=config.dynamic_lapse
            )
        frame = report.points.frame.slice(policy, 1)
        if changes is not None:
            frame = frame.with_columns(pl.lit(value).alias(name) for name, value in changes.items())
        points = ModelPoints(frame, report.points.fields)
        scenarios = report.scenarios
        if shocked:
            variables = {
                name: np.repeat(values, 2, axis=0) for name, values in scenarios.variables.items()
            }
            variables["ret_eq_large"][:, 1] = [-0.6, 0.6]
            scenarios = replace(
                scenarios,
                variables=variables,
                ids=("1", "2"),
                weights=np.full(2, 0.5),
                measure="real_world",
            )
        inputs = lower(report.contexts, points, scenarios, kernel, parameters)
        projection = project(
            kernel,
            inputs,
            OutputRequest(
                grids=tuple(f"{name}@{b}" for b in ("reserving", "be", "mc") for name in columns)
            ),
        )
        return {name: projection.grids[:, i, 0] for i, name in enumerate(projection.grid_columns)}

    return calculate


@pytest.mark.parametrize(
    ("fund", "paid", "multiplier"),
    [
        (400000.0, 600000.0, 0.5),
        (660000.0, 600000.0, 1.2),
        (900000.0, 600000.0, 1.5),
        (660000.0, 0.0, 1.0),
    ],
)
def test_active_surrender_uses_opening_moneyness(lapse_projection, fund, paid, multiplier):
    changes = {"Fund_1_Value": fund, "Premiums_Paid_To_Date": paid}
    base = lapse_projection(0, changes=changes)
    on = lapse_projection(0, settings=SETTINGS, changes=changes)
    original = base["w_surrender@be"][0, 1]
    assert original > 0
    assert on["fund_open_total@be"][0, 1] == fund
    assert on["w_surrender@be"][0, 1] == pytest.approx(original * multiplier, rel=1e-13)
    for basis in ("reserving", "mc"):
        for name in ("w_surrender", "surrenders_A"):
            np.testing.assert_array_equal(on[f"{name}@{basis}"], base[f"{name}@{basis}"])
    np.testing.assert_array_equal(on["w_cessation@be"], base["w_cessation@be"])


def test_paid_up_surrender_uses_aggregate_opening_moneyness(lapse_projection):
    base = lapse_projection(4)
    on = lapse_projection(4, settings=SETTINGS)
    fund = base["rpu_open_total@be"][0, 1]
    paid = base["rpu_tpp_open@be"][0, 1]
    original = base["w_surrender_full@be"][0, 1]
    multiplier = np.clip(1 + 2 * (fund / paid - 1), 0.5, 1.5)
    assert original > 0 and multiplier != 1
    assert on["w_surrender_full@be"][0, 1] == pytest.approx(original * multiplier, rel=1e-13)
    assert on["surrenders_R@be"][0, 1] == pytest.approx(
        base["surrenders_R@be"][0, 1] * multiplier, rel=1e-13
    )


def test_dynamic_surrender_responds_to_path_after_the_opening_month(lapse_projection):
    changes = {"Fund_1_Value": 600000.0}
    settings = {**SETTINGS, "be": {**ON, "Floor": 0.1, "Cap": 4}}
    off = lapse_projection(0, changes=changes, shocked=True)
    on = lapse_projection(0, settings=settings, changes=changes, shocked=True)
    a, b = on["w_surrender@be"]
    assert a[1] == b[1]
    assert a[2] < off["w_surrender@be"][0, 2] < b[2]


def test_dynamic_surrender_probability_caps_at_one(lapse_projection):
    settings = {**SETTINGS, "be": {**ON, "Floor": 1.0, "Cap": 10000.0}}
    on = lapse_projection(0, settings=settings, changes={"Fund_1_Value": 1e12})
    assert on["w_surrender@be"][0, 0] == 0
    assert on["w_surrender@be"][0, 1] == 1
