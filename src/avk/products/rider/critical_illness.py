"""Standalone CI composition; generic claim-stock/event/waiver ports also serve TPD.

RiderBase owns shared rates, premiums, reserves, reinsurance and IFRS discounting.
ClaimStockTransition extends the single LivesAndExits. No Rider_Option branch.
"""

from avk.model.lang import Component, RiderProduct, at_basis, if_, override
from avk.products.common.claim_stock import ClaimStockTransition, EventBenefit
from avk.products.common.ifrs17 import IfrsMeasurement
from avk.products.common.profit import ProfitSignature
from avk.products.common.waiver import StandaloneWaiverAdapter, WaiverOfPremiumEntitlement
from avk.products.rider.formulas import (
    AccidentalDeath,
    RiderBase,
    RiderCashflows,
    RiderIfrsBel,
    RiderMcev,
    RiderReserves,
)


class CriticalIllnessIncidence(Component):
    """Bind generic incidence to factory-selected Critical illness morbidity."""

    REQUIRES = (
        "morbidity_monthly",
        "lives_end",
        "maturities",
        "claim_stock",
        "sum_assured",
        "base_premium_due",
    )

    def incidence_rate(self, t):
        """CI incidence rate; the factory selects the table columns before compilation."""
        return self.morbidity_monthly(t)

    def coverage_units(self, t):
        """Own lump sum and contractual waiver cover on active best-estimate lives."""
        return (
            (self.sum_assured(t) + self.base_premium_due(t))
            * at_basis("be", self.lives_end)(t)
            * (t > 0)
        )


class ClaimantCashflows(RiderCashflows):
    """Cashflows for a standalone incidence rider with ongoing claimant expenses/waiver."""

    REQUIRES = (*RiderCashflows.REQUIRES, "claim_stock", "event_benefit", "wop_benefit", "npv_wop")

    @override
    def benefit_outgo(self, t):
        """Lump-sum incidence benefit plus waived base premiums as rider outgo."""
        return self.event_benefit(t) + self.wop_benefit(t)

    def reinsured_benefit(self, t):
        """Cover includes the lump sum and the remaining waiver premium PV."""
        return self.sum_assured(t) + self.npv_wop(t)

    @override
    def renewal_expenses(self, t):
        """Rider renewal expense on active opening lives plus current claimant stock."""
        return (
            (
                ((self.policy.renewal_fixed_expense + self.expense_add[t]) * self.expense_mult[t])
                + self.policy.renewal_percent_prem_expense_rate
                * self.expense_mult[t]
                * self.policy.Premium_Amount
                * if_(
                    self.renewal_premium_expense_after_payment_term,
                    1.0,
                    self.policy_month(t) <= self.policy.Premium_Payment_Term * 12,
                )
            )
            / 12
            * self.inflation_factor(t)
            * (1 + self.mad_expense)
            * (self.lives_begin(t) + self.claim_stock(t))
            * (self.policy_year(t) > 1)
        )


class ClaimantReserves(RiderReserves):
    """Shared reserve discounting, with claimant stock in both reserve denominators."""

    REQUIRES = (*RiderReserves.REQUIRES, "claim_stock")

    @override
    def eligible_reserve_lives(self, t):
        """Active, maturing and claimant lives with no book denominator floor."""
        return self.lives_end(t) + self.maturities(t) + self.claim_stock(t)

    @override
    def reserve_lives(self, t):
        """Active, maturing and claimant lives, floored for prospective reserves."""
        return max(self.lives_end(t) + self.maturities(t) + self.claim_stock(t), 1e-6)


class ClaimantProfit(ProfitSignature):
    """Scale the reserving net reserve to active and claimant BE lives."""

    REQUIRES = (*ProfitSignature.REQUIRES, "claim_stock")

    @override
    def be_reserves(self, t):
        """Reserve held for active, maturing and claimant BE lives; none at step zero."""
        return max(
            at_basis("reserving", self.net_reserve_pp)(t)
            * (
                at_basis("be", self.lives_end)(t)
                + at_basis("be", self.maturities)(t)
                + at_basis("be", self.claim_stock)(t)
            ),
            0.0,
        ) * (t > 0)


class ClaimantMcev(RiderMcev):
    """Keep rider MCEV/FCC and include claimants in the unfloored BEL denominator."""

    REQUIRES = (*RiderMcev.REQUIRES, "claim_stock")

    @override
    def bel_pp(self, t):
        """BEL per active/claimant life; retain IEEE NaN once no covered life remains."""
        return -self.bel(t) / (
            at_basis("be", self.lives_end)(t)
            + at_basis("be", self.maturities)(t)
            + at_basis("be", self.claim_stock)(t)
        )


class ClaimantIfrsBel(RiderIfrsBel):
    """Reuse IFRS BEL and its own onerous curve with claimant-aware scaling."""

    REQUIRES = (*RiderIfrsBel.REQUIRES, "claim_stock")

    @override
    def ifrs_bel_pp(self, t):
        """IFRS BEL per active/claimant life, with the target's unfloored denominator."""
        return self.ifrs_bel(t) / (
            at_basis("be", self.lives_end)(t)
            + at_basis("be", self.maturities)(t)
            + at_basis("be", self.claim_stock)(t)
        )


class CriticalIllness(
    CriticalIllnessIncidence,
    ClaimStockTransition,
    EventBenefit,
    WaiverOfPremiumEntitlement,
    StandaloneWaiverAdapter,
    ClaimantCashflows,
    ClaimantReserves,
    ClaimantProfit,
    ClaimantMcev,
    ClaimantIfrsBel,
    RiderBase,
    RiderProduct,
):
    CODE, LABEL, BASES = "CRITICAL_ILLNESS_RIDER", "Critical illness rider", ("reserving", "be")
    FIELDS = AccidentalDeath.FIELDS


class IfrsCriticalIllness(IfrsMeasurement, CriticalIllness):
    """CI plus the shared IFRS measurement adapters."""
