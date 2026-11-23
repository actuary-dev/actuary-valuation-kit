"""Guard 2: execute the published products and notebooks in fresh work folders."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TUTORIALS = ("term", "return_of_premium", "table_format")
NOTEBOOKS = ("valuation", "capital", "rollforward")


@pytest.mark.parametrize("name", TUTORIALS)
def test_tutorial_product(name, tmp_path):
    script = ROOT / "docs" / "tutorials" / f"{name}.py"
    assert script.is_file(), f"Missing tutorial product: {script}"
    result = subprocess.run(
        [sys.executable, str(script), str(tmp_path / name)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS" in result.stdout


@pytest.mark.parametrize("name", NOTEBOOKS)
def test_notebook_headless(name, tmp_path):
    source = ROOT / "notebooks" / f"{name}.ipynb"
    assert source.is_file(), f"Missing notebook: {source}"
    target = tmp_path / source.name
    shutil.copyfile(source, target)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--nbmake",
            "--nbmake-timeout=600",
            "-o",
            "addopts=",
            "-q",
            str(target),
        ],
        cwd=tmp_path,
        env={**os.environ, "PYTHONUTF8": "1"},
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("error", ("missing-cover", "swapped-sexes", "shifted-ages"))
def test_tutorial_negative_control(error, tmp_path):
    """Wrong formulas and table coordinates must fail complete-output parity."""
    tutorials = tmp_path / "tutorials"
    shutil.copytree(ROOT / "docs" / "tutorials", tutorials)
    if error == "missing-cover":
        source = tutorials / "package" / "src" / "tutorial_products" / "formulas.py"
        text = source.read_text()
        assert "self.policy.Sum_Assured * self.deaths(t)" in text
        text = text.replace("self.policy.Sum_Assured * self.deaths(t)", "self.deaths(t)", 1)
        script = tutorials / "term.py"
    else:
        source = tutorials / "table_format.py"
        text = source.read_text()
        if error == "swapped-sexes":
            mutation = 'wide.with_columns(pl.col("f").alias("m"), pl.col("m").alias("f"))'
        else:
            mutation = 'wide.with_columns((pl.col("age") + 1).alias("age"))'
        # Only the wide input changes; ordinary public mortality stays intact.
        assert "wide.write_csv(path)" in text
        text = text.replace("wide.write_csv(path)", mutation + ".write_csv(path)")
        script = tutorials / "table_format.py"
    source.write_text(text)
    result = subprocess.run(
        [sys.executable, str(script), str(tmp_path / "work")],
        text=True,
        capture_output=True,
        check=False,
    )
    output = result.stdout + result.stderr
    assert result.returncode != 0, f"{error} was not detected:\n{output}"
    assert "Parity: FAIL" in output, output
    assert "cashflows_be_death_benefits_BE" in output, output
