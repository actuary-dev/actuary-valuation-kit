"""Surplus (excess of retention) reinsurance: the ceded sum assured, premiums and recoveries.

The insurer keeps the retention limit plus
what the reserve already funds and cedes the rest, so the ceded amount falls as the reserve
builds up. The reserve used is last month's reserving-basis gross reserve on every basis: the
reinsurance in force during a month is set from the position at its start. In month 1 that is
the reserve held at the valuation date.
"""

from avk.model.lang import Component, at_basis, param, prev


class SurplusReinsurance(Component):
    """Cover above the retention limit, priced on the reinsurer's own death rate `reins_rate`."""

    REQUIRES = (
        "sum_assured",
        "reins_rate",
        "ceding_reserve_pp",
        "lives_begin",
        "deaths",
        "net_cashflows",
    )
    retention = param("Reinsurance Retention Limit abs")

    def reins_sum_assured(self, t):
        """Sum assured less the retention and last month's gross reserve, never negative."""
        return max(
            self.sum_assured(t)
            - self.retention
            - prev(at_basis("reserving", self.ceding_reserve_pp), 0.0),
            0.0,
        ) * (t > 0)

    def reins_premiums(self, t):
        """Premium to the reinsurer on the opening lives."""
        return self.reins_rate(t) * self.reins_sum_assured(t) * self.lives_begin(t) * (t > 0)

    def reins_recoveries(self, t):
        """The ceded sum assured, recovered on each death."""
        return self.reins_sum_assured(t) * self.deaths(t)

    def net_cf_with_reinsurance(self, t):
        """The reserving net cashflow plus reinsurance premiums less recoveries, on both bases."""
        return (
            at_basis("reserving", self.net_cashflows)(t)
            + self.reins_premiums(t)
            - self.reins_recoveries(t)
        ) * (t > 0)
