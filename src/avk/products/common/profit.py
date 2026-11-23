"""The profit signature on the best-estimate basis: emerging profit before and after tax and
the cost of holding solvency capital.

Best-estimate profit is calculated in three steps:

    profit before tax = BE net cashflow - increase in reserves + interest on the reserve
    net profit before SM = profit before tax - profit transfer - tax
    net profit after SM  = net profit before SM - cost of capital

The BE net cashflow is **income positive** (the reserving net cashflow flips the sign) and
includes reinsurance. The reserve held is the reserving basis's net reserve per policy, scaled
to the best-estimate lives. Every column reads the best-estimate basis explicitly, so the chain
is computed once, not once per basis.
"""

from avk.model.lang import Component, at_basis, param, prev, scen


class ProfitRates(Component):
    """The rates the profit chain earns and pays: the expected return on investments (ROI),
    the profit transfer and tax on profit."""

    expected_return = scen("roi")
    profit_transfer_rate = param("profit_transfer_rate")
    tax_rate = param("Tax Rate")


class ProfitSignature(ProfitRates):
    """Emerging profit on the best-estimate basis, for the projected lives."""

    REQUIRES = (
        "net_cashflows",
        "reins_premiums",
        "reins_recoveries",
        "net_reserve_pp",
        "lives_end",
        "maturities",
        "increase_in_solvency_capital",
        "interest_on_solvency_capital",
    )

    def be_net_cf(self, t):
        """Income less outgo, interest included, net of reinsurance: premiums ceded reduce
        it and recoveries add to it."""
        return (
            -at_basis("be", self.net_cashflows)(t)
            - at_basis("be", self.reins_premiums)(t)
            + at_basis("be", self.reins_recoveries)(t)
        ) * (t > 0)

    def be_reserves(self, t):
        """The reserve held for the best-estimate lives at the end of the month: the net
        reserve per policy times the lives it is held for, never negative; none at the
        valuation instant."""
        return max(
            at_basis("reserving", self.net_reserve_pp)(t)
            * (at_basis("be", self.lives_end)(t) + at_basis("be", self.maturities)(t)),
            0.0,
        ) * (t > 0)

    def increase_in_reserves(self, t):
        """This month's reserve less last month's."""
        return self.be_reserves(t) - prev(self.be_reserves, 0.0)

    def interest_on_reserves(self, t):
        """Interest earned on the reserve held at the start of the month."""
        return prev(self.be_reserves, 0.0) * self.expected_return[t] * (t > 0)

    def profit_before_tax(self, t):
        """The month's emerging profit before the profit transfer and tax."""
        return self.be_net_cf(t) - self.increase_in_reserves(t) + self.interest_on_reserves(t)

    def profit_transfer(self, t):
        """The transfer to the contingency reserve, deducted before tax."""
        return self.profit_before_tax(t) * self.profit_transfer_rate * (t > 0)

    def tax(self, t):
        """Tax on the profit after the profit transfer."""
        return (self.profit_before_tax(t) - self.profit_transfer(t)) * self.tax_rate * (t > 0)

    def net_profit_before_sm(self, t):
        """Profit after the profit transfer and tax, before the cost of solvency capital."""
        return self.profit_before_tax(t) - self.profit_transfer(t) - self.tax(t)

    def cost_of_capital(self, t):
        """Capital less its interest, plus tax and profit transfer
        on that interest. Only the profit transfer term is masked at month 0."""
        return (
            self.increase_in_solvency_capital(t)
            - self.interest_on_solvency_capital(t)
            + self.interest_on_solvency_capital(t) * self.tax_rate
            + self.interest_on_solvency_capital(t) * self.profit_transfer_rate * (t > 0)
        )

    def net_profit_after_sm(self, t):
        """Profit after the cost of holding solvency capital."""
        return self.net_profit_before_sm(t) - self.cost_of_capital(t)
