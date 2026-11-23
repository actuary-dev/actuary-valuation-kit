"""A built wheel exposes its declared version after a clean install."""

import os
import subprocess
import sys
import tomllib
from pathlib import Path


def test_wheel_installs_and_reports_declared_version(tmp_path: Path) -> None:
    """Catch broken packaging, missing CLI entry points and source-tree leakage."""
    project = Path(__file__).resolve().parents[2]
    dist = tmp_path / "dist"
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)

    def run(*args: str, cwd: Path = tmp_path) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, timeout=300)
        assert result.returncode == 0, result.stdout + result.stderr
        return result

    run("uv", "build", "--wheel", "--out-dir", str(dist), cwd=project)
    with (project / "pyproject.toml").open("rb") as metadata:
        expected = tomllib.load(metadata)["project"]["version"]
    (wheel,) = dist.glob("*.whl")
    venv = tmp_path / "clean environment"
    run("uv", "venv", "--python", sys.executable, str(venv))
    scripts = venv / ("Scripts" if os.name == "nt" else "bin")
    python = scripts / ("python.exe" if os.name == "nt" else "python")
    run("uv", "pip", "install", "--python", str(python), str(wheel))
    cli = scripts / ("avk.exe" if os.name == "nt" else "avk")
    result = run(str(cli), "--version")
    assert result.stdout.strip() == expected
    assert result.stderr == ""

    run(
        str(python),
        "-m",
        "avk.demo.generate",
        str(tmp_path / "demo"),
        "--product",
        "TERM",
        "--count",
        "10000",
        "--seed",
        "209",
    )
    run(str(cli), "check", str(tmp_path / "demo/capital.json"))
