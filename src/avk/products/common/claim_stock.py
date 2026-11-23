"""Incidence and surviving claimant stock for riders.

Bind incidence_rate at composition (CI/TPD select different morbidity columns).
The inherited LivesAndExits is the single lives owner. Its exits include incidence.
Stock deaths continue after maturity. The maturity mask applies to reported and
eligible stock.
"""

from avk.model.lang import Component, if_, override, prev
from avk.products.common.lives import LivesAndExits


class ClaimStockTransition(LivesAndExits):
    """Deaths, incidence, lapses, maturity; claimants die from opening stock only."""

    REQUIRES = (*LivesAndExits.REQUIRES, "incidence_rate", "policy_month", "term_months")

    def rider_event(self, t):
        """Incidence from active survivors of deaths, before lapses."""
        return (self.lives_begin(t) - self.deaths(t)) * self.incidence_rate(t) * (t > 0)

    @override
    def lapses(self, t):
        """Lapses from survivors of death and incidence."""
        return (self.lives_begin(t) - self.deaths(t) - self.rider_event(t)) * if_(
            t == 1 and self.policy_month(t) > 0 and self.case_mass_lapse > 0,
            self.w(t) + (1 - self.w(t)) * self.case_mass_lapse,
            self.w(t),
        )

    @override
    def maturities(self, t):
        """Maturity takes the active lives remaining after death, incidence and lapse."""
        return (
            self.lives_begin(t) - self.deaths(t) - self.rider_event(t) - self.lapses(t)
        ) * self.maturity(t)

    @override
    def lives_end(self, t):
        """Active closing lives, using the shared lives owner's opening state."""
        return max(
            self.lives_begin(t)
            - self.deaths(t)
            - self.rider_event(t)
            - self.lapses(t)
            - self.maturities(t),
            0.0,
        )

    def cumulative_claims(self, t):
        """Opening surviving stock plus new incidence, before this month's stock deaths."""
        return prev(self.claim_stock_state, 0.0) + self.rider_event(t)

    def stock_deaths(self, t):
        """Deaths from previous month's stock; new claimants cannot die this month."""
        return prev(self.claim_stock_state, 0.0) * self.q(t)

    def claim_stock_state(self, t):
        """Unmasked stock carried by the scan, including months after maturity."""
        return self.cumulative_claims(t) - self.stock_deaths(t)

    def claim_stock(self, t):
        """Reported stock, eligible only through the rider's term month."""
        return self.claim_stock_state(t) * (self.policy_month(t) <= self.term_months(t))


class EventBenefit(Component):
    """A lump sum on incidence; reusable with any rider_event and sum_assured ports."""

    REQUIRES = ("sum_assured", "rider_event")

    def event_benefit(self, t):
        """The event lump sum; the transition port owns the step-zero event mask."""
        return self.sum_assured(t) * self.rider_event(t)
