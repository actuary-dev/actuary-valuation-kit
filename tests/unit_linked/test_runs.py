"""Whole-run properties of UNIT_LINKED: oracle independence, batch and thread invariance,
the pure-Python path and a stochastic smoke run."""

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import polars as pl
import pytest

from avk.demo.generate import generate
from avk.testing.parity import compare

ASSETS = (
    "eq_large",
    "eq_mid",
    "eq_small",
    "eq_global",
    "gov_long",
    "gov_short",
    "corp_bond",
    "money_market",
    "gold",
    "real_assets",
)


def run_subprocess(config: Path, env: dict[str, str], timeout: int = 3000) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from avk.api import run; import sys; run(sys.argv[1])",
            str(config),
        ],
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def classes_for(frame: pl.DataFrame) -> dict[str, str]:
    out = {}
    for name in frame.columns:
        if name in ("Policy_Number", "Projection_Step", "Scenario", "Calendar_Month"):
            out[name] = "identifier"
        elif name.startswith("decrements_"):
            out[name] = "decrement"
        else:
            out[name] = "value"
    return out


def test_oracle_imports_nothing_from_avk():
    tree = ast.parse((Path(__file__).parent / "oracle.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert not {name for name in imported if name.split(".")[0] in ("avk", "numpy", "numba")}
    assert imported <= {"__future__", "math", "dataclasses", "datetime", "pathlib", "polars"}


@pytest.mark.slow
def test_batch_and_thread_invariance_on_the_10k_demo(tmp_path):
    path = generate(tmp_path, "UNIT_LINKED", 10000, 209)
    config = json.loads(path.read_text())
    outputs = []
    for batch, threads in ((1000, 1), (10000, 4)):
        folder = tmp_path / f"output-{batch}-{threads}"
        config.update(Batch_Size=batch, Output_path=str(folder))
        run_file = tmp_path / f"run-{batch}-{threads}.json"
        run_file.write_text(json.dumps(config))
        run_subprocess(run_file, {"NUMBA_NUM_THREADS": str(threads)})
        outputs.append(
            {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*.csv")}
        )
    assert outputs[0] and outputs[0] == outputs[1]


@pytest.mark.slow
def test_pure_python_run_equals_the_jit_run(tmp_path):
    from avk.api import run

    path = generate(tmp_path, "UNIT_LINKED", 20, 209)
    config = json.loads(path.read_text())
    runs = {}
    for label, env in (("jit", None), ("python", {"NUMBA_DISABLE_JIT": "1"})):
        folder = tmp_path / f"output-{label}"
        config.update(Output_path=str(folder), Output_seriatim_cf_flag=1)
        run_file = tmp_path / f"run-{label}.json"
        run_file.write_text(json.dumps(config))
        if env is None:
            run(run_file)
        else:
            run_subprocess(run_file, env)
        runs[label] = folder / "valuation"
    for name in (
        "UNIT_LINKED_Base_aggregate_output.csv",
        "UNIT_LINKED_Base_seriatim_output.csv",
        "UNIT_LINKED_Base_output.csv",
    ):
        golden = runs["jit"] / name
        frame = pl.read_csv(golden, infer_schema_length=None)
        compare(runs["python"] / name, golden, classes=classes_for(frame)).assert_ok()


def write_settings(folder: Path) -> None:
    pl.DataFrame(
        {
            "variable": [f"ret_{a}" for a in ASSETS],
            "volatility": [0.22, 0.26, 0.3, 0.2, 0.08, 0.03, 0.06, 0.01, 0.16, 0.14],
        }
    ).write_csv(folder / "assets.csv")
    names = [f"ret_{a}" for a in ASSETS]
    pl.DataFrame(
        {
            "risk": [a for a in names for _ in names],
            "other": [b for _ in names for b in names],
            "value": [1.0 if a == b else 0.0 for a in names for b in names],
        }
    ).write_csv(folder / "correlations.csv")


def test_stochastic_smoke_on_eight_risk_neutral_paths(tmp_path):
    from avk.api import run
    from avk.cli import main

    path = generate(tmp_path, "UNIT_LINKED", 200, 209)
    write_settings(path.parent)
    config = json.loads(path.read_text())
    config["Inputs"]["Scenarios"] = {
        "Source": "generator",
        "Generator": "MultiAssetLognormalESG",
        "Settings": {
            "Scenarios": 8,
            "Seed": 209,
            "Measure": "risk_neutral",
            "Risk_Free": "reference_forward",
            "Assets": "assets.csv",
            "Correlations": "correlations.csv",
        },
    }
    path.write_text(json.dumps(config))
    paths = path.parent / "paths.parquet"
    assert main(["scenarios", "generate", str(path), str(paths)]) == 0
    assert pl.read_parquet(paths)["Scenario"].n_unique() == 8
    config["Inputs"]["Scenarios"] = {
        "Source": "parquet",
        "Path": "paths.parquet",
        "Settings": {"Measure": "risk_neutral"},
    }
    path.write_text(json.dumps(config))
    run(path)
    output = path.parent / "output" / "valuation"
    aggregate = pl.read_csv(output / "UNIT_LINKED_Base_aggregate_output.csv")
    assert aggregate.columns[0] == "Scenario"
    assert sorted(aggregate["Scenario"].unique()) == list(range(1, 9))
    seriatim = pl.read_csv(output / "UNIT_LINKED_Base_seriatim_output.csv")
    assert seriatim.columns[0] == "Scenario" and seriatim.height == 8 * 200
    # With mc_fund_return_source 0 every mc fund grows at the deterministic reference
    # forward rate, so the mc projection (lives, net cashflow, BEL) agrees on every path
    # while the BE results differ. The mc profit chain and capital hold the reserving
    # basis's reserve, which follows each path's returns, so they are not compared.
    mc = [
        name
        for name in aggregate.columns
        if name.startswith("decrements_") and name.endswith("_MC")
    ] + ["MCEV_net_cf_MC", "MCEV_gf_bel_MC", "MCEV_bel_MC", "MCEV_bel_pp_MC", "MCEV_pv_premium_MC"]
    be = ("cashflows_unit_reserve_BE", "cashflows_charges_total_BE")
    first = aggregate.filter(pl.col("Scenario") == 1).drop("Scenario")
    first.select("Projection_Step", *mc).write_csv(tmp_path / "golden.csv")
    for scenario in range(2, 9):
        path_rows = aggregate.filter(pl.col("Scenario") == scenario).drop("Scenario")
        path_rows.select("Projection_Step", *mc).write_csv(tmp_path / "candidate.csv")
        frame = pl.read_csv(tmp_path / "golden.csv")
        compare(
            tmp_path / "candidate.csv", tmp_path / "golden.csv", classes=classes_for(frame)
        ).assert_ok()
        for name in be:
            assert path_rows[name][120] != first[name][120]
