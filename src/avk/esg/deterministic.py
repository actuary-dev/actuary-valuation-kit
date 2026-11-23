"""Single-path annual-effective interest conversion with product-declared timing."""

from collections.abc import Mapping, Sequence

import numpy as np
import numpy.typing as npt

from avk.assumptions.context import ScenarioVariable
from avk.assumptions.models import InterestCurveAssumption
from avk.esg.base import EconomicScenarioGenerator
from avk.model.data import ScenarioSet
from avk.runtime.errors import InputError


def _place(
    raw: npt.NDArray[np.float64], horizon: int, variable: ScenarioVariable, valuation_month: int
) -> npt.NDArray[np.float64]:
    """Apply a declared timing rule; see `ScenarioVariable`."""
    elapsed = 0
    if variable.fiscal_start_month == "fiscal_start_month":
        raise InputError(f"{variable.name}: unresolved fiscal_start_month")
    if variable.fiscal_start_month is not None:
        elapsed = (valuation_month - variable.fiscal_start_month) % 12
    result = np.zeros(horizon)
    if variable.timing == "fiscal_lead":
        if horizon - elapsed > 1:
            result[1 : horizon - elapsed] = raw[elapsed : horizon - 1]
        return result
    delay = variable.months - elapsed if variable.timing == "fiscal_lag" else variable.months
    if delay < 0:
        raise InputError(f"{variable.name}: timing places the rate before the valuation date")
    if delay < horizon:
        result[delay:] = raw[: horizon - delay]
    return result


class DeterministicCurveESG(EconomicScenarioGenerator):
    """One path: each declared variable is its curve's rate under the declared timing."""

    def __init__(self, variables: Sequence[ScenarioVariable]) -> None:
        if not variables:
            raise InputError("The product declares no scenario variables")
        self.variables = tuple(variables)

    def generate(self, curves: Mapping[str, InterestCurveAssumption], horizon: int) -> ScenarioSet:
        if horizon <= 0:
            raise InputError("Scenario horizon must be positive")
        monthly: dict[str, npt.NDArray[np.float64]] = {}
        variables = {}
        provenance = {"generator": type(self).__name__, "version": "1"}
        for variable in self.variables:
            if variable.curve not in curves:
                raise InputError(f"Scenario generator needs curve {variable.curve}")
            assumption = curves[variable.curve]
            if variable.curve not in monthly:
                monthly[variable.curve] = assumption.monthly(horizon)
                provenance[variable.curve] = assumption.table.source["sha256"]
            raw = monthly[variable.curve][:, assumption.column(variable.column)]
            placed = _place(raw, horizon, variable, assumption.valuation_month)
            variables[variable.name] = placed[None, :]
        return ScenarioSet(variables, ("deterministic",), np.ones(1), "deterministic", provenance)
