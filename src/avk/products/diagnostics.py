"""Product diagnostics."""

from collections.abc import Mapping

import numpy as np
import polars as pl

from avk.assumptions.models import ProductParameters, TabularAssumption
from avk.inputs.policies import PreparationConfig
from avk.inputs.sources import ResolvedInputs
from avk.model.data import ModelPoints, ScenarioSet
from avk.model.executor import Batch


class ProjectionRecorder:
    """Native columns for a small book, held in memory for debugging."""

    def __init__(self, numbers: pl.Series, batch_size: int) -> None:
        self.numbers = numbers
        self.batch_size = batch_size
        self.parts: dict[str, list[pl.DataFrame]] = {}

    def add(self, batch: Batch) -> None:
        policies, months = batch.stop - batch.start, batch.grids.shape[-1]
        batches = np.arange(batch.start, batch.stop, dtype=np.int64) // self.batch_size
        keys = {
            "Policy_Number": np.repeat(self.numbers[batch.start : batch.stop].to_numpy(), months),
            "Projection_Step": np.tile(np.arange(months, dtype=np.int64), policies),
            "Batch_Index": np.repeat(batches, months),
        }
        for g, label in enumerate(batch.columns):
            frame = pl.DataFrame({**keys, label.split("@")[0]: batch.grids[0, g].reshape(-1)})
            self.parts.setdefault(label, []).append(frame)

    def dumps(self) -> dict[str, pl.DataFrame]:
        frames = {label: pl.concat(parts) for label, parts in self.parts.items()}
        dumps = {"projection__" + label.replace("@", "__"): f for label, f in frames.items()}
        return dumps


class ProductDiagnostics:
    def projection_recorder(self, numbers: pl.Series, batch_size: int) -> ProjectionRecorder:
        return ProjectionRecorder(numbers, batch_size)

    def assumption_dumps(
        self,
        assumptions: Mapping[str, TabularAssumption],
        parameters: ProductParameters,
        inputs: ResolvedInputs,
        config: PreparationConfig,
    ) -> dict[str, pl.DataFrame]:
        return {}

    def preparation_dumps(
        self,
        points: ModelPoints[pl.DataFrame],
        scenarios: ScenarioSet,
        config: PreparationConfig,
        batch_size: int,
    ) -> dict[str, pl.DataFrame]:
        return {}
