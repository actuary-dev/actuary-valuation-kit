"""The unit-linked profit signature on the best-estimate basis and its segment split.

The chain mirrors the shared `ProfitSignature` without reinsurance:

    profit before tax = BE net cashflow - increase in reserves + interest on the reserve
    net profit before SM = profit before tax - profit transfer - tax
    net profit after SM  = net profit before SM - cost of capital

The BE net cashflow is the general fund's, income positive. The reserve is the reserving
basis's non-unit reserve per policy held for the best-estimate lives; the unit reserve
belongs to the unit segment, whose profit (unit inflows less unit outflows less the increase
in the unit reserve) must be nil. Profit columns read the best-estimate basis explicitly, so
each is computed once.
"""

from avk.model.lang import Component, at_basis, param, prev, scen


class UnitLinkedProfitRates(Component):
    """The rates the profit chain earns and pays: the expected return on investments,
    the profit transfer and tax on profit."""

    expected_return = scen("roi")
    profit_transfer_rate = param("profit_transfer_rate")
    tax_rate = param("Tax Rate")


class UnitSegmentProfit(Component):
    """The unit segment's movement on each basis: policyholders' money passing through."""

    REQUIRES = (
        "A_begin",
        "addition_outgo",
        "admin_income",
        "allocated_premiums",
        "charges_end",
        "dpf_credited_return",
        "fund_growth_total",
        "gc_income",
        "mc_income",
        "partial_withdrawal_outgo",
        "rpu_growth_total",
        "unit_exit_benefits",
        "unit_reserve",
    )

    def unit_fund_growth(self, t):
        """Investment return credited to the active and paid-up slots."""
        return self.A_begin(t) * self.fund_growth_total(t) + self.rpu_growth_total(t)

    def unit_charges_deducted(self, t):
        """Charges taken from the units: administration, mortality and guarantee charges,
        fund management charges on every state and discontinuance charges."""
        return self.admin_income(t) + self.mc_income(t) + self.gc_income(t) + self.charges_end(t)

    def increase_in_unit_reserve(self, t):
        """This month's unit reserve less last month's; none at the valuation instant."""
        return (self.unit_reserve(t) - prev(self.unit_reserve, 0.0)) * (t > 0)

    def unit_segment_profit(self, t):
        """Allocated premium, additions and investment return credited, less charges,
        unit-funded benefits and withdrawals, less the increase in the unit reserve."""
        return (
            self.allocated_premiums(t)
            + self.addition_outgo(t)
            + self.unit_fund_growth(t)
            + self.dpf_credited_return(t)
            - self.unit_charges_deducted(t)
            - self.unit_exit_benefits(t)
            - self.partial_withdrawal_outgo(t)
            - self.increase_in_unit_reserve(t)
        ) * (t > 0)


class UnitLinkedProfit(UnitLinkedProfitRates):
    """Emerging profit on the best-estimate basis, for the projected lives."""

    REQUIRES = (
        "increase_in_solvency_capital",
        "interest_on_solvency_capital",
        "lives_end",
        "maturities",
        "net_cashflows",
        "non_unit_reserve_pp",
        "unit_segment_profit",
    )

    def be_net_cf(self, t):
        """The general fund's income less outgo, interest included."""
        return -at_basis("be", self.net_cashflows)(t) * (t > 0)

    def be_reserves(self, t):
        """The non-unit reserve held for the best-estimate lives at the end of the month:
        the reserving basis's reserve per policy times those lives; none at the valuation
        instant."""
        return max(
            at_basis("reserving", self.non_unit_reserve_pp)(t)
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
        """Best-estimate capital increase less its interest, plus the tax and profit
        transfer on that interest."""
        return (
            at_basis("be", self.increase_in_solvency_capital)(t)
            - at_basis("be", self.interest_on_solvency_capital)(t)
            + at_basis("be", self.interest_on_solvency_capital)(t) * self.tax_rate
            + at_basis("be", self.interest_on_solvency_capital)(t)
            * self.profit_transfer_rate
            * (t > 0)
        )

    def net_profit_after_sm(self, t):
        """Profit after the cost of holding solvency capital."""
        return self.net_profit_before_sm(t) - self.cost_of_capital(t)

    def non_unit_segment_profit(self, t):
        """The non-unit (general fund) segment's profit: the profit before tax."""
        return self.profit_before_tax(t)

    def total_profit(self, t):
        """Unit plus non-unit segment profit on the best-estimate basis."""
        return at_basis("be", self.unit_segment_profit)(t) + self.non_unit_segment_profit(t)
