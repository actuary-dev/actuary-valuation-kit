"""Scenario CLI orchestration using the same declarations and curve readers as valuation."""

import json
import ntpath
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

from avk.assumptions.context import load_declared
from avk.esg.deterministic import placed_months
from avk.esg.library import Placement, custom, flat, shift, shock, write_parquet
from avk.esg.registry import generator_for
from avk.model.data import ScenarioSet
from avk.runs.check import _resolve_inputs, _scenario_curves, _scenario_variables, run_factory
from avk.runs.config import load_run_config
from avk.runtime.errors import InputError, reader_failure


def _generate(run_file: Path, *, library: bool) -> tuple[ScenarioSet, Placement]:
    cfg = load_run_config(run_file)
    run_folder = run_file.resolve().parent
    factory = run_factory(cfg)
    spec = factory.assumption_spec()
    spec.scenario_variables = _scenario_variables(cfg, spec)
    location = cfg.inputs.scenarios if cfg.inputs and not library else None
    if location is not None and location.source != "generator":
        raise InputError("scenarios generate requires Inputs.Scenarios.Source: generator")
    generator = generator_for(location, spec.scenario_variables, base=run_folder)

    # A scenario export needs the curve bindings. Policy and decrement inputs are not read.
    names = {variable.curve for variable in spec.scenario_variables}
    spec = replace(
        spec, tables={name: binding for name, binding in spec.tables.items() if name in names}
    )
    assumptions = load_declared(spec, _resolve_inputs(cfg, run_folder), cfg)
    curves = _scenario_curves(spec, assumptions)
    horizon = cfg.projection_term * 12
    placement = (
        {
            variable.name: placed_months(horizon, variable, curves[variable.curve].valuation_month)
            for variable in spec.scenario_variables
        }
        if library
        else {}
    )
    return generator.generate(curves, horizon), placement


def generate_scenarios(run_file: Path, output: Path) -> Path:
    scenarios, _ = _generate(run_file, library=False)
    return write_parquet(scenarios, output)


_OPERATION_FIELDS = {
    "flat": {"Variables", "Annual"},
    "shift": {"Variables", "Annual_Change"},
    "shock": {"Variables", "Month", "Factor"},
    "custom": {"Path"},
}


def _operation(
    base: ScenarioSet, operation: Any, placement: Placement, folder: Path
) -> ScenarioSet:
    name = operation.get("Op") if isinstance(operation, dict) else None
    if not isinstance(name, str) or name not in _OPERATION_FIELDS:
        raise InputError(f"Unknown scenario library Op {name!r}")
    expected = {"Op", *_OPERATION_FIELDS[name]}
    if set(operation) != expected:
        raise InputError(f"{name} operation requires exactly {sorted(expected)}")
    if name == "custom":
        path = operation["Path"]
        if not isinstance(path, str) or not path:
            raise InputError("custom Path must name a CSV file")
        return custom(base, folder / path)
    variables = operation["Variables"]
    if not isinstance(variables, list):
        raise InputError("Variables must be a list")
    if name == "flat":
        return flat(base, variables, operation["Annual"], placement=placement)
    if name == "shift":
        return shift(base, variables, operation["Annual_Change"], placement=placement)
    return shock(base, variables, operation["Month"], operation["Factor"])


def scenario_library(run_file: Path, library_file: Path, folder: Path) -> list[Path]:
    try:
        entries = json.loads(library_file.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise InputError(reader_failure("Scenario library", library_file, exc)) from exc
    if not isinstance(entries, list) or not entries:
        raise InputError("Scenario library must be a nonempty JSON list")

    base, placement = _generate(run_file, library=True)
    outputs: dict[str, ScenarioSet] = {}
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"Name", "Operations"}:
            raise InputError("Scenario library entries require Name and Operations")
        name, operations = entry["Name"], entry["Operations"]
        if (
            not isinstance(name, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]+", name)
            or ntpath.isreserved(name)
        ):
            raise InputError("Scenario library Name must be a safe filename stem")
        if name.casefold() in seen:
            raise InputError(f"Duplicate scenario library Name {name!r}")
        seen.add(name.casefold())
        if not isinstance(operations, list):
            raise InputError(f"{name}: Operations must be a list")
        scenarios = base
        for index, operation in enumerate(operations, start=1):
            try:
                scenarios = _operation(scenarios, operation, placement, library_file.parent)
            except InputError as exc:
                raise InputError(f"{name}, operation {index}: {exc}") from exc
        outputs[name] = scenarios
    return [
        write_parquet(scenarios, folder / f"{name}.parquet") for name, scenarios in outputs.items()
    ]
