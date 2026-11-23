"""Build and exercise the wheel in an isolated, runtime-only environment."""

import json
import os
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    env = os.environ.copy()
    for key in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "CONDA_PREFIX"):
        env.pop(key, None)
    env["PYTHONNOUSERSITE"] = "1"

    def run(*args: str, cwd: Path) -> None:
        print("+", *args, flush=True)
        subprocess.run(args, check=True, cwd=cwd, env=env)

    with tempfile.TemporaryDirectory(prefix="avk-wheel-") as temporary:
        work = Path(temporary)
        env["AVK_CACHE_DIR"] = str(work / "cache")
        env["NUMBA_CACHE_DIR"] = str(work / "cache" / "numba")
        run("uv", "build", "--wheel", "--out-dir", str(work), cwd=ROOT)
        (wheel,) = work.glob("*.whl")
        venv = work / "env"
        run("uv", "venv", "--python", sys.executable, str(venv), cwd=work)
        bin_dir = venv / ("Scripts" if os.name == "nt" else "bin")
        exe = ".exe" if os.name == "nt" else ""
        python, avk = (str(bin_dir / (name + exe)) for name in ("python", "avk"))
        run("uv", "pip", "install", "--python", python, str(wheel), cwd=work)
        run(
            python,
            "-c",
            "import importlib.util as u; "
            "assert not any(u.find_spec(p) for p in ('pytest', 'ruff', 'mypy', 'importlinter'))",
            cwd=work,
        )
        if not Path(avk).is_file():
            raise SystemExit("Installed wheel did not provide the avk command")
        with ZipFile(wheel) as archive:
            names = archive.namelist()
        roots = {name.split("/", 1)[0] for name in names}
        with (ROOT / "pyproject.toml").open("rb") as metadata:
            version = tomllib.load(metadata)["project"]["version"]
        metadata_root = f"actuary_valuation_kit-{version}.dist-info"
        if roots != {"avk", metadata_root}:
            raise SystemExit(f"Unexpected wheel contents: {sorted(roots)}")

        excluded = {"tests", "saved", "notebooks", "research"}
        if any(excluded.intersection(name.split("/")) or name.endswith(".ipynb") for name in names):
            raise SystemExit("Wheel includes files outside the runtime package")
        if f"{metadata_root}/licenses/LICENSE" not in names:
            raise SystemExit("Wheel is missing the Apache 2.0 licence")

        demo = work / "demo"
        config = str(demo / "valuation.json")
        run(avk, "demo", "generate", str(demo), "--product", "TERM", "--count", "8", cwd=work)
        run(avk, "check", config, cwd=work)
        run(avk, "run", config, cwd=work)
        output = demo / "output" / "valuation"
        record = json.loads((output / "run_record.json").read_text(encoding="utf-8"))
        if record["status"] != "completed" or record["engine_version"] != version:
            raise SystemExit("Valuation did not record successful completion and the wheel version")
        if not (output / "TERM_Base_aggregate_output.csv").stat().st_size:
            raise SystemExit("Valuation did not write a populated aggregate CSV")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode) from None
