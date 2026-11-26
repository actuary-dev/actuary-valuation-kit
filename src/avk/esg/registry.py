"""Select the scenario source named by the run file's `Inputs: Scenarios:`."""

from collections.abc import Sequence
from pathlib import Path

from avk.assumptions.context import ScenarioVariable
from avk.esg.base import EconomicScenarioGenerator
from avk.esg.deterministic import DeterministicCurveESG
from avk.esg.multi_asset import MultiAssetLognormalESG
from avk.esg.supplied import SuppliedScenarios
from avk.inputs.registry import Location
from avk.runtime.errors import InputError

DEFAULT = "DeterministicCurveESG"
GENERATORS: dict[str, type[DeterministicCurveESG] | type[MultiAssetLognormalESG]] = {
    DEFAULT: DeterministicCurveESG,
    MultiAssetLognormalESG.__name__: MultiAssetLognormalESG,
}


def generator_for(
    location: Location | None, variables: Sequence[ScenarioVariable], *, base: Path | None = None
) -> EconomicScenarioGenerator:
    """A source for the product's declared variables: `None` selects the default generator;
    `Source: parquet` reads a supplied scenario file, relative to `base` (the run file's
    folder)."""
    if location is None:
        return DeterministicCurveESG(variables)
    if location.source == "parquet":
        assert location.path is not None  # required for file sources by `Location`
        path = Path(location.path)
        path = path if path.is_absolute() or base is None else base / path
        return SuppliedScenarios(path, variables, location.settings)
    if location.source != "generator":
        raise InputError(f"Scenario source {location.source!r} is not yet supported")
    name = location.generator
    if name is None or name not in GENERATORS:
        raise InputError(f"Unknown scenario generator: {name}")
    cls = GENERATORS[name]
    if cls.SETTINGS:
        unknown = set(location.settings) - cls.SETTINGS
        if unknown:
            raise InputError(f"{name}: unknown Settings {sorted(unknown)}")
    return cls(variables, location.settings, base=base)
