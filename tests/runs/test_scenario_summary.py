import json
from dataclasses import replace

import numpy as np
import polars as pl
import pytest
from numba import get_num_threads, set_num_threads

from avk.api import check, load_run_config, run
from avk.demo.generate import generate
from avk.esg.library import write_parquet
from avk.runtime.errors import ConfigError

SUMMARY = {"Percentiles": [0.75, 0.25], "CTE_Levels": [0.5], "Tail": "upper"}


@pytest.fixture
def summary_run(tmp_path):
    file = generate(tmp_path, "TERM", 8, 209)
    return file, json.loads(file.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "overrides",
    [
        {"Percentiles": None},
        {"Percentiles": [True]},
        {"Percentiles": ["0.4"]},
        {"Percentiles": [-0.01]},
        {"Percentiles": [0.2, 0.2]},
        {"CTE_Levels": [1]},
        {"CTE_Levels": [float("nan")]},
        {"Tail": "both"},
        {"Extra": 1},
    ],
)
def test_summary_validates_levels_and_direction(summary_run, overrides):
    file, config = summary_run
    config["Scenario_Summary"] = {**SUMMARY, **overrides}
    file.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ConfigError, match="Scenario_Summary"):
        load_run_config(file)


def test_summary_requires_every_setting(summary_run):
    file, config = summary_run
    config["Scenario_Summary"] = {"Percentiles": [], "CTE_Levels": []}
    file.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ConfigError, match="Tail"):
        load_run_config(file)


def test_check_rejects_summary_for_a_deterministic_path(summary_run):
    file, config = summary_run
    config["Scenario_Summary"] = SUMMARY
    file.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ConfigError, match="Scenario_Summary.*multiple"):
        check(file)


@pytest.mark.parametrize("product", ["TERM", "UNIT_LINKED"])
def test_summary_matches_paths_and_has_stable_csv(tmp_path, product):
    file = generate(tmp_path, product, 1025, 209)
    base = check(file).scenarios
    assert base is not None
    variables = {name: np.repeat(values, 2, axis=0) for name, values in base.variables.items()}
    shocked = "roi" if product == "TERM" else "ret_eq_large"
    variables[shocked][1, 1:] *= 2
    path_set = replace(
        base,
        variables=variables,
        ids=("2", "10"),
        weights=np.array([0.25, 0.75]),
        measure="real_world",
        seeds=(17, 18),
    )
    path = write_parquet(path_set, tmp_path / "paths.parquet")
    config = json.loads(file.read_text(encoding="utf-8"))
    config["Inputs"]["Scenarios"] = {
        "Source": "parquet",
        "Path": str(path),
        "Settings": {"Measure": "real_world"},
    }
    config["Scenario_Summary"] = SUMMARY
    threads = get_num_threads()
    summaries = []
    try:
        for i, (batch, workers) in enumerate(((256, 1), (2048, min(threads, 4)))):
            config["Batch_Size"] = batch
            file.write_text(json.dumps(config), encoding="utf-8")
            set_num_threads(workers)
            result = run(file, output=tmp_path / f"out-{i}")
            summary = tmp_path / f"out-{i}" / f"{product}_Base_scenario_summary.csv"
            assert summary in result.files
            summaries.append(summary)
    finally:
        set_num_threads(threads)
    assert summaries[0].read_bytes() == summaries[1].read_bytes()

    aggregate = pl.read_csv(summaries[0].with_name(f"{product}_Base_aggregate_output.csv"))
    summary = pl.read_csv(summaries[0])
    step = aggregate.columns[1]
    assert summary.columns == [step, "Output_Column", "Mean", "P_0.75", "P_0.25", "CTE_0.5"]
    first = aggregate.filter(pl.col("Scenario") == 2)
    second = aggregate.filter(pl.col("Scenario") == 10)
    assert summary["Output_Column"].to_list() == [
        name for name in aggregate.columns[2:] for _ in range(first.height)
    ]
    assert not first.drop("Scenario").equals(second.drop("Scenario"))
    for name in aggregate.columns[2:]:
        rows = summary.filter(pl.col("Output_Column") == name)
        np.testing.assert_array_equal(rows[step], first[step])
        a, b = first[name].to_numpy(), second[name].to_numpy()
        np.testing.assert_allclose(rows["Mean"], a / 4 + 3 * b / 4, rtol=1e-15)
        np.testing.assert_array_equal(rows["P_0.75"], b)
        np.testing.assert_array_equal(rows["P_0.25"], np.minimum(a, b))
        np.testing.assert_allclose(rows["CTE_0.5"], (np.maximum(a, b) + b) / 2, rtol=1e-15)
