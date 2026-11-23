"""Float64 IFRS measurement and recognition; policy/month arrays only, no definition layer."""

import numpy as np

from avk.model.measures.stress import Array


def pv(cashflow: Array, rates: Array, *, start: bool = False) -> Array:
    """End-of-month remaining PV, with start- or end-of-month cashflow timing.

    Inputs contain the zero valuation instant. The last result is zero. Rates may be
    shared (M,) or policy-specific (N,M); no mutation of kernel-owned arrays.
    """
    result = np.zeros_like(cashflow)
    carry = np.zeros(cashflow.shape[0])
    for t in range(cashflow.shape[-1] - 1, -1, -1):
        rate = rates[..., t]
        carry = (
            cashflow[:, t] + carry / (1 + rate) if start else (cashflow[:, t] + carry) / (1 + rate)
        )
        if t:
            result[:, t - 1] = carry
    return result


def measurement(
    grid: dict[str, Array], current: Array, locked: Array, ratio: float, ri_ratio: float
) -> dict[str, Array]:
    premium, claim = grid["premiums"], grid["claims"]
    acquisition, maintenance = grid["acquisition"], grid["maintenance"]
    ri_premium, recovery = grid["ri_premiums"], grid["ri_recoveries"]
    expenses = acquisition + maintenance
    result = {
        "premiums": premium,
        "claims": claim,
        "acquisition": acquisition,
        "maintenance": maintenance,
        "claim_expense": grid["claim_expense"],
        "coverage_units": grid["coverage"],
        "ri_premiums": ri_premium,
        "ri_recoveries": recovery,
        "fulfilment_cashflow": claim + expenses + grid["claim_expense"] - premium,
        "ri_cashflow": ri_premium - recovery,
    }
    for basis, rates in (("current", current), ("locked", locked)):
        claims = pv(claim, rates)
        result[f"bel_{basis}"] = pv(claim + grid["claim_expense"], rates) + pv(
            expenses - premium, rates, start=True
        )
        result[f"ra_{basis}"] = ratio * claims
        result[f"ri_bel_{basis}"] = pv(ri_premium - recovery, rates)
        result[f"ri_ra_{basis}"] = ri_ratio * pv(recovery, rates)
    result.update(
        {
            "pv_claims": pv(claim, locked),
            "pv_premiums": pv(premium, locked, start=True),
            "pv_acquisition": pv(acquisition, locked, start=True),
            "pv_maintenance": pv(maintenance, locked, start=True),
            "pv_recoveries": pv(recovery, locked),
            "pv_coverage_units": pv(grid["coverage"], locked),
        }
    )
    return result


def recognition(
    bel: Array,
    ra: Array,
    ri_bel: Array,
    ri_ra: Array,
    claims: Array,
    recoveries: Array,
    growth: Array,
) -> dict[str, Array]:
    fcf = bel + ra
    loss = np.maximum(fcf, 0.0)
    # No claims means no loss recovery; the proportion is bounded to actual expected cover.
    fraction = np.divide(recoveries, claims, out=np.zeros_like(claims), where=claims > 0)
    recovery = loss * np.clip(fraction, 0.0, 1.0)
    csm = np.maximum(-fcf, 0.0)
    # IFRS 17 65(d)/66A: loss-recovery income adjusts signed-cost held CSM.
    ri_csm = ri_bel + ri_ra + recovery
    return {
        "recognition_bel": bel,
        "recognition_ra": ra,
        "recognition_fcf": fcf,
        "csm_at_recognition": csm,
        "loss_component": loss,
        "csm_interest": csm * (growth - 1.0),
        "ri_csm_at_recognition": ri_csm,
        "loss_recovery_component": recovery,
        "ri_csm_interest": ri_csm * (growth - 1.0),
    }
