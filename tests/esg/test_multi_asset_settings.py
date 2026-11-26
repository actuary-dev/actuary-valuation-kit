from pathlib import Path

import numpy as np
import pytest

from avk.assumptions.context import ScenarioVariable
from avk.runtime.errors import InputError

VARIABLES = tuple(ScenarioVariable(name, "curve", name, "lag", 1) for name in ("z", "a", "rf"))


@pytest.fixture
def settings(tmp_path):
    (tmp_path / "assets.csv").write_text("variable,volatility\nz,0.25\na,0.1\n", encoding="utf-8")
    (tmp_path / "corr.csv").write_text(
        "risk,other,value\na,a,1\nz,z,1\na,z,0.4\nz,a,0.4\n", encoding="utf-8"
    )
    return {
        "Scenarios": 8,
        "Seed": 0,
        "Measure": "real_world",
        "Assets": "assets.csv",
        "Correlations": "corr.csv",
    }


def parse(settings, base: Path):
    from avk.esg.multi_asset import MultiAssetSettings

    return MultiAssetSettings.parse(settings, VARIABLES, base)


def test_valid_settings(settings, tmp_path):
    parsed = parse(settings, tmp_path)
    assert (parsed.scenarios, parsed.seed, parsed.measure) == (8, 0, "real_world")
    assert [(asset.variable, asset.volatility) for asset in parsed.assets] == [
        ("z", 0.25),
        ("a", 0.1),
    ]
    np.testing.assert_array_equal(parsed.correlation, [[1.0, 0.4], [0.4, 1.0]])
    assert parsed.risk_free is None
    assert parsed.antithetic is False


@pytest.mark.parametrize("name", ["Scenarios", "Seed", "Measure", "Assets", "Correlations"])
def test_missing_required_setting(settings, tmp_path, name):
    del settings[name]
    with pytest.raises(InputError, match=name):
        parse(settings, tmp_path)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("Unknown", 1),
        ("Scenarios", 0),
        ("Scenarios", True),
        ("Seed", -1),
        ("Seed", 2.0),
        ("Measure", "historical"),
        ("Antithetic", "true"),
        ("Risk_Free", "rf"),
    ],
)
def test_invalid_setting(settings, tmp_path, name, value):
    settings[name] = value
    with pytest.raises(InputError, match=name):
        parse(settings, tmp_path)


@pytest.mark.parametrize(
    "rows",
    ["missing,0.2\na,0.1", "a,0.2\na,0.1", "z,-0.2\na,0.1", "z,NaN\na,0.1"],
)
def test_invalid_assets(settings, tmp_path, rows):
    (tmp_path / "assets.csv").write_text(f"variable,volatility\n{rows}\n", encoding="utf-8")
    with pytest.raises(InputError, match="Assets"):
        parse(settings, tmp_path)


def test_correlation_matrix_missing_asset(settings, tmp_path):
    (tmp_path / "corr.csv").write_text("risk,other,value\nz,z,1\n", encoding="utf-8")
    with pytest.raises(InputError, match=r"Correlations.*a"):
        parse(settings, tmp_path)


def test_correlation_matrix_not_psd(settings, tmp_path):
    (tmp_path / "assets.csv").write_text(
        "variable,volatility\nz,0.2\na,0.1\nrf,0.1\n", encoding="utf-8"
    )
    (tmp_path / "corr.csv").write_text(
        "risk,other,value\nz,z,1\na,a,1\nrf,rf,1\nz,a,-0.9\na,z,-0.9\n"
        "z,rf,-0.9\nrf,z,-0.9\na,rf,-0.9\nrf,a,-0.9\n",
        encoding="utf-8",
    )
    with pytest.raises(InputError, match=r"Correlations.*invalid correlation matrix"):
        parse(settings, tmp_path)


@pytest.mark.parametrize("risk_free", [None, "undeclared", "z"])
def test_invalid_risk_free(settings, tmp_path, risk_free):
    settings["Measure"] = "risk_neutral"
    if risk_free is not None:
        settings["Risk_Free"] = risk_free
    with pytest.raises(InputError, match="Risk_Free"):
        parse(settings, tmp_path)


def test_risk_neutral_settings(settings, tmp_path):
    settings.update(Measure="risk_neutral", Risk_Free="rf", Antithetic=True)
    parsed = parse(settings, tmp_path)
    assert parsed.measure == "risk_neutral"
    assert parsed.risk_free == "rf"
    assert parsed.antithetic is True
