"""Strict stress metadata; ordinary cases still own input resolution and shocks."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from avk.inputs.formats import read_csv_format
from avk.runs.capital_settings import KEYS
from avk.runs.config import RunConfig
from avk.runs.numbers import finite_number
from avk.runtime.errors import ConfigError, reader_failure
from avk.runtime.progress import fingerprint

EXPENSE_KEYS = {"Expense_Method", "Expense_Discount_Rate"}
METHODS = ("revaluation", "mass_lapse", "catastrophe")
CLEAN_METHODS = {"mass lapse": "mass_lapse", "catastrophe": "catastrophe"}


@dataclass(frozen=True)
class Stress:
    name: str
    risk: str
    method: str
    factor: float | None = None


def _read(cfg: RunConfig, root: Path) -> dict[str, Any]:
    raw = cfg.stress_set
    if isinstance(raw, str):
        path = (cfg._path.parent if cfg._path else root) / raw
        try:
            fingerprint(path)
            raw = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
        except (OSError, yaml.YAMLError) as exc:
            raise ConfigError(reader_failure("Stress_Set", path, exc)) from exc
    if (
        not isinstance(raw, dict)
        or set(raw) - {"Cases", "Settings", "Correlation"}
        or "Cases" not in raw
    ):
        raise ConfigError("Stress_Set expects Cases, optional Correlation and Settings")
    if isinstance(raw["Cases"], dict):
        location = raw["Cases"]
        if set(location) != {"CSV", "Format"}:
            raise ConfigError("Stress Cases table needs CSV and Format")
        table = read_csv_format(
            str((cfg._path.parent if cfg._path else root) / location["CSV"]),
            location["Format"],
            "stress sets",
        )
        cases: dict[str, dict[str, Any]] = {}
        for key, values in zip(table.axes[0].keys, table.values, strict=True):
            risk, target, method, _ = str(key).split("|")
            a, m, start, end, cap, factor = (float(v) for v in values)
            if risk not in cases:
                cases[risk] = {"Name": risk, "Risk": risk, "Method": method, "Shocks": {}}
            entry = cases[risk]
            if entry["Method"] != method:
                raise ConfigError("Stress table: inconsistent method per risk")
            if method == "revaluation":
                if factor != 0:
                    raise ConfigError("Stress table: unused factor")
                shock = {"Additive": a, "Multiplicative": m}
                if target == "lapse":
                    shock["Maximum_Decrease"] = cap
                elif cap != 1:
                    raise ConfigError("Stress table: only lapse uses maximum_decrease")
                if start != 0 or end != 0:
                    shock.update(Start_Month=start, End_Month=end)
                previous = entry["Shocks"].get(target)
                if previous is None:
                    entry["Shocks"][target] = shock
                elif isinstance(previous, list):
                    previous.append(shock)
                else:
                    entry["Shocks"][target] = [previous, shock]
            else:
                if target != "none" or (a, m, start, end, cap) != (0, 1, 0, 0, 1):
                    raise ConfigError("Stress table: analytic row requires neutral shock fields")
                entry["Factor"] = factor
        raw = {**raw, "Cases": list(cases.values())}
    return raw


def _risk_label(item: dict[str, Any], seen: dict[str, str]) -> str:
    risk = item.get("Risk")
    if (
        not isinstance(risk, str)
        or not risk.strip()
        or risk != risk.strip()
        or any(ord(c) < 32 for c in risk)
    ):
        raise ConfigError(
            "Stress_Set Risk must be a nonempty text label without control characters"
        )
    if risk.casefold() == "lapse":
        raise ConfigError("lapse is reserved for the derived maximum")
    if risk.casefold() in seen and seen[risk.casefold()] != risk:
        raise ConfigError("Risk labels differing only by case are ambiguous")
    seen[risk.casefold()] = risk
    return risk


def _method(item: dict[str, Any], risk: str) -> str:
    clean = CLEAN_METHODS.get(risk.casefold())
    method = item.get("Method", clean or "revaluation")
    if clean is not None and method != clean:
        raise ConfigError(f"{risk}: requires clean Method {clean} with Factor")
    if method not in METHODS:
        raise ConfigError(f"{risk}: unknown stress Method {method}")
    return str(method)


def _factor(item: dict[str, Any], ordinary: dict[str, Any], method: str, risk: str) -> float | None:
    if method not in ("mass_lapse", "catastrophe"):
        if "Factor" in item:
            raise ConfigError(f"{risk}: Factor is only for mass_lapse/catastrophe")
        return None
    factor = finite_number(item.get("Factor"), f"{risk}: Factor")
    if not 0 <= factor <= 1:
        raise ConfigError(f"{risk}: Factor must be between 0 and 1")
    if set(ordinary) - {"Name", "Shocks"} or ordinary["Shocks"]:
        raise ConfigError(f"{risk}: analytic method uses base inputs and Factor only")
    return factor


def load_stresses(cfg: RunConfig, root: Path) -> tuple[RunConfig, tuple[Stress, ...]]:
    if cfg.run_type != "StressCapital":
        if cfg.stress_set is not None:
            raise ConfigError("Stress_Set requires Run_Type StressCapital")
        return cfg, ()
    if cfg.stress_set is None or cfg.cases is not None:
        raise ConfigError("StressCapital needs Stress_Set and cannot also supply Cases")
    raw = _read(cfg, root)
    settings = raw.get("Settings", {})
    if not isinstance(settings, dict):
        raise ConfigError("Stress_Set Settings: invalid mapping")
    if set(settings) & EXPENSE_KEYS:
        raise ConfigError(
            "Stress_Set Settings: unsupported Expense_Method or Expense_Discount_Rate. "
            "Use expense revaluation."
        )
    if set(settings) - KEYS:
        raise ConfigError("Stress_Set Settings: unknown setting")
    items = raw["Cases"]
    if not isinstance(items, list) or not items:
        raise ConfigError("Stress_Set Cases must be a nonempty list")
    stresses, cases = [], []
    seen: dict[str, str] = {}
    for entry in items:
        if not isinstance(entry, dict):
            raise ConfigError("Stress_Set case must be a mapping")
        item = dict(entry)
        risk = _risk_label(item, seen)
        method = _method(item, risk)
        ordinary = {
            k: v for k, v in item.items() if k not in ("Risk", "Method", "Factor", "Discount_Rate")
        }
        ordinary.setdefault("Shocks", {})
        factor = _factor(item, ordinary, method, risk)
        if "Discount_Rate" in item:
            raise ConfigError("Discount_Rate annuity option removed; use revaluation")
        cases.append(ordinary)
        stresses.append(Stress(str(item.get("Name", "")), risk, method, factor))
    return cfg.model_copy(update={"cases": cases, "stress_set": raw}), tuple(stresses)
