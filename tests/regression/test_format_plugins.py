"""Installed format entry points exercised through complete Term commands."""

import json
import os
import subprocess
import sys

import polars as pl
import pytest

from avk.demo.generate import generate

PLUGIN = """
import numpy as np
from avk.inputs.formats import integer_axis, key_axis, numeric, table

def mortality(frame, spec):
    frame = frame.sort("attained_age")
    ages = frame["attained_age"].to_numpy()
    if not np.array_equal(ages, np.arange(ages[0], ages[-1] + 1)):
        raise ValueError("attained ages must be consecutive and unique")
    frame = frame.rename({"male_probability": spec.columns[0],
                          "female_probability": spec.columns[1],
                          "other_probability": spec.columns[2]})
    return table(spec, numeric(frame, spec.columns, spec),
                 (integer_axis("age", int(ages[0]), len(ages), spec.axes[0]),
                  key_axis("sex", tuple(range(len(spec.columns))))))

not_callable = 17

def wrong_result(frame, spec):
    return frame
"""


def installed_reader(tmp_path, entries, module=PLUGIN):
    """Supply real discoverable package metadata without modifying the shared environment."""
    plugin_dir = tmp_path / "site"
    plugin_dir.mkdir(exist_ok=True)
    (plugin_dir / "example_formats.py").write_text(module)
    metadata = plugin_dir / "example_formats-0.1.dist-info"
    metadata.mkdir(exist_ok=True)
    (metadata / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: example-formats\nVersion: 0.1\n"
    )
    (metadata / "entry_points.txt").write_text("[avk.formats]\n" + entries + "\n")
    return {**os.environ, "PYTHONPATH": os.pathsep.join([str(plugin_dir), *sys.path])}


def invoke(config, command, env):
    return subprocess.run(
        [
            sys.executable,
            "-c",
            "from avk.cli import main; raise SystemExit(main())",
            command,
            str(config),
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def config_with_plugin(tmp_path, format_name="example_mortality", *, invalid=False):
    config = generate(tmp_path, "TERM", 24, 209)
    frame = (
        pl.read_csv(tmp_path / "basis/mortality.csv")
        .pivot(on="field", index="age", values="value")
        .select(
            pl.col("age").alias("attained_age"),
            pl.col("male").alias("male_probability"),
            pl.col("female").alias("female_probability"),
            pl.col("transgender").alias("other_probability"),
        )
    )
    if invalid:
        frame = frame.with_columns(pl.lit(1.01).alias("male_probability"))
    path = tmp_path / "mortality.csv"
    frame.write_csv(path)
    cfg = json.loads(config.read_text())
    cfg["Output_path"] = str(tmp_path / "output")
    cfg["Inputs"]["Replace"]["mortality"] = {"Path": str(path), "Format": format_name}
    config.write_text(json.dumps(cfg))
    return config


def test_installed_format_preserves_complete_product_outputs(tmp_path):
    env = installed_reader(tmp_path, "example_mortality = example_formats:mortality")
    config = config_with_plugin(tmp_path)
    changed = invoke(config, "run", env)
    assert changed.returncode == 0, changed.stdout + changed.stderr
    original_config = generate(tmp_path / "original-inputs", "TERM", 24, 209)
    cfg = json.loads(original_config.read_text())
    cfg["Output_path"] = str(tmp_path / "original")
    original_config.write_text(json.dumps(cfg))
    original = invoke(original_config, "run", env)
    assert original.returncode == 0, original.stdout + original.stderr
    actual = {
        p.relative_to(tmp_path / "output"): p.read_bytes()
        for p in (tmp_path / "output").rglob("*.csv")
    }
    expected = {
        p.relative_to(tmp_path / "original"): p.read_bytes()
        for p in (tmp_path / "original").rglob("*.csv")
    }
    assert actual and actual == expected


@pytest.mark.parametrize(
    ("entries", "format_name", "message"),
    [
        (
            "example_mortality = example_formats:mortality\n"
            "example_mortality = example_formats:mortality",
            "example_mortality",
            "ambiguous",
        ),
        ("avk_mortality_v1 = example_formats:mortality", "avk_mortality_v1", "built-in"),
        ("example_mortality = example_formats:not_callable", "example_mortality", "callable"),
        ("example_mortality = missing_example_formats:mortality", "example_mortality", "load"),
        ("example_mortality = example_formats:wrong_result", "example_mortality", "Table"),
        ("unused = missing_example_formats:mortality", "unknown_example", "unknown format"),
    ],
)
def test_bad_installed_format_is_a_clear_product_error(tmp_path, entries, format_name, message):
    env = installed_reader(tmp_path, entries)
    config = config_with_plugin(tmp_path, format_name)
    result = invoke(config, "check", env)
    assert result.returncode == 1, result.stdout + result.stderr
    assert message in result.stderr
    assert "mortality" in result.stderr
    assert "Traceback" not in result.stderr


def test_plugin_probability_validation_is_preserved(tmp_path):
    env = installed_reader(tmp_path, "example_mortality = example_formats:mortality")
    config = config_with_plugin(tmp_path, invalid=True)
    result = invoke(config, "check", env)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "probability must be between 0 and 1" in result.stderr
    assert "mortality" in result.stderr
    assert "Traceback" not in result.stderr


def test_unselected_broken_plugin_does_not_break_a_product(tmp_path):
    env = installed_reader(tmp_path, "unused = missing_example_formats:mortality")
    config = generate(tmp_path, "TERM", 24, 209)
    result = invoke(config, "check", env)
    assert result.returncode == 0, result.stdout + result.stderr
