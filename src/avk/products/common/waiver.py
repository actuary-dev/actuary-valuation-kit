"""Waiver entitlement and its standalone outgo adapter.

The entitlement consumes a term-masked claimant stock and eligible base premium.
Premium due includes the rider row's payment-term stop. An embedded adapter
would reduce premium_income by waiver_entitlement instead of adding wop_benefit
to benefit_outgo; it must override the host premium owner and retain one lives owner.
That embedded adapter is design only, pending its approved specification/oracle.
"""

from avk.model.lang import Component, prev


class WaiverOfPremiumEntitlement(Component):
    """Previous month's eligible claimant stock times the premium due this month."""

    REQUIRES = ("claim_stock", "base_premium_due")

    def waiver_entitlement(self, t):
        """Waived premium; base_premium_due owns step, term and payment masks."""
        return prev(self.claim_stock, 0.0) * self.base_premium_due(t)


class StandaloneWaiverAdapter(Component):
    """Expose the entitlement as standalone rider outgo for the benefit port."""

    REQUIRES = ("waiver_entitlement",)

    def wop_benefit(self, t):
        """Standalone waiver benefit, added to the event benefit by the product."""
        return self.waiver_entitlement(t)
