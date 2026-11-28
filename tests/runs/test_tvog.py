import json
import math
from dataclasses import replace

import numpy as np
import polars as pl
import pytest

from avk.api import check, run
from avk.demo.generate import generate
from avk.esg.library import write_parquet
from avk.model.data import ScenarioSet


@pytest.fixture
def risk_neutral():
    return ScenarioSet(
        {"roi": np.zeros((3, 2))},
        ("1", "2", "3"),
        np.array([0.25, 0.75, 0.0]),
        "risk_neutral",
        {},
    )


def test_tvog_is_weighted_risk_neutral_pv_less_reference(risk_neutral):
    from avk.api import tvog

    assert tvog(risk_neutral, [50.0, 10.0, np.nan], 24.0) == -4.0
    assert tvog(risk_neutral, [25.0, 25.0, 25.0], 25.0) == 0.0


@pytest.mark.parametrize(
    ("measure", "values", "reference", "message"),
    [
        ("real_world", [1.0, 2.0, 3.0], 1.0, "risk_neutral"),
        ("risk_neutral", [1.0, 2.0], 1.0, "one present value"),
        ("risk_neutral", [[1.0], [2.0], [3.0]], 1.0, "one present value"),
        ("risk_neutral", [1.0, float("inf"), 3.0], 1.0, "finite"),
        ("risk_neutral", [1.0, 2.0, 3.0], float("nan"), "finite"),
    ],
)
def test_tvog_rejects_invalid_inputs(risk_neutral, measure, values, reference, message):
    from avk.api import tvog

    with pytest.raises(ValueError, match=message):
        tvog(replace(risk_neutral, measure=measure), values, reference)


def test_tvog_reads_term_step_zero_pvfp_under_matching_bases(tmp_path):
    from avk.api import tvog

    config_file = generate(tmp_path, "TERM", 8, 209)
    base = check(config_file).scenarios
    assert base is not None and base.measure == "deterministic"
    label = "MCEV_pvfp_BE"
    baseline = run(config_file, output=tmp_path / "reference")
    reference_path = next(file for file in baseline.files if "aggregate_output" in file.name)
    reference = pl.read_csv(reference_path).filter(pl.col("Projection_Step") == 0)[label].item()
    variables = {name: np.repeat(values, 2, axis=0) for name, values in base.variables.items()}
    variables["reference_forward"][1, 1:] += 0.0075
    scenarios = ScenarioSet(
        variables, ("2", "12"), np.array([0.25, 0.75]), "risk_neutral", {}, (1, 2)
    )
    path = write_parquet(scenarios, tmp_path / "risk-neutral.parquet")
    config = json.loads(config_file.read_text(encoding="utf-8"))
    config["Inputs"]["Scenarios"] = {
        "Source": "parquet",
        "Path": str(path),
        "Settings": {"Measure": "risk_neutral"},
    }
    config_file.write_text(json.dumps(config), encoding="utf-8")
    result = run(config_file, output=tmp_path / "risk-neutral")
    path = next(file for file in result.files if "aggregate_output" in file.name)
    rows = pl.read_csv(path).filter(pl.col("Projection_Step") == 0).sort("Scenario")
    assert rows["Scenario"].to_list() == [2, 12]
    first, second = rows[label]
    assert first == reference
    assert second != first
    actual = tvog(scenarios, [first, second], reference)
    assert actual == math.fsum([0.25 * first, 0.75 * second]) - reference
