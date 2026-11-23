"""Shared runnable setup: one invented policy with transparent arithmetic."""

import json
import subprocess
import sys
from pathlib import Path

import polars as pl

from avk.api import check, compile, run
from avk.demo.generate import generate


def setup(folder):
    """Install the tutorial package into a disposable local discovery folder."""
    folder = Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    site = folder / "site"
    package = Path(__file__).parent / "package"
    subprocess.run(
        ["uv", "pip", "install", "--no-deps", "--target", str(site), str(package)],
        check=True,
    )
    sys.path.insert(0, str(site))
    return folder


def inputs(folder, annual_mortality=0.012):
    config = generate(folder, "TERM", 1, 209)
    path = folder / "policies.csv"
    pl.read_csv(path).with_columns(
        pl.lit(35).alias("Age at Policy Start"),
        pl.lit("2025-12-01").alias("Policy Start Date"),
        pl.lit(2).alias("Policy Term (Years)"),
        pl.lit(2).alias("Premium Payment Term"),
        pl.lit(1000.0).alias("Sum Assured"),
        pl.lit(100.0).alias("Premium Amount"),
        pl.lit(1).alias("Premium Frequency"),
        pl.lit(0).alias("Distribution Channel"),
        pl.lit("M").alias("Gender"),
        pl.lit("NS").alias("Smoking Status"),
    ).write_csv(path)
    for name in ("mortality", "reinsurance_mortality", "lapse_rates_term"):
        if name == "mortality" and annual_mortality is None:
            continue
        rate = annual_mortality if name == "mortality" else 0.0
        path = folder / "basis" / f"{name}.csv"
        pl.read_csv(path).with_columns(pl.lit(rate).alias("value")).write_csv(path)
    return json.loads(config.read_text())


def project(folder, cfg, code, name):
    cfg = {**cfg, "Products_to_run": [code], "Output_path": str(folder / name)}
    path = folder / f"{name}.json"
    path.write_text(json.dumps(cfg, indent=2) + "\n")
    check(path)
    compile([code])
    result = run(path)
    aggregate = next(p for p in result.files if p.name.endswith("_aggregate_output.csv"))
    return pl.read_csv(aggregate)


def verify(frame, annual_mortality=0.012):
    """Independent survival arithmetic checked with the central tolerance policy."""
    monthly = 1 - (1 - annual_mortality) ** (1 / 12)
    survival = 1 - monthly
    columns = {
        "decrements_deaths_BE": [monthly],
        "cashflows_be_death_benefits_BE": [1000 * monthly],
        "decrements_lives_so_end_BE": [survival],
    }
    opening = frame.filter(pl.col("Projection_Step") == 1)
    same_outputs(opening.select(list(columns)), pl.DataFrame(columns))
    # Duration is one month at valuation: 23 future months including maturity.
    totals = {
        "cashflows_be_premiums_BE": [100 * survival**11],
        "cashflows_be_death_benefits_BE": [1000 * (1 - survival**23)],
    }
    same_outputs(frame.select(pl.col(name).sum() for name in totals), pl.DataFrame(totals))
    print(
        f"Monthly death rate = {monthly:.12f}; first deaths = {monthly:.12f}; "
        f"first benefit = {1000 * monthly:.8f}; "
        f"total benefits = {1000 * (1 - survival**23):.8f}; "
        f"future premiums = {100 * survival**11:.8f}; step 1 lives = {survival:.12f}"
    )


def same_outputs(actual, expected):
    """Check all aggregate columns using the central tolerance policy."""
    from tempfile import TemporaryDirectory

    from avk.testing.demo import column_class
    from avk.testing.parity import compare

    with TemporaryDirectory() as temporary:
        a, e = Path(temporary) / "actual.csv", Path(temporary) / "expected.csv"
        actual.write_csv(a)
        expected.write_csv(e)
        classes = {name: column_class(name, dtype) for name, dtype in expected.schema.items()}
        compare(a, e, classes=classes).assert_ok()
