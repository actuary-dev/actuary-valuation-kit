"""Public documentation contracts checked through the generation command."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_generated_reference_is_current():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/generate_reference.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_published_notebooks_have_no_outputs():
    for path in (ROOT / "notebooks").glob("*.ipynb"):
        cells = json.loads(path.read_text(encoding="utf-8"))["cells"]
        for cell in cells:
            if cell["cell_type"] == "code":
                assert cell["outputs"] == [], path
                assert cell["execution_count"] is None, path
