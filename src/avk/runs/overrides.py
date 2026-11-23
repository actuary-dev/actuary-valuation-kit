"""Strict case input replacements, resolved over the original run's cached sources."""

from pathlib import Path
from typing import TYPE_CHECKING, Any

import polars as pl
from pydantic import ValidationError

from avk.inputs.registry import InputSpec
from avk.inputs.sources import ResolvedInputs, Sources
from avk.model.compiler import bound
from avk.products.registry import ProductRegistry
from avk.runs.compile import product_ir
from avk.runs.config import RunConfig
from avk.runs.numbers import finite_number
from avk.runtime.errors import ConfigError

if TYPE_CHECKING:
    from avk.runs.check import CheckReport

KEYS = {"Tables", "Parameters", "Curves", "Valuation_Date", "Policy_Data"}


def parse_overrides(raw: object, label: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ConfigError(f"{label}: Overrides must be a mapping")
    if set(raw) - KEYS:
        raise ConfigError(f"{label}: unknown override fields {sorted(set(raw) - KEYS)}")
    result = dict(raw)
    for key in KEYS - {"Valuation_Date"}:
        if key not in raw:
            continue
        if not isinstance(raw[key], dict):
            raise ConfigError(f"{label}: Overrides.{key} must be a mapping")
        if any(not isinstance(name, str) or not name for name in raw[key]):
            raise ConfigError(f"{label}: Overrides.{key} needs nonempty names")
        if key == "Parameters":
            result[key] = {}
            for code, values in raw[key].items():
                if not isinstance(values, dict) or not values:
                    raise ConfigError(f"{label}: Parameters.{code} must be a nonempty mapping")
                result[key][code] = {
                    name: finite_number(value, f"{label}: {code}.{name}")
                    for name, value in values.items()
                }
        else:
            try:
                # The existing input schema validates every source descriptor.
                InputSpec.model_validate({"Replace": raw[key]})
            except ValidationError as exc:
                raise ConfigError(f"{label}: Overrides.{key}: {exc}") from exc
    return result


def csv_override(parts: list[str], value: str, result: dict[str, Any]) -> bool:
    """Recognise override CSV columns even when a cell is empty; values use source paths."""
    if parts == ["Overrides", "Valuation_Date"]:
        if value.strip():
            result["Valuation_Date"] = value
        return True
    if len(parts) == 3 and parts[:2] in [
        ["Overrides", "Tables"],
        ["Overrides", "Curves"],
        ["Overrides", "Policy_Data"],
    ]:
        if value.strip():
            result.setdefault(parts[1], {})[parts[2]] = value
        return True
    if len(parts) == 4 and parts[:2] == ["Overrides", "Parameters"]:
        if value.strip():
            result.setdefault("Parameters", {}).setdefault(parts[2], {})[parts[3]] = value
        return True
    return False


def resolve_overrides(
    base: "CheckReport", overrides: dict[str, Any], root: Path
) -> tuple[RunConfig, ResolvedInputs]:
    """Resolve independent locations and scalar parameters, rejecting unused names first."""
    cfg = base.config
    registry = ProductRegistry.default()
    tables = {"product_parameters"}
    curves: set[str] = set()
    policies: set[str] = set()
    parameters: dict[str, tuple[str, set[str]]] = {}
    for code in cfg.products_to_run:
        factory = registry.for_code(code)
        spec = factory.assumption_spec()
        policies.add(factory.policy_table)
        tables.update(binding.logical_name for binding in spec.tables.values())
        curves.update(
            binding.logical_name
            for binding in spec.tables.values()
            if binding.kind in {"annual_curve", "annual_schedule"}
        )
        parameters[code] = (
            spec.parameter_column or spec.product,
            set(bound(product_ir(factory.definition())).params),
        )
    tables.update(policies)
    replacements = {}
    for key, allowed, noun in (
        ("Tables", tables, "table"),
        ("Curves", curves, "curve"),
        ("Policy_Data", policies, "policy source"),
    ):
        for name, source in overrides.get(key, {}).items():
            if name not in allowed:
                raise ConfigError(f"unknown or unused {noun} {name}")
            if name in replacements:
                raise ConfigError(f"duplicate replacement for {name}")
            replacements[name] = source
    for code, values in overrides.get("Parameters", {}).items():
        if code not in parameters:
            raise ConfigError(f"product {code} is not used by this run")
        for name in values:
            if name not in parameters[code][1]:
                raise ConfigError(f"{code}: unknown or unused parameter {name}")
    run_folder = cfg._path.parent if cfg._path else root
    locations = Sources.resolve(
        InputSpec.model_validate(
            {
                "Replace": replacements,
                "Connections": cfg.inputs.connections if cfg.inputs else {},
            }
        ),
        base=run_folder,
    ).locations
    # Preserve a table-list format when the source descriptor only changes its location.
    locations = {
        name: location.model_copy(update={"format": base.inputs.location(name).format})
        if location.format is None and name in base.inputs.locations
        else location
        for name, location in locations.items()
    }
    inputs = base.inputs.replacing(locations)
    if overrides.get("Parameters"):
        frame = inputs.read("product_parameters")
        for code, values in overrides["Parameters"].items():
            column = parameters[code][0]
            available = frame.filter(pl.col("product") == column)["parameter"].to_list()
            missing_public = set(values) - set(available)
            if missing_public:
                raise ConfigError(
                    f"product_parameters: missing required variables {sorted(missing_public)}"
                )
            for name, value in values.items():
                frame = frame.with_columns(
                    pl.when((pl.col("product") == column) & (pl.col("parameter") == name))
                    .then(pl.lit(value))
                    .otherwise(pl.col("value"))
                    .alias("value")
                )
        inputs.with_frame("product_parameters", frame)
    data = cfg.model_dump()
    data["cases"] = None
    if "Valuation_Date" in overrides:
        data["valuation_date"] = overrides["Valuation_Date"]
    try:
        # Revalidate dates and every ordinary configuration invariant.
        config = RunConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"Valuation_Date: {exc}") from exc
    config._path = cfg._path
    return config, inputs
