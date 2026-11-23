"""Scenario sets produced elsewhere, read as they are from one Parquet file.

The file has one row per scenario and month,
with the columns `Scenario` (an integer scenario number), `Seed` (the integer seed that
generated it, constant within a scenario), `Month` (0 to the horizon less one) and one column
per scenario variable the product declares, exactly those. `Settings: {Measure: ...}` names
the measure (`real_world` or `risk_neutral`); there is no default. Scenarios are equally
weighted and processed in scenario-number order. Generate scenarios externally before
supplying them to the calculator.
"""

import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from avk.assumptions.context import ScenarioVariable
from avk.assumptions.models import InterestCurveAssumption
from avk.esg.base import EconomicScenarioGenerator
from avk.model.data import ScenarioSet
from avk.runtime.errors import InputError
from avk.runtime.progress import fingerprint

KEYS = ("Scenario", "Seed", "Month")
MEASURES = ("real_world", "risk_neutral")


class SuppliedScenarios(EconomicScenarioGenerator):
    """Reads a supplied scenario file; the interest curves are not used."""

    def __init__(
        self, path: Path, variables: Sequence[ScenarioVariable], settings: Mapping[str, Any]
    ) -> None:
        unknown = sorted(set(settings) - {"Measure"})
        if unknown:
            raise InputError(f"Supplied scenarios accept only the setting Measure, not {unknown}")
        if settings.get("Measure") not in MEASURES:
            raise InputError(f"Supplied scenarios need Settings: Measure: one of {MEASURES}")
        self.path = path
        self.names = tuple(variable.name for variable in variables)
        self.measure = str(settings["Measure"])

    def generate(self, curves: Mapping[str, InterestCurveAssumption], horizon: int) -> ScenarioSet:
        try:
            fingerprint(self.path)
            frame = pl.read_parquet(self.path)
        except (OSError, pl.exceptions.PolarsError) as exc:
            raise InputError(f"Cannot read the scenario file {self.path}: {exc}") from exc
        where = f"Scenario file {self.path}"
        missing = sorted(set((*KEYS, *self.names)) - set(frame.columns))
        if missing:
            raise InputError(f"{where}: missing columns {missing}")
        extra = sorted(set(frame.columns) - set((*KEYS, *self.names)))
        if extra:
            raise InputError(f"{where}: unknown scenario variables {extra}")
        for key in KEYS:
            if not frame[key].dtype.is_integer() or frame[key].null_count():
                raise InputError(f"{where}: {key} must hold integers in every row")
        frame = frame.sort("Scenario", "Month")
        numbers = frame["Scenario"].unique(maintain_order=True)
        months = np.tile(np.arange(horizon), len(numbers))
        if frame.height != len(months) or not np.array_equal(frame["Month"].to_numpy(), months):
            raise InputError(f"{where}: every scenario needs months 0 to {horizon - 1}, once each")
        seeds = frame.group_by("Scenario", maintain_order=True).agg(pl.col("Seed").unique())
        if (seeds["Seed"].list.len() != 1).any():
            raise InputError(f"{where}: a scenario's Seed must be the same in every month")
        variables = {}
        for name in self.names:
            values = frame[name].cast(pl.Float64).to_numpy()
            if not np.isfinite(values).all():
                raise InputError(f"{where}: {name} must be finite in every row")
            variables[name] = values.reshape(len(numbers), horizon)
        digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
        return ScenarioSet(
            variables,
            tuple(str(number) for number in numbers.to_list()),
            np.full(len(numbers), 1 / len(numbers)),
            self.measure,
            {"source": "parquet", "path": str(self.path), "sha256": digest},
            tuple(int(seed[0]) for seed in seeds["Seed"].to_list()),
        )
