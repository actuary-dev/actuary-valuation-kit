"""Complete product runs: Parquet policy books preserve CSV output bytes."""

import json
from pathlib import Path

import polars as pl
import pytest

from avk.api import InputError, run
from avk.demo.generate import PRODUCTS, generate
from avk.testing.demo import MODES


def parquet_config(path: Path) -> Path:
    cfg = json.loads(path.read_text())
    for name, location in cfg["Inputs"]["Replace"].items():
        if "polic" not in name:
            continue
        source = Path(location["Path"])
        target = source.with_suffix(".parquet")
        pl.read_csv(source, infer_schema_length=None).write_parquet(target, row_group_size=1703)
        cfg["Inputs"]["Replace"][name] = {**location, "Path": str(target), "Source": "parquet"}
    # Opening books are independent policy inputs for the roll-forward.
    opening = cfg.get("IFRS17", {}).get("Roll_Forward", {}).get("Opening", {})
    for name, source in opening.get("Policy_Data", {}).items():
        source = Path(source)
        target = source.with_suffix(".parquet")
        pl.read_csv(source, infer_schema_length=None).write_parquet(target, row_group_size=1703)
        opening["Policy_Data"][name] = {"Path": str(target), "Source": "parquet"}
    cfg["Output_path"] += "-parquet"
    result = path.with_name(path.stem + "-parquet.json")
    result.write_text(json.dumps(cfg))
    return result


@pytest.mark.parametrize("product", PRODUCTS)
@pytest.mark.parametrize("batch_size", [8192, 3073])
def test_parquet_product_bytes(tmp_path, product, batch_size):
    generate(tmp_path, product, 10000, 209)
    for mode in MODES:
        original = tmp_path / f"{mode}.json"
        run(original)
        alternate = parquet_config(original)
        cfg = json.loads(alternate.read_text())
        cfg["Batch_Size"] = batch_size
        alternate.write_text(json.dumps(cfg))
        run(alternate)
        record = json.loads(
            (tmp_path / "output" / (mode + "-parquet") / "run_record.json").read_text()
        )
        assert record["policy_sources"]
        for source in record["policy_sources"].values():
            assert source["batch_rows"] <= batch_size
            assert source["rows"] > 0
            assert source["batches"] == (source["rows"] + batch_size - 1) // batch_size

        left = tmp_path / "output" / mode
        right = tmp_path / "output" / (mode + "-parquet")
        expected = {p.relative_to(left): p.read_bytes() for p in left.rglob("*.csv")}
        actual = {p.relative_to(right): p.read_bytes() for p in right.rglob("*.csv")}
        assert actual and actual == expected


def test_parquet_cross_batch_duplicate_fails_with_record(tmp_path):
    path = generate(tmp_path, "TERM", 24, 209)
    alternate = parquet_config(path)
    cfg = json.loads(alternate.read_text())
    cfg["Batch_Size"] = 8
    alternate.write_text(json.dumps(cfg))
    location = next(v for k, v in cfg["Inputs"]["Replace"].items() if "polic" in k)
    book = Path(location["Path"])
    frame = pl.read_parquet(book)
    frame.with_columns(
        pl.when(pl.int_range(pl.len()) == 18)
        .then(pl.lit(frame["Policy Number"][0]))
        .otherwise(pl.col("Policy Number"))
        .alias("Policy Number")
    ).write_parquet(book, row_group_size=7)
    with pytest.raises(InputError, match="duplicate"):
        run(alternate)
    output = Path(cfg["Output_path"])
    assert json.loads((output / "run_record.json").read_text())["status"] == "failed"
    assert "duplicate" in (output / "error.log").read_text()


@pytest.mark.parametrize("product", PRODUCTS)
def test_parquet_streamed_policy_exports(tmp_path, product):
    config = generate(tmp_path, product, 17, 209)
    cfg = json.loads(config.read_text())
    cfg.update(Projection_Term=1, Output_seriatim_cf_flag=1, Batch_Size=7)
    config.write_text(json.dumps(cfg))
    run(config)
    alternate = parquet_config(config)
    run(alternate)
    left, right = tmp_path / "output/valuation", tmp_path / "output/valuation-parquet"
    assert {p.name: p.read_bytes() for p in left.glob("*.csv")} == {
        p.name: p.read_bytes() for p in right.glob("*.csv")
    }


@pytest.mark.parametrize(
    ("product", "columns"),
    [
        ("TERM", ("Policy Status",)),
        ("ACCIDENTAL_DEATH_RIDER", ("Policy Status",)),
        ("CRITICAL_ILLNESS_RIDER", ("Policy Status",)),
        ("DISABILITY_RIDER", ("Policy Status",)),
        ("CREDIT_LIFE", ("Mode", "Interest Accrue", "Mortality Table Loading Flag")),
    ],
)
@pytest.mark.parametrize("null_batch", [0, 3, None])
def test_parquet_nullable_policy_batches(tmp_path, product, columns, null_batch):
    config = generate(tmp_path, product, 32, 209)
    cfg = json.loads(config.read_text())
    cfg["Batch_Size"] = 8
    config.write_text(json.dumps(cfg))
    book = tmp_path / "policies.csv"
    frame = pl.read_csv(book, infer_schema_length=None)
    frame.with_columns(
        pl.when(pl.lit(True) if null_batch is None else pl.int_range(pl.len()) // 8 == null_batch)
        .then(None)
        .otherwise(pl.col(column))
        .alias(column)
        for column in columns
    ).write_csv(book)
    run(config)
    alternate = parquet_config(config)
    run(alternate)
    left, right = tmp_path / "output/valuation", tmp_path / "output/valuation-parquet"
    assert {p.name: p.read_bytes() for p in left.glob("*.csv")} == {
        p.name: p.read_bytes() for p in right.glob("*.csv")
    }


@pytest.mark.parametrize("operation", ["check", "run", "failure"])
def test_parquet_releases_temporary_mappings(tmp_path, monkeypatch, operation):
    import gc
    import tempfile

    from avk.api import check

    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    config = parquet_config(generate(tmp_path / "book", "TERM", 17, 209))
    if operation == "check":
        report = check(config)
        frame = report.points.frame
        del report
        gc.collect()
        # A caller may retain a prepared frame beyond the report's lifetime.
        assert frame.height == 17
        del frame
    elif operation == "failure":

        def fail_after_preparation(state):
            if state["stage"] == "projecting":
                raise RuntimeError("cancel after preparation")

        with pytest.raises(RuntimeError, match="cancel after preparation"):
            run(config, progress=fail_after_preparation)
    else:
        run(config)
    gc.collect()
    assert not list(scratch.glob("avk-policies-*"))
