"""Economic scenarios are prepared separately from the liability calculator."""

from abc import ABC, abstractmethod
from collections.abc import Mapping

from avk.assumptions.models import InterestCurveAssumption
from avk.model.data import ScenarioSet


class EconomicScenarioGenerator(ABC):
    @abstractmethod
    def generate(
        self, curves: Mapping[str, InterestCurveAssumption], horizon: int
    ) -> ScenarioSet: ...
