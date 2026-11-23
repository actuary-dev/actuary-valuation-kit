"""Complete input checks for the independently invented demo formats."""

import json

import polars as pl
import pytest

from avk.api import AvkError, check
from avk.demo.generate import PRODUCTS, generate


@pytest.mark.parametrize("product", PRODUCTS)
def test_demo_formats_load_through_complete_product(tmp_path, product):
    config = generate(tmp_path, product, 20, 209)
    check(config)


@pytest.mark.parametrize("damage", ["missing", "duplicate", "nan", "gap"])
def test_public_mortality_rejects_incomplete_values(tmp_path, damage):
    config = generate(tmp_path, "TERM", 20, 209)
    path = tmp_path / "basis/mortality.csv"
    frame = pl.read_csv(path)
    if damage == "missing":
        frame = frame.head(frame.height - 1)
    elif damage == "duplicate":
        frame = pl.concat([frame, frame.head(1)])
    elif damage == "nan":
        frame = frame.with_columns(pl.lit(float("nan")).alias("value"))
    else:
        frame = frame.filter(pl.col("age") != 30)
    frame.write_csv(path)
    with pytest.raises(AvkError, match="missing|duplicate|finite|consecutive"):
        check(config)


@pytest.mark.parametrize("mode", ["capital", "measurement", "rollforward"])
@pytest.mark.parametrize("product", PRODUCTS)
def test_run_level_public_formats_check(tmp_path, product, mode):
    generate(tmp_path, product, 40, 209)
    check(tmp_path / f"{mode}.json")


@pytest.mark.parametrize(
    ("name", "mode"),
    [
        ("morbidity", "valuation"),
        ("lapse_rates_term", "valuation"),
        ("expenses_rider", "valuation"),
        ("commissions_term", "valuation"),
        ("interest_rates", "valuation"),
        ("product_parameters", "valuation"),
        ("stresses", "capital"),
        ("correlations", "capital"),
        ("balances", "rollforward"),
        ("locked", "measurement"),
    ],
)
def test_public_tables_do_not_default_missing_numbers(tmp_path, name, mode):
    generate(tmp_path, "CRITICAL_ILLNESS_RIDER", 40, 209)
    path = tmp_path / (
        f"{name}.csv" if name in ("stresses", "correlations", "balances") else f"basis/{name}.csv"
    )
    frame = pl.read_csv(path)
    column = "csm" if name == "balances" else "multiplier" if name == "stresses" else "value"
    frame.with_columns(pl.lit(None).alias(column)).write_csv(path)
    with pytest.raises(AvkError, match="missing|finite|numeric|number"):
        check(tmp_path / f"{mode}.json")


def test_public_parameter_override_through_complete_product(tmp_path):
    config = generate(tmp_path, "TERM", 40, 209)
    cfg = json.loads(config.read_text())
    cfg["Cases"] = [
        {"Name": "parameter override", "Overrides": {"Parameters": {"TERM": {"Inflation": 0.03}}}}
    ]
    config.write_text(json.dumps(cfg))
    check(config)


@pytest.mark.parametrize("product", PRODUCTS)
def test_preset_csv_matches_native_complete_run(tmp_path, product):
    import yaml

    from avk.api import run

    generate(tmp_path, product, 24, 209)
    cfg = json.loads((tmp_path / "capital.json").read_text())
    run(tmp_path / "capital.json")
    native = yaml.safe_load((tmp_path / "stress-source.yaml").read_text())
    for case in native["Cases"]:
        case["Name"] = case["Risk"]
    cfg["Stress_Set"] = native
    cfg["Output_path"] = str(tmp_path / "native")
    path = tmp_path / "native.json"
    path.write_text(json.dumps(cfg))
    run(path)
    csv = {p.name: p.read_bytes() for p in (tmp_path / "output/capital").rglob("*.csv")}
    other = {p.name: p.read_bytes() for p in (tmp_path / "native").rglob("*.csv")}
    assert csv == other


def test_stress_csv_rejects_overlapping_windows(tmp_path):
    generate(tmp_path, "CRITICAL_ILLNESS_RIDER", 24, 209)
    path = tmp_path / "stresses.csv"
    frame = pl.read_csv(path).with_columns(
        pl.when((pl.col("risk") == "morbidity") & (pl.col("start_month") == 13))
        .then(12)
        .otherwise(pl.col("start_month"))
        .alias("start_month")
    )
    frame.write_csv(path)
    with pytest.raises(AvkError, match="overlapping stress windows"):
        check(tmp_path / "capital.json")


@pytest.mark.parametrize("product", PRODUCTS)
def test_committed_demo_basis_matches_generator(tmp_path, product):
    from importlib.resources import files
    from pathlib import Path

    generate(tmp_path, product, 20, 209)
    check(tmp_path / "capital.json")
    committed = Path(__file__).resolve().parents[2] / "examples/demo"
    _assert_basis_matches(tmp_path / "basis", committed / "basis")
    for name in ("stresses.csv", "correlations.csv", "stress-source.yaml"):
        _assert_basis_file_matches(tmp_path / name, committed / "basis" / product / name)
    for name in ("solvency_ii_life.yaml", "solvency_ii_riders.yaml"):
        assert files("avk.presets").joinpath(name).read_text(encoding="utf-8")


@pytest.mark.parametrize("product", PRODUCTS)
def test_public_registry_defaults_check_complete_product(tmp_path, product):
    from avk.inputs.registry import BUILTIN_FORMATS

    config = generate(tmp_path, product, 24, 209)
    cfg = json.loads(config.read_text())
    for name, location in cfg["Inputs"]["Replace"].items():
        if name in BUILTIN_FORMATS:
            location.pop("Format", None)
    config.write_text(json.dumps(cfg))
    check(config)


@pytest.mark.parametrize("product", PRODUCTS)
def test_public_diagnostics_use_native_names_and_preserve_outputs(tmp_path, product):
    from avk.api import run

    config = generate(tmp_path, product, 24, 209)
    run(config)
    expected = {p.name: p.read_bytes() for p in (tmp_path / "output/valuation").glob("*.csv")}
    cfg = json.loads(config.read_text())
    cfg["Output_path"] = str(tmp_path / "with-diagnostics")
    config.write_text(json.dumps(cfg))
    folder = tmp_path / "diagnostics"
    run(config, diagnostics=folder)
    actual = {p.name: p.read_bytes() for p in (tmp_path / "with-diagnostics").glob("*.csv")}
    assert actual == expected
    assert list(folder.glob("projection__*.parquet"))
    assert all(
        p.stem.startswith(("projection__", "table__", "context__", "inforce__"))
        or p.stem in {"prepared_policies", "scenarios"}
        for p in folder.glob("*.parquet")
    )


def _assert_basis_file_matches(actual, expected):
    from avk.testing.parity import compare

    if expected.suffix != ".csv":
        assert actual.read_text(encoding="utf-8") == expected.read_text(encoding="utf-8")
        return
    frame = pl.read_csv(expected, infer_schema_length=None)
    # Keys (including numeric keys), text and row order remain exact.
    classes = {
        name: "decrement"
        if name in {"value", "multiplier", "additive", "maximum_decrease", "factor"}
        and dtype.is_numeric()
        else "identifier"
        for name, dtype in frame.schema.items()
    }
    compare(actual, expected, classes=classes).assert_ok()


def _assert_basis_matches(actual, expected):
    expected_files = {p.name for p in expected.iterdir() if p.is_file()}
    assert {p.name for p in actual.iterdir() if p.is_file()} == expected_files
    for name in sorted(expected_files):
        _assert_basis_file_matches(actual / name, expected / name)


def test_committed_basis_drift_detects_one_part_per_billion(tmp_path):
    import shutil
    from pathlib import Path

    generate(tmp_path, "TERM", 20, 209)
    check(tmp_path / "capital.json")
    committed = Path(__file__).resolve().parents[2] / "examples/demo/basis"
    reference = tmp_path / "committed-copy"
    shutil.copytree(committed, reference)
    _assert_basis_matches(tmp_path / "basis", reference)
    path = reference / "mortality.csv"
    frame = pl.read_csv(path)
    # A rate is a fraction: one part in a billion is an absolute 1e-9.
    frame.with_row_index("_row").with_columns(
        pl.when(pl.col("_row") == 0)
        .then(pl.col("value") + 1e-9)
        .otherwise(pl.col("value"))
        .alias("value")
    ).drop("_row").write_csv(path)
    with pytest.raises(AssertionError, match="Parity: FAIL"):
        _assert_basis_matches(tmp_path / "basis", reference)
