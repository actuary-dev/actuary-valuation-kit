"""Canonical numeric input data; no loading or validation-framework dependencies."""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True)
class Axis:
    name: str
    kind: Literal["int", "keymap"]
    start: int | None
    size: int
    below: Literal["error", "clamp", "zero_rows"] | None
    above: Literal["error", "clamp", "zero"]
    keys: tuple[str | int | float, ...]
    unknown: Literal["error", "first"] | None


@dataclass(frozen=True)
class Table:
    name: str
    axes: tuple[Axis, ...]
    values: npt.NDArray[np.float64]
    source: Mapping[str, str]

    def __post_init__(self) -> None:
        values = np.array(self.values, dtype=np.float64, order="C", copy=True)
        if values.shape != tuple(axis.size for axis in self.axes):
            raise ValueError(f"{self.name}: array shape does not match axes")
        values.flags.writeable = False
        object.__setattr__(self, "values", values)


@dataclass(frozen=True)
class ModelPoints[FrameT]:
    """Prepared frame owned by the input layer; arrays are lowered before execution."""

    frame: FrameT
    fields: tuple[str, ...]


@dataclass(frozen=True)
class ScenarioSet:
    """Economic variables `(S, M)` by name; scenario ids, weights and, for generated paths,
    the seed of each (empty for the deterministic path); the measure; provenance."""

    variables: Mapping[str, npt.NDArray[np.float64]]
    ids: tuple[str, ...]
    weights: npt.NDArray[np.float64]
    measure: str
    provenance: Mapping[str, str]
    seeds: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        variables = {}
        shape = None
        for name, value in self.variables.items():
            array = np.array(value, dtype=np.float64, order="C", copy=True)
            if array.ndim != 2 or not np.isfinite(array).all():
                raise ValueError(f"{name}: scenarios need finite (S, M) arrays")
            if shape is not None and array.shape != shape:
                raise ValueError("Scenario variables must share a shape")
            shape = array.shape
            array.flags.writeable = False
            variables[name] = array
        weights = np.array(self.weights, dtype=np.float64, copy=True)
        if (
            shape is None
            or not all(shape)
            or len(self.ids) != shape[0]
            or len(set(self.ids)) != len(self.ids)
        ):
            raise ValueError("Scenario ids must be unique and match nonempty arrays")
        if self.seeds and len(self.seeds) != shape[0]:
            raise ValueError("Scenario seeds, when given, are one per scenario")
        object.__setattr__(self, "seeds", tuple(int(seed) for seed in self.seeds))
        if (
            weights.shape != (shape[0],)
            or not np.isfinite(weights).all()
            or (weights < 0).any()
            or not np.isclose(weights.sum(), 1)
        ):
            raise ValueError("Scenario weights must be finite, nonnegative and sum to one")
        weights.flags.writeable = False
        object.__setattr__(self, "variables", MappingProxyType(variables))
        object.__setattr__(self, "weights", weights)
        object.__setattr__(self, "provenance", MappingProxyType(dict(self.provenance)))
