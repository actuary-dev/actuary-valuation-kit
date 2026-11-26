import json

import numpy as np
import polars as pl
import pytest

from avk.api import check, run
from avk.cli import main
from avk.demo.generate import generate


@pytest.fixture
def book(tmp_path):
    return generate(tmp_path / "book", "TERM", 50, 209)


def test_cli_generates_a_supplied_scenario_file(book, tmp_path):
    config = json.loads(book.read_text(encoding="utf-8"))
    (book.parent / "assets.csv").write_text("variable,volatility\nroi,0.02\n", encoding="utf-8")
    (book.parent / "corr.csv").write_text("risk,other,value\nroi,roi,1\n", encoding="utf-8")
    config["Inputs"]["Scenarios"] = {
        "Source": "generator",
        "Generator": "MultiAssetLognormalESG",
        "Settings": {
            "Scenarios": 4,
            "Seed": 211,
            "Measure": "real_world",
            "Assets": "assets.csv",
            "Correlations": "corr.csv",
        },
    }
    book.write_text(json.dumps(config), encoding="utf-8")
    target = tmp_path / "scenarios.parquet"
    assert main(["scenarios", "generate", str(book), str(target)]) == 0
    file = pl.read_parquet(target)
    expected = check(book).scenarios
    assert file.columns == ["Scenario", "Seed", "Month", *expected.variables]
    assert file["Scenario"].n_unique() == 4

    config["Inputs"]["Scenarios"] = {
        "Source": "parquet",
        "Path": "../scenarios.parquet",
        "Settings": {"Measure": "real_world"},
    }
    book.write_text(json.dumps(config), encoding="utf-8")
    supplied = check(book).scenarios
    assert supplied.ids == expected.ids
    assert supplied.seeds == expected.seeds
    for name in expected.variables:
        np.testing.assert_array_equal(
            supplied.variables[name].view(np.uint64), expected.variables[name].view(np.uint64)
        )
    result = run(book)
    aggregate = next(p for p in result.files if p.name.endswith("_aggregate_output.csv"))
    assert pl.read_csv(aggregate)["Scenario"].n_unique() == 4


def test_cli_generates_the_default_path_using_only_curve_inputs(book, tmp_path):
    config = json.loads(book.read_text(encoding="utf-8"))
    config["Inputs"]["Replace"] = {
        name: config["Inputs"]["Replace"][name]
        for name in ("interest_rates", "ifrs17_interest_rates")
    }
    book.write_text(json.dumps(config), encoding="utf-8")
    target = tmp_path / "deterministic.parquet"
    assert main(["scenarios", "generate", str(book), str(target)]) == 0
    frame = pl.read_parquet(target)
    assert frame["Scenario"].unique().to_list() == [1]
    assert frame["Seed"].unique().to_list() == [0]


def test_cli_library_writes_each_entry_with_placement_and_order(book, tmp_path):
    files = tmp_path / "library"
    files.mkdir()
    library = files / "library.json"
    months = json.loads(book.read_text(encoding="utf-8"))["Projection_Term"] * 12
    (files / "custom.csv").write_text(
        "Month,roi\n" + "".join(f"{month},0.01\n" for month in range(months)),
        encoding="utf-8",
    )
    entries = [
        {
            "Name": "illustration_8",
            "Operations": [
                {"Op": "flat", "Variables": ["roi", "ifrs_current"], "Annual": 0.08},
                {"Op": "shock", "Variables": ["roi"], "Month": 2, "Factor": 0.7},
            ],
        },
        {"Name": "override", "Operations": [{"Op": "custom", "Path": "custom.csv"}]},
    ]
    library.write_text(json.dumps(entries), encoding="utf-8")
    folder = tmp_path / "output"
    assert main(["scenarios", "library", str(book), str(library), str(folder)]) == 0
    assert {p.name for p in folder.iterdir()} == {"illustration_8.parquet", "override.parquet"}
    illustration = pl.read_parquet(folder / "illustration_8.parquet")
    gross = 1.08 ** (1 / 12)
    np.testing.assert_allclose(illustration["roi"].head(3), [0.0, gross - 1, gross * 0.7 - 1])
    np.testing.assert_array_equal(illustration["ifrs_current"].head(2), [0.0, 0.0])
    assert illustration["Seed"].unique().to_list() == [0]
    custom = pl.read_parquet(folder / "override.parquet")
    np.testing.assert_array_equal(custom["roi"], np.full(months, 0.01))


@pytest.mark.parametrize(
    "invalid",
    [
        {"Name": "bad", "Operations": [{"Op": "unknown"}]},
        {"Name": "../bad", "Operations": []},
        {"Name": "first", "Operations": []},
    ],
)
def test_cli_library_validates_all_entries_before_writing(book, tmp_path, capsys, invalid):
    library = tmp_path / "library.json"
    library.write_text(json.dumps([{"Name": "first", "Operations": []}, invalid]), encoding="utf-8")
    folder = tmp_path / "output"
    assert main(["scenarios", "library", str(book), str(library), str(folder)]) == 1
    assert "InputError" in capsys.readouterr().err
    assert not folder.exists()
