"""Large seeded Term policy book; operator runs only on idle mains power."""

import json
from pathlib import Path

import pyarrow.csv as csv
import pyarrow.parquet as pq
import pytest
from workload import timed

from avk.demo.generate import generate

MIB = 1024 * 1024
PEAK_LIMIT = 1024 * MIB
GROWTH_LIMIT = 128 * MIB


def parquet_book(folder: Path, count: int) -> Path:
    path = generate(folder, "TERM", count, 209)
    cfg = json.loads(path.read_text())
    for name, location in cfg["Inputs"]["Replace"].items():
        if "polic" not in name:
            continue
        source = Path(location["Path"])
        target = source.with_suffix(".parquet")
        with csv.open_csv(source) as reader:
            with pq.ParquetWriter(target, reader.schema) as writer:
                for batch in reader:
                    writer.write_batch(batch)
        cfg["Inputs"]["Replace"][name] = {"Path": str(target), "Source": "parquet"}
    cfg["Output_path"] = str(folder / "output/parquet")
    alternate = folder / "parquet.json"
    alternate.write_text(json.dumps(cfg))
    return alternate


@pytest.mark.perf
def test_million_policy_parquet_memory(tmp_path):
    # Generation runs in this parent; peak RSS is measured in a fresh run-only child.
    # Books and per-policy outputs live only in pytest scratch, never in the repository.
    records = {}
    for count in (100000, 1000000):
        config = parquet_book(tmp_path / str(count), count)
        records[count] = timed(config, tmp_path / f"result-{count}")
    csv_config = tmp_path / "100000/valuation.json"
    parquet_config = tmp_path / "100000/parquet.json"
    timed(csv_config, tmp_path / "prime-csv")
    timed(parquet_config, tmp_path / "prime-parquet")
    csv_warm = [timed(csv_config, tmp_path / f"csv-{i}") for i in range(3)]
    parquet_warm = [timed(parquet_config, tmp_path / f"parquet-{i}") for i in range(3)]
    ratio = min(r["wall"] for r in parquet_warm) / min(r["wall"] for r in csv_warm)
    peak = records[1000000]["peak_rss_bytes"]
    growth = peak - records[100000]["peak_rss_bytes"]
    report = {
        "power": "idle mains, checked by operator",
        "seed": 209,
        "peak_limit_bytes": PEAK_LIMIT,
        "growth_limit_bytes": GROWTH_LIMIT,
        "measurements": records,
        "growth_bytes": growth,
        "csv_warm": csv_warm,
        "parquet_warm": parquet_warm,
        "warm_wall_ratio": ratio,
        "warm_wall_ratio_limit": 1.25,
    }
    print("\nParquet memory:", json.dumps(report), flush=True)
    # These CSV children start after the parent has generated the million-policy book.
    assert all(r["peak_rss_bytes"] < peak for r in csv_warm), report
    assert peak <= PEAK_LIMIT, report
    assert growth <= GROWTH_LIMIT, report
    assert ratio <= 1.25, report
