"""Seeded public book regressions, using the public saved reporting tables."""

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import polars as pl
import pytest

from avk.api import ConfigError, InputError, check, run
from avk.demo.generate import PRODUCTS, generate
from avk.testing.demo import MODES, PRODUCT_MODES, tables
from avk.testing.parity import compare

SAVED = Path(__file__).resolve().parents[1] / "saved/demo"


@pytest.fixture(scope="module", params=PRODUCTS)
def demo_book(request, tmp_path_factory):
    folder = tmp_path_factory.mktemp(request.param)
    generate(folder, request.param, 10000, 209)
    return folder, request.param


def regression(folder, product, count, mode):
    run(folder / f"{mode}.json")
    output = folder / "output" / mode
    record = json.loads((output / "run_record.json").read_text())
    assert record["status"] == "completed"
    assert record["engine_version"]
    assert record["kernel_identities"]
    assert "fix_set" not in record
    assert record["settings"]["Products_to_run"] == [product]
    assert record["cases"]
    assert record["timings"]
    for item in record["inputs"].values():
        assert item["sha256"] == hashlib.sha256(Path(item["path"]).read_bytes()).hexdigest()
    assert str(folder / f"{mode}.json") in {v["path"] for v in record["inputs"].values()}
    assert (output / "main.log").is_file()
    assert (output / "error.log").read_text() == ""
    assert json.loads((output / "run_status.json").read_text())["status"] == "completed"
    actual = tables(output)
    home = SAVED / str(count) / product / mode
    expected = {
        p.relative_to(home).with_suffix(".csv").as_posix(): p for p in home.rglob("*.parquet")
    }
    assert actual.keys() == expected.keys(), (actual.keys(), expected.keys())
    assert expected, "Generate saved results with python -m avk.testing.demo"
    for name, golden in expected.items():
        compare(actual[name], golden).assert_ok()


@pytest.mark.parametrize("mode", MODES)
def test_public_10k(demo_book, mode):
    folder, product = demo_book
    regression(folder, product, 10000, mode)


@pytest.mark.parametrize("mode", PRODUCT_MODES["UNIT_LINKED"])
def test_public_10k_unit_linked(tmp_path, mode):
    generate(tmp_path, "UNIT_LINKED", 10000, 209)
    regression(tmp_path, "UNIT_LINKED", 10000, mode)


@pytest.mark.slow
@pytest.mark.parametrize("product", PRODUCTS)
def test_public_100k(tmp_path, product):
    generate(tmp_path, product, 100000, 209)
    for mode in MODES:
        regression(tmp_path, product, 100000, mode)


@pytest.mark.slow
def test_public_100k_batch_thread_bytes(tmp_path):
    generate(tmp_path, "TERM", 100000, 209)
    cfg = json.loads((tmp_path / "valuation.json").read_text())
    outputs = []
    for batch, threads in ((1024, 1), (8192, 4)):
        folder = tmp_path / f"output-{threads}"
        cfg.update(Batch_Size=batch, Output_path=str(folder))
        path = tmp_path / f"run-{threads}.json"
        path.write_text(json.dumps(cfg))
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from avk.api import ConfigError, run; import sys; run(sys.argv[1])",
                str(path),
            ],
            env={**os.environ, "NUMBA_NUM_THREADS": str(threads)},
            capture_output=True,
            text=True,
            timeout=900,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        outputs.append(
            {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*.csv")}
        )
    assert outputs[0] and outputs[0] == outputs[1]


def test_rider_event_perturbation_fails(tmp_path):
    """The manifest must reject an event-count drift below the monetary floor."""
    golden = (
        SAVED
        / "10000/ACCIDENTAL_DEATH_RIDER/valuation"
        / "ACCIDENTAL_DEATH_RIDER_Base_aggregate_output.parquet"
    )
    frame = pl.read_parquet(golden)
    candidate = tmp_path / "perturbed.parquet"
    frame.with_columns(
        pl.when(pl.col("Projection_Step") == 1)
        .then(pl.col("decrements_adb_BE") + 0.000005)
        .otherwise(pl.col("decrements_adb_BE"))
        .alias("decrements_adb_BE")
    ).write_parquet(candidate)
    report = compare(candidate, golden)
    assert not report.ok
    result = next(c for c in report.columns if c.name == "decrements_adb_BE")
    assert result.tolerance_class == "decrement"
    assert result.mismatches == 1


def test_failed_run_leaves_audit(tmp_path):
    generate(tmp_path, "TERM", 8, 209)
    path = tmp_path / "valuation.json"
    cfg = json.loads(path.read_text())
    cfg["Products_to_run"] = ["UNKNOWN_PRODUCT"]
    path.write_text(json.dumps(cfg))
    with pytest.raises(ConfigError, match="Unknown product"):
        run(path)
    output = tmp_path / "output/valuation"
    record = json.loads((output / "run_record.json").read_text())
    assert record["status"] == "failed"
    assert record["error"]
    assert (output / "error.log").read_text().strip()
    assert json.loads((output / "run_status.json").read_text())["status"] == "failed"


@pytest.mark.parametrize(
    "key, value",
    [("Sensitivities_Flag", 0), ("Sensitivities_Flag", 1), ("data_source", {})],
)
def test_unknown_run_file_keys_tell_reader_to_delete_them(tmp_path, key, value):
    path = generate(tmp_path, "TERM", 8, 209)
    cfg = json.loads(path.read_text())
    cfg[key] = value
    path.write_text(json.dumps(cfg))

    with pytest.raises(ConfigError, match=rf"Unknown run-file key {key}.*Delete it"):
        check(path)


def test_check_requires_explicit_inputs(tmp_path):
    path = generate(tmp_path, "TERM", 8, 209)
    cfg = json.loads(path.read_text())
    del cfg["Inputs"]
    path.write_text(json.dumps(cfg))

    with pytest.raises(ConfigError, match="Inputs is required"):
        check(path)


@pytest.mark.parametrize("mode", ["valuation", "cases"])
def test_repeat_run_audit_is_deterministic(tmp_path, mode):
    generate(tmp_path, "TERM", 8, 209)
    path = tmp_path / f"{mode}.json"
    records = []
    generated_records = []
    for _ in range(2):
        run(path)
        record = json.loads((tmp_path / "output" / mode / "run_record.json").read_text())
        generated = record.get("generated_files", {})
        generated_records.append(generated)
        for item in generated.values():
            assert item["sha256"] == hashlib.sha256(Path(item["name"]).read_bytes()).hexdigest()
        for key in ("started_at", "finished_at", "timings"):
            record.pop(key)
        records.append(record)
    assert records[0] == records[1]
    if mode == "cases":
        assert all(generated_records), "Generated aggregates must be separate from supplied inputs"


def test_failed_progress_callback_leaves_audit(tmp_path):
    path = generate(tmp_path, "TERM", 8, 209)

    def observer(state):
        raise RuntimeError("observer stopped")

    with pytest.raises(RuntimeError, match="observer stopped"):
        run(path, progress=observer)
    output = tmp_path / "output/valuation"
    assert json.loads((output / "run_record.json").read_text())["status"] == "failed"
    assert "observer stopped" in (output / "error.log").read_text()


def test_run_records_effective_paths(tmp_path):
    path = generate(tmp_path, "TERM", 8, 209)
    cfg = json.loads(path.read_text())
    cfg["Output_path"] = "relative-output"
    path.write_text(json.dumps(cfg))
    root = tmp_path / "effective-root"
    diagnostics = tmp_path / "diagnostics"
    run(path, root=root, diagnostics=diagnostics)
    record = json.loads((root / "relative-output/run_record.json").read_text())
    assert record["resolved_root"] == str(root)
    assert record["output_path"] == str(root / "relative-output")
    assert record["diagnostics_path"] == str(diagnostics)


@pytest.mark.parametrize("entry", ["api", "cli"])
@pytest.mark.parametrize("format_name", ["json", "yaml"])
def test_invalid_settings_leave_audit(tmp_path, entry, format_name):
    path = generate(tmp_path, "TERM", 8, 209)
    cfg = json.loads(path.read_text())
    cfg["Batch_Size"] = 0
    if format_name == "yaml":
        from datetime import date

        import yaml

        cfg["Valuation_Date"] = date(2025, 12, 31)
        path = path.with_suffix(".yaml")
        path.write_text(yaml.safe_dump(cfg))
    else:
        path.write_text(json.dumps(cfg))
    output = tmp_path / "output/valuation"
    if entry == "cli":
        output = tmp_path / "requested-output"
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from avk.cli import main; raise SystemExit(main())",
                "run",
                str(path),
                "--output",
                str(output),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 1, result.stdout + result.stderr
    else:
        with pytest.raises(ConfigError, match="Batch_Size"):
            run(path)
    record = json.loads((output / "run_record.json").read_text())
    assert record["status"] == "failed"
    assert record["settings"]["Batch_Size"] == 0
    assert record["output_path"] == str(output)
    assert record["inputs"][str(path)]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert "Batch_Size" in record["error"]
    assert str(path) in {v["path"] for v in record["inputs"].values()}
    assert "Batch_Size" in (output / "error.log").read_text()
    assert json.loads((output / "run_status.json").read_text())["status"] == "failed"


@pytest.mark.parametrize("damage", ["missing", "malformed"])
def test_bad_configuration_with_explicit_output_leaves_audit(tmp_path, damage):
    path = generate(tmp_path, "TERM", 8, 209)
    if damage == "missing":
        path.unlink()
    else:
        path.write_text("{broken")
    output = tmp_path / "requested-output"
    with pytest.raises(ConfigError):
        run(path, output=output)
    record = json.loads((output / "run_record.json").read_text())
    assert record["status"] == "failed"
    expected = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
    assert record["inputs"][str(path)]["sha256"] == expected
    assert (output / "error.log").read_text().strip()


def test_policy_parse_failure_audit_excludes_row_contents(tmp_path):
    path = generate(tmp_path, "TERM", 8, 209)
    book = tmp_path / "policies.csv"
    header, rows = book.read_text().split("\n", 1)
    book.write_text(header + '\n"PRIVATE_POLICY_123,' + rows)
    with pytest.raises(InputError):
        run(path)
    output = tmp_path / "output/valuation"
    for name in ("error.log", "run_record.json"):
        text = (output / name).read_text()
        assert "PRIVATE_POLICY_123" not in text
        path_text = json.loads(text)["error"] if name == "run_record.json" else text
        assert str(book) in path_text and "policies_term" in path_text
        assert "ComputeError" in text
        assert re.search(r"; (?:line|row) [0-9]+", text)
        assert "DEMO1" not in text
