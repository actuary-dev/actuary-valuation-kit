"""Manifest-driven numerical comparisons; the sole tolerance policy.

No exceptions have been approved. Supplying an exception file fails closed.
"""

from __future__ import annotations

import ast
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Literal, cast

import numpy as np
import numpy.typing as npt
import polars as pl

ToleranceClass = Literal["identifier", "text", "list", "rate", "decrement", "value"]
CLASS_RULES: Mapping[ToleranceClass, tuple[float, float]] = MappingProxyType(
    {
        "identifier": (0.0, 0.0),
        "text": (0.0, 0.0),
        "list": (0.0, 0.0),
        "rate": (1e-12, 0.0),
        "decrement": (1e-9, 1e-10),
        "value": (1e-6, 1e-8),
    }
)
# The absolute floor applies only to monetary values. Strict non-monetary
# rules stay unchanged, so the floor applies to a "value" column only when it is not listed in
# NON_MONETARY_VALUES.
VALUE_ABSOLUTE_FLOOR = 1e-5
# "value" is the manifest default for every computed number, so these captured columns hold lives,
# counts, coverage units, factors, rates, flags and policy attributes rather than money. They keep
# the plain value rule. A new golden that captures another non-monetary "value" column adds it
# here until capture assigns a dedicated class.
NON_MONETARY_VALUES = frozenset(
    {
        "policies",
        "coverage_units",
        "coverage_units_total",
        "pv_coverage_units",
        "provided_coverage_units",
        "loss_release_fraction",
        "future_coverage_units",
        "release_fraction",
    }
)


@dataclass(frozen=True)
class ColumnResult:
    name: str
    tolerance_class: ToleranceClass
    mismatches: int
    max_relative: float = 0.0
    max_scaled: float = 0.0


@dataclass
class Report:
    """A complete comparison, including structural failures and per-column maxima."""

    columns: list[ColumnResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors and all(item.mismatches == 0 for item in self.columns)

    def assert_ok(self) -> None:
        if not self.ok:
            raise AssertionError(self.to_markdown())

    def to_markdown(self) -> str:
        lines = ["Parity: " + ("PASS" if self.ok else "FAIL")]
        lines.extend(self.errors)
        lines.extend(
            [
                "",
                "| Column | Class | Mismatches | Max relative | Max scaled |",
                "|---|---|---:|---:|---:|",
            ]
        )
        lines.extend(
            f"| {r.name} | {r.tolerance_class} | {r.mismatches} | "
            f"{r.max_relative:.8g} | {r.max_scaled:.8g} |"
            for r in self.columns
        )
        return "\n".join(lines)


def _read(path: Path) -> pl.DataFrame:
    if path.suffix == ".parquet":
        return pl.read_parquet(path)
    return pl.read_csv(path, infer_schema_length=None, null_values=["", "NaN", "nan"])


def _manifest_classes(golden: Path) -> Mapping[str, ToleranceClass]:
    for home in golden.resolve().parents:
        manifest = home / "MANIFEST.json"
        if manifest.is_file():
            entry = json.loads(manifest.read_text(encoding="utf-8"))["files"].get(
                golden.resolve().relative_to(home).as_posix()
            )
            if entry is not None:
                return cast(Mapping[str, ToleranceClass], entry["classes"])
    raise ValueError(f"No manifest classes for {golden}")


def _numbers(
    c: npt.NDArray[np.float64],
    g: npt.NDArray[np.float64],
    scale: npt.NDArray[np.float64],
    rule: tuple[float, float],
    absolute_floor: float = 0.0,
) -> tuple[int, float, float]:
    finite = np.isfinite(g) & np.isfinite(c)
    same_special = (np.isnan(c) & np.isnan(g)) | (np.isinf(g) & (c == g))
    delta = np.zeros_like(g)
    np.subtract(c, g, out=delta, where=finite)
    delta = np.abs(delta)
    allowed = np.maximum(absolute_floor, rule[0] * np.abs(g) + rule[1] * scale)
    passed = same_special | (finite & (delta <= allowed))
    with np.errstate(invalid="ignore", divide="ignore"):
        relative = np.where(delta == 0, 0.0, delta / np.abs(g))
        scaled = np.where(delta == 0, 0.0, delta / scale)
    return (
        int(np.count_nonzero(~passed)),
        float(np.max(relative[finite], initial=0)),
        float(np.max(scaled[finite], initial=0)),
    )


def _list_value(value: object) -> object:
    if isinstance(value, str):
        return ast.literal_eval(value)
    return value


def _list_equal(c: object, g: object) -> bool:
    if isinstance(g, (list, tuple)):
        return (
            isinstance(c, (list, tuple))
            and len(c) == len(g)
            and all(_list_equal(x, y) for x, y in zip(c, g, strict=True))
        )
    if isinstance(g, (int, float)) and not isinstance(g, bool):
        if not isinstance(c, (int, float)) or isinstance(c, bool):
            return False
        # Loan schedule elements are prepared inputs, hence the rate class.
        ca, ga = np.asarray([c], dtype=float), np.asarray([g], dtype=float)
        return _numbers(ca, ga, np.abs(ga), CLASS_RULES["rate"])[0] == 0
    return bool(type(c) is type(g) and c == g)


def _compare(
    candidate: Path,
    golden: Path,
    classes: Mapping[str, ToleranceClass],
    columns: Sequence[str] | None,
) -> Report:
    report = Report()
    c, g = _read(candidate), _read(golden)
    if c.columns != g.columns:
        report.errors.append("Column names/order differ")
        return report
    if c.height != g.height:
        report.errors.append(f"Row count differs: {c.height} != {g.height}")
        return report
    selected = list(g.columns if columns is None else columns)
    if len(selected) != len(set(selected)) or not set(selected) <= set(g.columns):
        raise ValueError("columns must be unique golden column names")
    # Even a column subset cannot hide key/row misalignment.
    for key in ("Policy_Number", "Projection_Step"):
        if key in g.columns and key not in selected:
            selected.insert(0, key)
    for name in selected:
        cls = classes.get(name)
        if cls is None or cls not in CLASS_RULES:
            raise ValueError(f"Missing or unknown tolerance class for {name}: {cls!r}")
        cs, gs = c[name], g[name]
        if cls in ("identifier", "text"):
            mismatch = sum(x != y for x, y in zip(cs.to_list(), gs.to_list(), strict=True))
            report.columns.append(ColumnResult(name, cls, mismatch))
        elif cls == "list":
            mismatch = sum(
                not _list_equal(_list_value(x), _list_value(y))
                for x, y in zip(cs.to_list(), gs.to_list(), strict=True)
            )
            report.columns.append(ColumnResult(name, cls, mismatch))
        else:
            if not cs.dtype.is_numeric() or not gs.dtype.is_numeric():
                report.errors.append(f"Non-numeric data in {name} ({cls})")
                continue
            cv = cs.cast(pl.Float64).to_numpy()
            gv = gs.cast(pl.Float64).to_numpy()
            finite_abs = np.where(np.isfinite(gv), np.abs(gv), 0.0)
            if "Policy_Number" in g.columns:
                # Seriatim files have one row per policy and no step; they still must not
                # borrow a larger policy's scale.
                scales = (
                    g.select("Policy_Number")
                    .with_columns(pl.Series("_scale", finite_abs))
                    .select(pl.col("_scale").max().over("Policy_Number"))
                    .to_series()
                    .to_numpy()
                )
            else:
                scales = np.full(g.height, np.max(finite_abs, initial=0))
            count, relative, scaled = _numbers(
                cv,
                gv,
                scales,
                CLASS_RULES[cls],
                VALUE_ABSOLUTE_FLOOR if cls == "value" and name not in NON_MONETARY_VALUES else 0.0,
            )
            # Null and IEEE NaN are different writer representations.
            count += int(np.count_nonzero(cs.is_null().to_numpy() != gs.is_null().to_numpy()))
            report.columns.append(ColumnResult(name, cls, count, relative, scaled))
    return report


def compare(
    candidate: Path,
    golden: Path,
    *,
    classes: Mapping[str, ToleranceClass] | None = None,
    columns: Sequence[str] | None = None,
    exceptions: Path | None = None,
) -> Report:
    """Compare rows in writer order, with manifest classes unless explicitly provided."""
    if exceptions is not None:
        raise ValueError("No parity exceptions are approved; an exception cannot be applied")
    return _compare(
        candidate, golden, _manifest_classes(golden) if classes is None else classes, columns
    )
