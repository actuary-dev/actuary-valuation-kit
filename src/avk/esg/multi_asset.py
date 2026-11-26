"""Correlated monthly lognormal scenarios built on product-declared interest curves."""

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

import numpy as np
import numpy.typing as npt
import polars as pl

from avk.assumptions.context import ScenarioVariable
from avk.assumptions.models import InterestCurveAssumption
from avk.esg.base import EconomicScenarioGenerator
from avk.esg.deterministic import DeterministicCurveESG, placed_months
from avk.inputs.formats import FormatSpec, read
from avk.inputs.public_formats import exact, numbers
from avk.model.data import ScenarioSet
from avk.runtime.errors import InputError, reader_failure
from avk.runtime.progress import fingerprint

_REQUIRED = frozenset({"Scenarios", "Seed", "Measure", "Assets", "Correlations"})
_SETTINGS = _REQUIRED | {"Risk_Free", "Antithetic"}


@dataclass(frozen=True)
class AssetModel:
    variable: str
    volatility: float


@dataclass(frozen=True)
class MultiAssetSettings:
    scenarios: int
    seed: int
    measure: Literal["real_world", "risk_neutral"]
    assets: tuple[AssetModel, ...]
    correlation: npt.NDArray[np.float64]
    risk_free: str | None
    antithetic: bool
    file_hashes: Mapping[str, str] = field(default_factory=dict, repr=False)

    @classmethod
    def parse(
        cls, settings: Mapping[str, Any], variables: Sequence[ScenarioVariable], base: Path | None
    ) -> "MultiAssetSettings":
        unknown = set(settings) - _SETTINGS
        if unknown:
            raise InputError(
                f"MultiAssetLognormalESG: unknown Settings {sorted(map(str, unknown))}"
            )
        missing = _REQUIRED - set(settings)
        if missing:
            raise InputError(f"MultiAssetLognormalESG: missing Settings {sorted(missing)}")
        scenarios = _integer(settings, "Scenarios", 1)
        seed = _integer(settings, "Seed", 0)
        measure = settings["Measure"]
        if measure not in ("real_world", "risk_neutral"):
            raise InputError("Measure must be real_world or risk_neutral")
        antithetic = settings.get("Antithetic", False)
        if not isinstance(antithetic, bool):
            raise InputError("Antithetic must be a Boolean")
        if antithetic and scenarios % 2:
            raise InputError("Scenarios must be even when Antithetic is true")
        declared = {variable.name for variable in variables}
        risk_free = settings.get("Risk_Free")
        if measure == "risk_neutral":
            if not isinstance(risk_free, str) or risk_free not in declared:
                raise InputError("Risk_Free must name a declared variable under risk_neutral")
        elif "Risk_Free" in settings:
            raise InputError("Risk_Free is allowed only under risk_neutral")

        asset_frame, asset_spec = _settings_csv(settings, "Assets", base, ("variable",))
        try:
            exact(asset_frame, ("variable", "volatility"), asset_spec)
            volatility = numbers(asset_frame, ("volatility",), asset_spec).ravel()
        except pl.exceptions.PolarsError as exc:
            raise InputError(
                f"Assets: invalid volatility column in {asset_spec.source['path']}"
            ) from exc
        if (volatility < 0).any():
            raise InputError("Assets: volatility must be nonnegative")
        names = asset_frame["variable"].to_list()
        if len(set(names)) != len(names):
            raise InputError("Assets: duplicate variable")
        undeclared = set(names) - declared
        if undeclared:
            raise InputError(f"Assets: undeclared variables {sorted(undeclared)}")
        if risk_free in names:
            raise InputError("Risk_Free must be a deterministic variable outside Assets")
        assets = tuple(
            AssetModel(name, float(sigma)) for name, sigma in zip(names, volatility, strict=True)
        )

        frame, spec = _settings_csv(settings, "Correlations", base, ("risk", "other"))
        table = read("avk_correlations_v1", frame, spec)
        labels = table.axes[0].keys
        if set(names) != set(labels):
            raise InputError(
                "Correlations must match Assets: "
                f"missing {sorted(set(names) - set(labels))}, "
                f"unexpected {sorted(set(labels) - set(names))}"
            )
        order = [labels.index(name) for name in names]
        correlation = table.values[np.ix_(order, order)]
        correlation.flags.writeable = False
        hashes = MappingProxyType({item.name: item.source["sha256"] for item in (asset_spec, spec)})
        return cls(scenarios, seed, measure, assets, correlation, risk_free, antithetic, hashes)


def _integer(settings: Mapping[str, Any], name: str, minimum: int) -> int:
    value = settings[name]
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise InputError(f"{name} must be an integer >= {minimum}")
    return value


def _settings_csv(
    settings: Mapping[str, Any], name: str, base: Path | None, labels: tuple[str, ...]
) -> tuple[pl.DataFrame, FormatSpec]:
    value = settings[name]
    if not isinstance(value, str) or not value:
        raise InputError(f"{name} must name a CSV file")
    path = Path(value)
    if base is not None and not path.is_absolute():
        path = base / path
    try:
        data = path.read_bytes()
        frame = pl.read_csv(
            data, infer_schema_length=None, schema_overrides=dict.fromkeys(labels, pl.String)
        )
    except (OSError, ValueError, pl.exceptions.PolarsError) as exc:
        raise InputError(reader_failure(name, path, exc)) from exc
    digest = hashlib.sha256(data).hexdigest()
    fingerprint(path, digest)
    spec = FormatSpec(
        name,
        {"path": str(path), "sha256": digest},
        (),
        (),
        "",
        0,
        "mixed",
    )
    return frame, spec


class MultiAssetLognormalESG(EconomicScenarioGenerator):
    """Simulate independent monthly shocks with cross-asset correlation."""

    SETTINGS = _SETTINGS

    def __init__(
        self,
        variables: Sequence[ScenarioVariable],
        settings: Mapping[str, Any],
        *,
        base: Path | None,
    ) -> None:
        self.baseline = DeterministicCurveESG(variables)
        self.settings = MultiAssetSettings.parse(settings, variables, base)
        self.provenance = {
            "generator": type(self).__name__,
            "version": "1",
            "settings": json.dumps({"Antithetic": False, **settings}, sort_keys=True),
            **{f"{name}.sha256": digest for name, digest in self.settings.file_hashes.items()},
        }

    def generate(self, curves: Mapping[str, InterestCurveAssumption], horizon: int) -> ScenarioSet:
        baseline = self.baseline.generate(curves, horizon)
        settings = self.settings
        names = tuple(asset.variable for asset in settings.assets)
        declarations = {variable.name: variable for variable in self.baseline.variables}
        active = np.column_stack(
            [
                placed_months(horizon, variable, curves[variable.curve].valuation_month)
                for variable in (declarations[name] for name in names)
            ]
        )[1:]
        placed = np.column_stack([baseline.variables[name][0, 1:] for name in names])
        drift = (
            placed
            if settings.risk_free is None
            else baseline.variables[settings.risk_free][0, 1:, None]
        )
        sigma = np.array([asset.volatility for asset in settings.assets]) / np.sqrt(12)
        root = _correlation_root(settings.correlation)
        paths = {
            name: np.repeat(values, settings.scenarios, axis=0)
            for name, values in baseline.variables.items()
        }
        pair_size = 2 if settings.antithetic else 1
        children = np.random.SeedSequence(settings.seed).spawn(settings.scenarios // pair_size)
        seeds = []
        with np.errstate(over="ignore", invalid="ignore"):
            center = np.log1p(drift) - sigma**2 / 2
            for pair, child in enumerate(children):
                rng = np.random.Generator(np.random.PCG64(child))
                # Each product has the same shape regardless of the path count.
                shocks = (rng.standard_normal(placed.shape) @ root.T) * sigma
                seed = int(child.generate_state(1, dtype=np.uint64)[0])
                for offset in range(pair_size):
                    if offset:
                        shocks = -shocks
                    rates = np.where(sigma == 0, drift, np.expm1(center + shocks))
                    rates = np.where(active, rates, placed)
                    for i, name in enumerate(names):
                        paths[name][pair * pair_size + offset, 1:] = rates[:, i]
                    seeds.append(seed)
        for name in names:
            if not np.isfinite(paths[name]).all() or (paths[name] <= -1).any():
                raise InputError(
                    f"Assets: {name} generated non-finite rates or rates at or below -1"
                )
        return ScenarioSet(
            paths,
            tuple(str(i) for i in range(1, settings.scenarios + 1)),
            np.full(settings.scenarios, 1 / settings.scenarios),
            settings.measure,
            {**baseline.provenance, **self.provenance},
            tuple(seeds),
        )


def _correlation_root(correlation: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    try:
        return np.linalg.cholesky(correlation)
    except np.linalg.LinAlgError:
        # The reader already checked PSD to its numerical tolerance.
        eigenvalues, eigenvectors = np.linalg.eigh(correlation)
        return eigenvectors * np.sqrt(eigenvalues.clip(min=0))
