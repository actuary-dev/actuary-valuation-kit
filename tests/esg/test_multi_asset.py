import hashlib
import json

import numpy as np
import pytest

from avk.assumptions.context import ScenarioVariable
from avk.assumptions.models import InterestCurveAssumption
from avk.esg.deterministic import DeterministicCurveESG
from avk.inputs.formats import key_axis
from avk.model.data import Table
from avk.runtime.errors import InputError

HORIZON = 120
VARIABLES = (
    ScenarioVariable("equity", "curve", "equity", "lag", 1),
    ScenarioVariable("bonds", "curve", "bonds", "lag", 1),
    ScenarioVariable("rf", "curve", "rf", "lag", 1),
)


@pytest.fixture
def curves():
    table = Table(
        "curve",
        (key_axis("year", tuple(range(10))), key_axis("field", ("equity", "bonds", "rf"))),
        np.tile([0.08, 0.0, 0.03], (10, 1)),
        {"sha256": "synthetic"},
    )
    return {
        "curve": InterestCurveAssumption(
            table=table,
            kind="annual_curve",
            valuation_month=7,
            units="annual_effective",
            fractional_age="not_applicable",
            below="error",
            above="error",
            unknown="error",
        )
    }


@pytest.fixture
def settings(tmp_path):
    (tmp_path / "assets.csv").write_text(
        "variable,volatility\nequity,0.2\nbonds,0.1\n", encoding="utf-8"
    )
    (tmp_path / "corr.csv").write_text(
        "risk,other,value\nbonds,equity,0.6\nequity,equity,1\nbonds,bonds,1\nequity,bonds,0.6\n",
        encoding="utf-8",
    )
    return {
        "Scenarios": 10,
        "Seed": 503,
        "Measure": "real_world",
        "Assets": "assets.csv",
        "Correlations": "corr.csv",
    }


@pytest.fixture
def generate(tmp_path, settings, curves):
    def make(*, variables=VARIABLES, **options):
        from avk.esg.multi_asset import MultiAssetLognormalESG

        generator = MultiAssetLognormalESG(variables, settings | options, base=tmp_path)
        return generator.generate(curves, HORIZON)

    return make


def test_output_metadata_and_deterministic_variables(generate, curves, tmp_path, settings):
    simulated = generate()
    baseline = DeterministicCurveESG(VARIABLES).generate(curves, HORIZON)
    assert simulated.ids == tuple(str(n) for n in range(1, 11))
    np.testing.assert_array_equal(simulated.weights, np.full(10, 0.1))
    assert len(set(simulated.seeds)) == 10
    assert simulated.measure == "real_world"
    assert simulated.provenance["generator"] == "MultiAssetLognormalESG"
    assert simulated.provenance["version"] == "1"
    assert json.loads(simulated.provenance["settings"])["Seed"] == settings["Seed"]
    for name in ("Assets", "Correlations"):
        digest = hashlib.sha256((tmp_path / settings[name]).read_bytes()).hexdigest()
        assert simulated.provenance[f"{name}.sha256"] == digest
    for values in simulated.variables.values():
        assert values.shape == (10, HORIZON)
        assert values.dtype == np.float64
    np.testing.assert_array_equal(
        simulated.variables["rf"], np.repeat(baseline.variables["rf"], 10, axis=0)
    )


def test_zero_volatility_reproduces_real_world_curves(generate, curves, tmp_path):
    (tmp_path / "assets.csv").write_text(
        "variable,volatility\nequity,0\nbonds,0\n", encoding="utf-8"
    )
    simulated = generate()
    baseline = DeterministicCurveESG(VARIABLES).generate(curves, HORIZON)
    for name, values in baseline.variables.items():
        np.testing.assert_allclose(
            simulated.variables[name], np.repeat(values, 10, axis=0), atol=1e-15, rtol=0
        )


@pytest.mark.parametrize("antithetic", [False, True])
def test_seeding_is_reproducible_and_prefix_stable(generate, antithetic):
    first = generate(Antithetic=antithetic)
    larger = generate(Scenarios=200, Antithetic=antithetic)
    again = generate(Antithetic=antithetic)
    other = generate(Seed=123, Antithetic=antithetic)
    for name, values in first.variables.items():
        np.testing.assert_array_equal(values, larger.variables[name][:10])
        np.testing.assert_array_equal(values, again.variables[name])
    assert first.seeds == larger.seeds[:10] == again.seeds
    assert not np.array_equal(first.variables["equity"], other.variables["equity"])


def test_real_world_monthly_means_and_correlation(generate):
    simulated = generate(Scenarios=20_000)
    equity = 1 + simulated.variables["equity"][:, 1:]
    bonds = 1 + simulated.variables["bonds"][:, 1:]
    for gross, annual, sigma in [(equity, 0.08, 0.2), (bonds, 0.0, 0.1)]:
        expected = (1 + annual) ** (1 / 12)
        standard_error = expected * np.sqrt(np.expm1(sigma**2 / 12) / len(gross))
        assert np.all(np.abs(gross.mean(axis=0) - expected) < 4 * standard_error)
    assert abs(np.corrcoef(np.log(equity[:, 0]), np.log(bonds[:, 0]))[0, 1] - 0.6) < 0.02


def test_risk_neutral_discounted_asset_indices(generate):
    simulated = generate(Scenarios=20_000, Measure="risk_neutral", Risk_Free="rf")
    assert simulated.measure == "risk_neutral"
    discount_base = np.prod(1 + simulated.variables["rf"], axis=1)
    for name, sigma in [("equity", 0.2), ("bonds", 0.1)]:
        discounted = np.prod(1 + simulated.variables[name], axis=1) / discount_base
        standard_error = np.sqrt(np.expm1((HORIZON - 1) * sigma**2 / 12) / len(discounted))
        assert abs(discounted.mean() - 1) < 4 * standard_error


def test_antithetic_pairs_use_opposite_shocks(generate):
    simulated = generate(Antithetic=True)
    expected_product = (1.08 ** (1 / 12)) ** 2 * np.exp(-(0.2**2) / 12)
    gross = 1 + simulated.variables["equity"][:, 1:]
    np.testing.assert_allclose(gross[::2] * gross[1::2], expected_product, rtol=1e-15, atol=0)
    assert simulated.seeds[::2] == simulated.seeds[1::2]
    with pytest.raises(InputError, match=r"Scenarios.*even.*Antithetic"):
        generate(Antithetic=True, Scenarios=3)


def test_timing_zeros_and_zero_rates_are_distinct(generate):
    variables = (
        ScenarioVariable("equity", "curve", "equity", "fiscal_lead", fiscal_start_month=4),
        ScenarioVariable("bonds", "curve", "bonds", "lag", 2),
        VARIABLES[2],
    )
    paths = generate(variables=variables).variables
    assert np.all(paths["equity"][:, [0, -3, -2, -1]] == 0)
    assert np.all(paths["bonds"][:, :2] == 0)
    assert np.any(paths["bonds"][:, 2:] != 0)


def test_singular_correlations_are_supported(generate, tmp_path):
    (tmp_path / "corr.csv").write_text(
        "risk,other,value\nbonds,equity,1\nequity,equity,1\nbonds,bonds,1\nequity,bonds,1\n",
        encoding="utf-8",
    )
    paths = generate().variables
    equity = (np.log1p(paths["equity"][:, 1:]) - np.log(1.08) / 12 + 0.2**2 / 24) / 0.2
    bonds = (np.log1p(paths["bonds"][:, 1:]) + 0.1**2 / 24) / 0.1
    np.testing.assert_allclose(equity, bonds, atol=1e-15, rtol=0)
