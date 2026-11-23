"""Interest and the net cashflow: what a reserve has to fund, from the family's ports.

Items are positive
amounts; the net cashflow is outgo less income, so it is **positive when outgo exceeds
income**. Month 0 is the valuation instant and carries no cashflow.
"""

from avk.model.lang import Component, by_basis, on, scen


class ValuationInterest(Component):
    """The basis's monthly interest rate: the valuation rate of interest (VROI) on the
    reserving basis, the expected return on investments (ROI) on best estimate."""

    interest_rate = by_basis(reserving=scen("vroi"), be=scen("roi"))


class NetCashflows(ValuationInterest):
    """Interest on the month's opening cashflows, and the net outgo the reserve funds."""

    REQUIRES = (
        "premium_income",
        "acquisition_cost",
        "expense_outgo",
        "claim_expenses",
        "benefit_outgo",
        "reins_premiums",
    )

    def interest_earning_cashflow(self, t):
        """The month's cashflow that earns interest: premiums less acquisition costs and
        maintenance expenses, all paid at the start of the month (claims are paid at its end
        and earn none)."""
        return self.premium_income(t) - self.acquisition_cost(t) - self.expense_outgo(t)

    @on("be", overrides="interest_earning_cashflow")
    def interest_earning_cashflow_be(self, t):
        """Best estimate: reinsurance premiums, paid at the start, also reduce it."""
        return (
            self.premium_income(t)
            - self.acquisition_cost(t)
            - self.expense_outgo(t)
            - self.reins_premiums(t)
        )

    def interest_on_cashflows(self, t):
        """A month's interest on the interest-earning cashflow, at the basis's rate."""
        return self.interest_earning_cashflow(t) * self.interest_rate[t] * (t > 0)

    def net_cashflows(self, t):
        """Outgo less income, interest included: positive when the reserve pays out."""
        return -(
            self.premium_income(t)
            - self.acquisition_cost(t)
            - self.expense_outgo(t)
            - self.claim_expenses(t)
            - self.benefit_outgo(t)
            + self.interest_on_cashflows(t)
        ) * (t > 0)
