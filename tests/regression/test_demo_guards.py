"""Public error guard and independent ordinary-Python projection arithmetic."""

import csv
import json
import math
import os
import subprocess
import sys

import polars as pl
import pytest

from avk.api import AvkError, check
from avk.demo.generate import generate
from avk.testing.parity import compare


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("Sum Assured", -1, "negative value"),
        ("Policy Term (Years)", 0, "non-positive value"),
        ("Gender", "bad", "unrecognised Gender"),
        ("Policy Start Date", "bad", "unparseable value"),
    ],
)
def test_public_bad_inputs(tmp_path, column, value, message):
    config = generate(tmp_path, "TERM", 8, 209)
    path = tmp_path / "policies.csv"
    pl.read_csv(path).with_columns(pl.lit(value).alias(column)).write_csv(path)
    with pytest.raises(AvkError, match=message):
        check(config)


@pytest.mark.parametrize(
    ("expression", "message"),
    [
        ("self.missing(t)", "unknown name 'missing'"),
        ("1 if t > 0 else 0", "use if_(condition, then, otherwise)"),
    ],
)
def test_public_bad_formulas(tmp_path, expression, message):
    path = tmp_path / "bad.py"
    path.write_text(
        "from avk.model.lang import Component, Product\n"
        "class Values(Component):\n"
        "    def amount(self, t):\n"
        '        """Invalid demonstration formula."""\n'
        f"        return {expression}\n"
        "class Invalid(Values, Product):\n"
        '    CODE, LABEL, BASES, FIELDS = "INVALID", "Invalid", ("be",), ()\n'
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from avk.cli import main; raise SystemExit(main())",
            "compile",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "FormulaError" in result.stderr and f"{path}:5:" in result.stderr
    assert message in result.stderr, result.stderr


@pytest.mark.purepython
def test_public_independent_small_book(tmp_path):
    config = generate(tmp_path, "TERM", 4, 209)
    path = tmp_path / "policies.csv"
    frame = pl.read_csv(path).with_columns(
        pl.lit("2025-12-31").alias("Policy Start Date"),
        pl.lit("M").alias("Gender"),
        pl.lit("NS").alias("Smoking Status"),
        pl.lit(10).alias("Policy Term (Years)"),
        pl.lit(5).alias("Premium Payment Term"),
    )
    frame.write_csv(path)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from avk.api import run; import sys; run(sys.argv[1])",
            str(config),
        ],
        env={**os.environ, "NUMBA_DISABLE_JIT": "1"},
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    rows = []
    policies = frame.to_dicts()
    lives = {b: [1.0] * 4 for b in ("BE", "reserving")}
    for t in range(372):
        row = {"Projection_Step": t}
        for basis in lives:
            deaths = lapses = premiums = end = 0.0
            for i, policy in enumerate(policies):
                opening = lives[basis][i]
                month = t + 1  # Calendar duration includes the issue month.
                age = policy["Age at Policy Start"] + (month - 1) // 12
                annual_q = min(0.7, 0.00012 + 0.00035 * math.exp(0.075 * (age - 35)))
                annual_q *= 1.12 if basis == "reserving" else 1.0
                death = opening * (1 - (1 - annual_q) ** (1 / 12)) if t else 0.0
                year = (month - 1) // 12 + 1
                annual_w = 0.065 if year == 1 else 0.045 if year <= 3 else 0.025
                annual_w += 0.005 * policy["Distribution Channel"]
                annual_w *= 0.9 if basis == "reserving" else 1.0
                lapse = (
                    (opening - death) * annual_w if t and month % 12 == 0 and month <= 60 else 0.0
                )
                premium = (
                    opening * policy["Premium Amount"]
                    if t and month % 12 == 1 and month <= 60
                    else 0.0
                )
                lives[basis][i] = 0.0 if month == 120 else max(opening - death - lapse, 0.0)
                deaths += death
                lapses += lapse
                premiums += premium
                end += lives[basis][i]
            row.update(
                {
                    f"decrements_deaths_{basis}": deaths,
                    f"decrements_lapses_{basis}": lapses,
                    f"decrements_lives_so_end_{basis}": end,
                    (
                        "cashflows_be_premiums_BE"
                        if basis == "BE"
                        else "cashflows_premiums_reserving"
                    ): premiums,
                }
            )
        rows.append(row)
    oracle = tmp_path / "oracle.csv"
    with oracle.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    actual = tmp_path / "output/valuation/TERM_Base_aggregate_output.csv"
    # Comparator requires complete equal schemas; select the independent columns only.
    selected = tmp_path / "selected.csv"
    pl.read_csv(actual).select(list(rows[0])).write_csv(selected)
    classes = {
        c: "identifier"
        if c == "Projection_Step"
        else "decrement"
        if c.startswith("decrements")
        else "value"
        for c in rows[0]
    }
    compare(selected, oracle, classes=classes).assert_ok()
    (tmp_path / "oracle-summary.json").write_text(
        json.dumps(
            {
                "policies": 4,
                "months": 372,
                "checked_cells": 372 * 8,
                "premium_BE": sum(row["cashflows_be_premiums_BE"] for row in rows),
                "deaths_BE": sum(row["decrements_deaths_BE"] for row in rows),
            },
            indent=2,
        )
    )
