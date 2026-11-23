"""Guard 3: public 100k Term, recorded only on idle mains power."""

import json
import os
from pathlib import Path

import pytest
from workload import timed

from avk.demo.generate import generate

BASELINE = Path(__file__).with_name("demo_baseline_wsl_laptop.json")


@pytest.mark.perf
def test_public_term_speed(tmp_path):
    config = generate(tmp_path / "book", "TERM", 100000, 209)
    cold = timed(config, tmp_path / "cold", cache=tmp_path / "cold-cache")
    timed(config, tmp_path / "prime")
    warm = [timed(config, tmp_path / f"warm-{i}") for i in range(3)]
    record = {
        "policies": 100000,
        "projection_months": 372,
        "seed": 209,
        "threads": 16,
        "batch_size": 8192,
        "power": "idle mains, checked by operator",
        "cold": cold,
        "warm": warm,
        "warm_wall_s": min(r["wall"] for r in warm),
        "fixed_overhead_s": min(r["timings"]["overhead"] for r in warm),
    }
    print("\nPublic demo speed:", json.dumps(record), flush=True)
    assert cold["timings"]["compile"] <= 30.0, record
    assert record["fixed_overhead_s"] <= 1.0, record
    if BASELINE.exists():
        assert record["warm_wall_s"] <= 1.25 * json.loads(BASELINE.read_text())["warm_wall_s"], (
            record
        )
    if os.environ.get("AVK_RECORD_DEMO_BASELINE") == "1":
        assert not BASELINE.exists(), "Never replace an existing approved speed baseline"
        BASELINE.write_text(json.dumps(record, indent=2) + "\n")
    else:
        assert BASELINE.exists(), "Record baseline on idle mains power before running Guard 3"
