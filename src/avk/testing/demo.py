"""Public demo regression capture. References are produced only by complete runs."""

import argparse
import json
from pathlib import Path
from typing import Any

import polars as pl

from avk.api import run
from avk.demo.generate import PRODUCTS, generate
from avk.testing.parity import NON_MONETARY_VALUES

MODES = ("valuation", "cases", "capital", "measurement", "rollforward")


def is_reporting_table(name: str) -> bool:
    return name.endswith(("_aggregate_output.csv", "_group_output.csv")) or name in {
        "cases_impact.csv",
        "IFRS17_rollforward.csv",
    }


def prune(destination: Path) -> None:
    """Discard non-reporting exports from an unapproved capture, using the same policy."""
    manifest_path = destination / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text())
    for name in list(manifest["files"]):
        if not is_reporting_table(Path(name).with_suffix(".csv").name):
            (destination / name).unlink()
            del manifest["files"][name]
        else:
            schema = pl.read_parquet_schema(destination / name)
            manifest["files"][name]["classes"] = {
                column: column_class(column, dtype) for column, dtype in schema.items()
            }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    size = sum(p.stat().st_size for p in destination.rglob("*.*"))
    print(f"Reporting tables only: {size / 1000000:.3f} MB", flush=True)


def tables(folder: Path) -> dict[str, Path]:
    """Capture all aggregate, impact, capital and group tables, never seriatim."""
    return {
        p.relative_to(folder).as_posix(): p
        for p in sorted(folder.rglob("*.csv"))
        if is_reporting_table(p.name)
    }


def column_class(name: str, dtype: pl.DataType) -> str:
    if not dtype.is_numeric():
        return "text"
    lower = name.lower()
    if lower in {"projection_step", "scenario", "cohort", "reporting_months", "month"}:
        return "identifier"
    if lower.startswith("decrements_") or any(
        s in lower
        for s in ("lives_", "deaths", "lapses", "maturities", "adj_px", "claimant", "event_count")
    ):
        return "decrement"
    if name in NON_MONETARY_VALUES:
        return "value"
    if lower.endswith("_pct") or any(s in lower for s in ("rate", "factor", "fraction")):
        return "rate"
    return "value"


def regenerate(destination: Path, scratch: Path, counts: list[int]) -> None:
    manifest_path = destination / "MANIFEST.json"
    manifest: dict[str, Any] = (
        json.loads(manifest_path.read_text())
        if manifest_path.exists()
        else {"seed": 209, "reference": "Invented demo; owner approval required", "files": {}}
    )
    for count in counts:
        for product in PRODUCTS:
            folder = scratch / str(count) / product
            generate(folder, product, count, 209)
            for mode in MODES:
                print(f"RUN {count} {product} {mode}", flush=True)
                run(folder / f"{mode}.json")
                for name, source in tables(folder / "output" / mode).items():
                    relative = f"{count}/{product}/{mode}/{name.removesuffix('.csv')}.parquet"
                    target = destination / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    frame = pl.read_csv(
                        source, infer_schema_length=None, null_values=["NaN", "nan"]
                    )
                    frame.write_parquet(target, compression="zstd")
                    manifest["files"][relative] = {
                        "classes": {c: column_class(c, t) for c, t in frame.schema.items()},
                        "rows": frame.height,
                    }
                manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    size = sum(p.stat().st_size for p in destination.rglob("*.*"))
    print(f"Saved results: {size / 1000000:.3f} MB", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("scratch", type=Path)
    parser.add_argument("--counts", type=int, nargs="+", default=[10000, 100000])
    parser.add_argument("--prune", action="store_true")
    args = parser.parse_args()
    if args.prune:
        prune(args.destination)
    else:
        regenerate(args.destination, args.scratch, args.counts)


if __name__ == "__main__":
    main()
