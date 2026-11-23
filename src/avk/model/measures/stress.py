"""Batch stress measures over float64 policy/month grids; no input-layer objects."""

import numpy as np
import numpy.typing as npt

Array = npt.NDArray[np.float64]


def combine(stack: Array, correlation: Array, floor: float) -> dict[str, Array]:
    """Last axis holds aligned risks; preserve the shortcut's undefined tails."""
    quadratic = np.einsum("...i,ij,...j->...", stack, correlation, stack)
    diversified = np.sqrt(np.maximum(quadratic, 0.0))
    return {
        "diversified": diversified,
        "combined": np.maximum(diversified, floor * stack.sum(axis=-1)),
    }


def operational(premiums: Array, bel: Array, premium_charge: float, bel_charge: float) -> Array:
    """Operational risk: the larger of a premium charge and a technical-provision charge.

    `bel` is the model net-cashflow present value, income positive (`mcev.bel`), so the
    liability is `-bel` and only a liability attracts the provision charge.
    """
    rolling = np.cumsum(premiums, axis=-1)
    rolling[..., 12:] = rolling[..., 12:] - rolling[..., :-12]
    return np.maximum(premium_charge * rolling, bel_charge * np.maximum(0.0, -np.nan_to_num(bel)))


def cost_and_pv(total: Array, rates: Array, annual_rate: float, loading: float) -> dict[str, Array]:
    cost = total * annual_rate * loading / 12.0
    discounted = np.zeros_like(cost)
    carry = np.zeros_like(cost[..., 0])
    for t in range(cost.shape[-1] - 1, -1, -1):
        carry = (carry + np.nan_to_num(cost[..., t])) / (1.0 + rates[..., t])
        if t > 0:
            discounted[..., t - 1] = carry
    return {"cost_of_capital": cost, "pv_cost_of_capital": discounted}


def revaluation(base_bel: Array, stressed_bel: Array, inforce: Array) -> Array:
    return np.maximum(np.nan_to_num(stressed_bel) - np.nan_to_num(base_bel), 0.0) * inforce


def immediate(benefit: Array, base_bel: Array, inforce: Array, factor: float) -> Array:
    return factor * np.maximum(benefit - np.nan_to_num(base_bel), 0.0) * inforce
