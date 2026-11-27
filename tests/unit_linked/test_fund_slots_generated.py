"""The generated formulas agree with the slot catalogue."""

import shutil
import subprocess
import sys
from pathlib import Path

from avk.products.unit_linked import bindings

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = Path("scripts/generate_ul_fund_slots.py")
MODULE = Path("src/avk/products/unit_linked/fund_slots.py")


def generate(root, *args):
    return subprocess.run(
        ["uv", "run", "--no-sync", sys.executable, str(root / SCRIPT), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def test_generated_fund_slots_are_current():
    result = generate(ROOT, "--check")
    assert result.returncode == 0, result.stderr or result.stdout
    source = (ROOT / MODULE).read_text(encoding="utf-8")
    assert "def fund_close_total(" in source
    for k in range(1, bindings.MAX_FUND_SLOTS + 1):
        assert f"def fund_{k}_close(" in source


def test_generator_uses_slot_count_from_bindings(tmp_path):
    (tmp_path / SCRIPT).parent.mkdir()
    shutil.copyfile(ROOT / SCRIPT, tmp_path / SCRIPT)
    (tmp_path / MODULE).parent.mkdir(parents=True)
    catalogue = MODULE.with_name("bindings.py")
    source = (ROOT / catalogue).read_text(encoding="utf-8")
    count = bindings.MAX_FUND_SLOTS + 1
    (tmp_path / catalogue).write_text(
        source.replace(f"MAX_FUND_SLOTS = {count - 1}", f"MAX_FUND_SLOTS = {count}"),
        encoding="utf-8",
    )
    result = generate(tmp_path)
    assert result.returncode == 0, result.stderr or result.stdout
    generated = (tmp_path / MODULE).read_text(encoding="utf-8")
    assert f"def fund_{count}_close(" in generated
    assert f"self.fund_{count}_close(t)" in generated
