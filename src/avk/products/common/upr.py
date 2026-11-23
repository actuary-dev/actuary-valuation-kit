"""Unearned premium reserve for riders."""

from avk.model.lang import Component, if_


class UnearnedPremiumReserve(Component):
    """The retained half-month UPR floor, on the unmodified rider premium."""

    REQUIRES = ("policy_month", "term_months")

    def premium_period(self, t):
        """Months between instalments."""
        return 12 / self.policy.Premium_Frequency

    def upr_months_due(self, t):
        """The retained calendar-year remainder, including the year-end special case."""
        return if_(
            self.policy_month(t) % 12 == 0, self.premium_period(t), self.policy_month(t) % 12
        )

    def upr(self, t):
        """Unearned rider premium through half a month; zero at maturity and step zero."""
        return (
            max(
                0.0,
                self.policy.Premium_Amount
                * (self.premium_period(t) - self.upr_months_due(t) + 0.5)
                / self.premium_period(t),
            )
            * (t > 0)
            * (self.policy_month(t) < self.term_months(t))
        )
