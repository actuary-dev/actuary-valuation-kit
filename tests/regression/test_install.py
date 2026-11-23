"""Check the installed wheel and repository paths used by Git installs."""

import os
import subprocess
import sys
import tomllib
from collections.abc import Iterable
from pathlib import Path

import pytest


def _assert_windows_path_lengths(paths: Iterable[str]) -> None:
    limit = 140
    offenders = sorted(
        (path for path in paths if len(path) > limit),
        key=lambda path: (-len(path), path),
    )
    if offenders:
        longest = "\n".join(f"{len(path)} characters: {path}" for path in offenders[:5])
        raise AssertionError(
            f"Repository paths must be at most {limit} characters to leave room for "
            f"the clone folder within the Windows 260-character path limit.\n{longest}"
        )


def test_repository_paths_leave_room_for_windows_clone_folder() -> None:
    project = Path(__file__).resolve().parents[2]
    source_dirs = {"src", "tests", "docs", "notebooks", "scripts", "examples"}
    generated_dirs = {
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".import_linter_cache",
        "build",
        "dist",
        "output",
    }
    paths = []
    for directory, subdirs, files in project.walk():
        if directory == project:
            subdirs[:] = [name for name in subdirs if name in source_dirs]
        else:
            subdirs[:] = [name for name in subdirs if name not in generated_dirs]
        paths.extend((directory / name).relative_to(project).as_posix() for name in files)
    _assert_windows_path_lengths(paths)

    at_limit = f"docs/{'x' * 132}.md"
    _assert_windows_path_lengths([at_limit])
    too_long = f"docs/{'x' * 133}.md"
    with pytest.raises(AssertionError) as error:
        _assert_windows_path_lengths([too_long])
    assert f"141 characters: {too_long}" in str(error.value)


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
