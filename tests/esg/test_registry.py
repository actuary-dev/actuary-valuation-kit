import json

import polars as pl
import pytest

from avk.api import run
from avk.assumptions.context import ScenarioVariable
from avk.demo.generate import generate
from avk.esg.multi_asset import MultiAssetLognormalESG
from avk.esg.registry import generator_for
from avk.inputs.registry import Location
from avk.runtime.errors import InputError
from avk.testing.demo import column_class
from avk.testing.parity import compare

ROI = (ScenarioVariable("roi", "interest_rates", "roi", "lag", 1),)


def _source(folder, volatility):
    (folder / "assets.csv").write_text(f"variable,volatility\nroi,{volatility}\n", encoding="utf-8")
    (folder / "correlations.csv").write_text("risk,other,value\nroi,roi,1\n", encoding="utf-8")
    return {
        "Source": "generator",
        "Generator": "MultiAssetLognormalESG",
        "Settings": {
            "Scenarios": 4,
            "Seed": 209,
            "Measure": "real_world",
            "Assets": "assets.csv",
            "Correlations": "correlations.csv",
        },
    }


def test_deterministic_generator_rejects_settings():
    location = Location.model_validate(
        {"Source": "generator", "Generator": "DeterministicCurveESG", "Settings": {"Seed": 1}}
    )
    with pytest.raises(InputError, match="DeterministicCurveESG does not accept Settings"):
        generator_for(location, ROI)


def test_unknown_generator():
    location = Location.model_validate({"Source": "generator", "Generator": "unknown"})
    with pytest.raises(InputError, match="Unknown scenario generator: unknown"):
        generator_for(location, ROI)


def test_select_multi_asset_generator(tmp_path):
    location = Location.model_validate(_source(tmp_path, 0.02))
    generator = generator_for(location, ROI, base=tmp_path)
    assert isinstance(generator, MultiAssetLognormalESG)
    assert generator.settings.scenarios == 4
    assert generator.settings.assets[0].volatility == 0.02


def test_registry_rejects_unknown_multi_asset_setting(tmp_path):
    source = _source(tmp_path, 0.02)
    source["Settings"]["Unexpected"] = True
    with pytest.raises(InputError, match=r"Settings.*Unexpected"):
        generator_for(Location.model_validate(source), ROI, base=tmp_path)


def _aggregate(result):
    return next(path for path in result.files if path.name.endswith("_aggregate_output.csv"))


def test_term_valuation_with_generated_scenarios(tmp_path):
    path = generate(tmp_path, "TERM", 50, 209)
    baseline = _aggregate(run(path))
    config = json.loads(path.read_text(encoding="utf-8"))
    config["Inputs"]["Scenarios"] = _source(tmp_path, 0.02)
    path.write_text(json.dumps(config), encoding="utf-8")

    varied = pl.read_csv(_aggregate(run(path, output=tmp_path / "varied")))
    assert varied.columns[0] == "Scenario"
    assert varied["Scenario"].unique(maintain_order=True).to_list() == [1, 2, 3, 4]
    assert (
        not varied.filter(pl.col("Scenario") == 1)
        .drop("Scenario")
        .equals(varied.filter(pl.col("Scenario") == 2).drop("Scenario"))
    )

    record = json.loads((tmp_path / "varied/run_record.json").read_text(encoding="utf-8"))
    assert {str(tmp_path / name) for name in ("assets.csv", "correlations.csv")} <= set(
        record["inputs"]
    )

    _source(tmp_path, 0)
    steady = pl.read_csv(_aggregate(run(path, output=tmp_path / "steady")))
    classes = {
        name: column_class(name, dtype) for name, dtype in steady.drop("Scenario").schema.items()
    }
    for scenario in (1, 2, 3, 4):
        steady_path = tmp_path / f"scenario-{scenario}.csv"
        steady.filter(pl.col("Scenario") == scenario).drop("Scenario").write_csv(steady_path)
        compare(steady_path, baseline, classes=classes).assert_ok()
