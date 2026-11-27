"""Fixed-order reductions of portfolio values across economic scenarios."""

import math
from collections.abc import Sequence
from typing import Literal

import numpy as np
import numpy.typing as npt

from avk.model.data import ScenarioSet

type FloatArray = npt.NDArray[np.float64]
type Tail = Literal["upper", "lower"]


def _cumulative_mass(weights: FloatArray) -> FloatArray:
    """Compensated prefix sums keep roundoff from moving a quantile across a path."""
    cumulative = np.empty_like(weights)
    total = np.zeros(weights.shape[1])
    correction = np.zeros_like(total)
    for index, weight in enumerate(weights):
        adjusted = weight - correction
        updated = total + adjusted
        correction = (updated - total) - adjusted
        total = updated
        cumulative[index] = total
    return cumulative


def summarize(
    values: FloatArray,
    weights: FloatArray,
    percentiles: Sequence[float],
    cte_levels: Sequence[float],
    tail: Tail,
) -> FloatArray:
    """Return mean, inverse-CDF quantiles and CTE for each step of an (S, M) array."""
    positive = weights > 0
    values = values[positive]
    weights = weights[positive] / math.fsum(weights[positive])
    valid = np.isfinite(values).all(axis=0)
    # Fill invalid steps for the calculation and restore them as missing at the end.
    values[:, ~valid] = 0
    mean = np.add.reduce(values * weights[:, None], axis=0)
    results = [mean]
    if percentiles or cte_levels:
        order = np.argsort(values, axis=0, kind="stable")
        sorted_values = np.take_along_axis(values, order, axis=0)
        sorted_weights = weights[order]
        if percentiles:
            cumulative = _cumulative_mass(sorted_weights)
            cumulative[-1] = 1.0
            steps = np.arange(values.shape[1])
            for level in percentiles:
                index = -1 if level == 1 else (cumulative >= level).argmax(axis=0)
                results.append(sorted_values[index, steps])

        if cte_levels:
            if tail == "upper":
                # Accumulate from the upper endpoint so small tails avoid subtraction
                # from probabilities near one.
                sorted_values = sorted_values[::-1]
                sorted_weights = sorted_weights[::-1]
            prior_mass = np.empty_like(sorted_weights)
            prior_mass[0] = 0
            prior_mass[1:] = _cumulative_mass(sorted_weights[:-1])
            for level in cte_levels:
                if level == 0:
                    results.append(mean)
                else:
                    mass = 1 - level
                    taken = np.minimum(sorted_weights, np.maximum(mass - prior_mass, 0))
                    results.append(np.add.reduce(sorted_values * (taken / mass), axis=0))
    result = np.stack(results)
    result[:, ~valid] = np.nan
    return result


def tvog(scenarios: ScenarioSet, path_values: npt.ArrayLike, certainty_equivalent: float) -> float:
    """Weighted risk-neutral present value less the deterministic reference-forward value.

    Supply one PV per scenario in `scenarios.ids` order. Use the same portfolio,
    quantity, valuation step and non-economic assumptions for both projections.
    """
    if scenarios.measure != "risk_neutral":
        raise ValueError("TVOG requires risk_neutral scenarios")
    values = np.asarray(path_values, dtype=np.float64)
    if values.shape != scenarios.weights.shape:
        raise ValueError("TVOG requires one present value per scenario")
    mean = float(summarize(values[:, None], scenarios.weights, (), (), "upper")[0, 0])
    if not math.isfinite(mean) or not math.isfinite(certainty_equivalent):
        raise ValueError("TVOG requires a finite reference PV and finite positive-weight path PVs")
    return mean - certainty_equivalent
