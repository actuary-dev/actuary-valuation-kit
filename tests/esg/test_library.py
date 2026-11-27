import numpy as np
import pytest

from avk.assumptions.context import ScenarioVariable
from avk.esg.supplied import SuppliedScenarios
from avk.model.data import ScenarioSet
from avk.runtime.errors import InputError


@pytest.fixture
def baseline():
    return ScenarioSet(
        {"roi": [[0.0, 0.0, 0.01, 0.02]], "ref": [[0.0, 0.015, 0.01, 0.015]]},
        ("deterministic",),
        np.ones(1),
        "deterministic",
        {"fixture": "curves"},
    )


def test_flat_sets_monthly_rate_only_on_placed_months(baseline):
    from avk.esg.library import flat

    active = {"roi": np.array([False, False, True, True])}
    modified = flat(baseline, ["roi"], 1.05**12 - 1, placement=active)
    np.testing.assert_allclose(modified.variables["roi"], [[0.0, 0.0, 0.05, 0.05]], atol=1e-15)
    np.testing.assert_array_equal(modified.variables["ref"], baseline.variables["ref"])
    np.testing.assert_array_equal(baseline.variables["roi"], [[0.0, 0.0, 0.01, 0.02]])
    assert modified.ids == baseline.ids
    assert modified.provenance == baseline.provenance


def test_shift_in_annual_rate_space_changes_true_zero_rate(baseline):
    from avk.esg.library import shift

    shifted = shift(baseline, ["roi"], 1.01**12 - 1)
    expected = [
        [0.0, 0.01, (2 * 1.01**12 - 1) ** (1 / 12) - 1, (1.02**12 + 1.01**12 - 1) ** (1 / 12) - 1]
    ]
    np.testing.assert_allclose(shifted.variables["roi"], expected, atol=1e-15, rtol=0)


def test_shock_compounds_with_the_flat_return(baseline):
    from avk.esg.library import flat, shock

    modified = shock(flat(baseline, ["roi"], 1.05**12 - 1), ["roi"], 2, 0.7)
    np.testing.assert_allclose(modified.variables["roi"], [[0.0, 0.05, -0.265, 0.05]], atol=1e-15)
    np.testing.assert_array_equal(modified.variables["ref"], baseline.variables["ref"])


def test_custom_replaces_months_by_key_including_zero(baseline, tmp_path):
    from avk.esg.library import custom

    path = tmp_path / "path.csv"
    path.write_text("Month,ref\n3,-0.01\n1,0.02\n0,0.01\n2,0.03\n", encoding="utf-8")
    modified = custom(baseline, path)
    np.testing.assert_array_equal(modified.variables["ref"], [[0.01, 0.02, 0.03, -0.01]])
    np.testing.assert_array_equal(modified.variables["roi"], baseline.variables["roi"])


def test_invalid_overlays(baseline):
    from avk.esg.library import flat, shift, shock

    with pytest.raises(InputError, match=r"Unknown scenario variables.*missing"):
        flat(baseline, ["missing"], 0.04)
    with pytest.raises(InputError, match="Annual_Change"):
        shift(baseline, ["roi"], -1.0)
    with pytest.raises(InputError, match="Month"):
        shock(baseline, ["roi"], 4, 0.7)
    with pytest.raises(InputError, match="Factor"):
        shock(baseline, ["roi"], 2, 0.0)


@pytest.mark.parametrize("months", ["0,0.01\n1,0.02\n3,0.04", "0,0\n1,0\n1,0\n3,0"])
def test_custom_requires_each_month_once(baseline, tmp_path, months):
    from avk.esg.library import custom

    path = tmp_path / "incomplete.csv"
    path.write_text(f"Month,roi\n{months}\n", encoding="utf-8")
    with pytest.raises(InputError, match="months 0 to 3"):
        custom(baseline, path)


def test_scenario_parquet_round_trips_exactly(tmp_path):
    from avk.esg.library import write_parquet

    values = np.array([[-0.0, 0.1, np.nextafter(0.1, 1)], [0.0, -0.25, 0.15]])
    paths = ScenarioSet(
        {"roi": values}, ("1", "10"), np.full(2, 0.5), "real_world", {}, (2**64 - 1, 2031)
    )
    path = tmp_path / "output" / "scenarios.parquet"
    assert write_parquet(paths, path) == path
    reader = SuppliedScenarios(
        path, [ScenarioVariable("roi", "curve", "roi", "lag")], {"Measure": "real_world"}
    )
    loaded = reader.generate({}, 3)
    assert loaded.ids == paths.ids
    assert loaded.seeds == paths.seeds
    assert loaded.measure == paths.measure
    np.testing.assert_array_equal(loaded.weights, paths.weights)
    np.testing.assert_array_equal(loaded.variables["roi"].view(np.uint64), values.view(np.uint64))


def test_scenario_parquet_round_trips_unequal_weights(tmp_path):
    from avk.esg.library import write_parquet

    paths = ScenarioSet(
        {"roi": [[0.0], [0.1]]}, ("1", "2"), np.array([0.25, 0.75]), "real_world", {}, (1, 2)
    )
    path = write_parquet(paths, tmp_path / "weighted.parquet")
    loaded = SuppliedScenarios(
        path, [ScenarioVariable("roi", "curve", "roi", "lag")], {"Measure": "real_world"}
    ).generate({}, 1)
    assert loaded.ids == paths.ids
    np.testing.assert_array_equal(loaded.weights, paths.weights)


@pytest.mark.parametrize(
    "weights",
    [
        [None, 0.75, 0.25, 0.75],
        [-0.25, 0.75, -0.25, 0.75],
        [float("inf"), 0.75, float("inf"), 0.75],
        [float("nan"), 0.75, float("nan"), 0.75],
        [0.25, 0.75, 0.20, 0.75],
        [0.25, 0.625, 0.25, 0.625],
    ],
)
def test_supplied_scenarios_reject_invalid_weights(tmp_path, weights):
    import polars as pl

    path = tmp_path / "weighted.parquet"
    pl.DataFrame(
        {
            "Scenario": [2, 10, 2, 10],
            "Month": [1, 0, 0, 1],
            "Seed": [4, 9, 4, 9],
            "Weight": weights,
            "roi": [0.1, 0.0, 0.0, 0.2],
        }
    ).write_parquet(path)
    reader = SuppliedScenarios(
        path, [ScenarioVariable("roi", "curve", "roi", "lag")], {"Measure": "real_world"}
    )
    with pytest.raises(InputError, match="Weight"):
        reader.generate({}, 2)
