"""Commission and general-fund expenses on the lives of each basis.

Shocks follow Term: `expense_add` raises the fixed per-policy amounts and `expense_mult`
scales every expense. Renewal and claim expenses grow with the case's inflation from the
valuation date. The reserving basis loads every expense, but not commission, by
`1 + prudent_margin_expense`. Step 0 is the valuation instant and carries none.
"""

from avk.model.lang import Component, by_basis, param, prev, run_param
from avk.products.unit_linked.decrements import channel_table


class ExpenseShocks(Component):
    """Expense shock schedules and the inflation level, prepared by the run per case."""

    expense_add = run_param("expense_add", monthly=True)
    expense_mult = run_param("expense_mult", monthly=True)
    inflation_add = run_param("inflation_add")
    inflation_mult = run_param("inflation_mult")
    inflation_months = run_param("inflation_months", monthly=True)
    inflation = param("Inflation")

    def inflation_factor(self, t):
        """Expense escalation from month 1 to t: shocked months grow at the case rate."""
        return (1 + self.inflation) ** ((t - 1 - self.inflation_months[t]) / 12) * (
            1 + (self.inflation + self.inflation_add) * self.inflation_mult
        ) ** (self.inflation_months[t] / 12)


class UnitLinkedExpenses(ExpenseShocks):
    """Commission, initial, renewal, fund and claim expenses and the two expense ports."""

    REQUIRES = (
        "A_begin",
        "D_begin",
        "R_begin",
        "deaths_A",
        "deaths_D",
        "deaths_R",
        "live",
        "policy_month",
        "policy_year",
        "premium_income",
        "premium_pp",
        "unit_reserve",
    )
    commission = channel_table("commissions_ul")
    mad_expense = by_basis(reserving=param("prudent_margin_expense"), be=0.0, mc=0.0)
    initial_fixed_expense = param("initial_fixed_expense")
    initial_percent_premium_expense = param("initial_percent_premium_expense")
    initial_percent_sa_expense = param("initial_percent_sa_expense")
    renewal_fixed_expense = param("renewal_fixed_expense")
    claim_expense = param("claim_expense")
    fund_expense_rate = param("fund_expense_rate")

    def commission_rate(self, t):
        """Commission rate by policy year and distribution channel."""
        return self.commission[self.policy_year(t), self.policy.Distribution_Channel]

    def commissions(self, t):
        """Commission on the premiums received."""
        return self.commission_rate(t) * self.premium_income(t) * (t > 0)

    def initial_expense(self, t):
        """A fixed amount plus shares of the premium and the sum assured, once, in policy
        month 1: only new business pays it."""
        return (
            (
                (self.initial_fixed_expense + self.expense_add[t]) * self.expense_mult[t]
                + self.initial_percent_premium_expense * self.expense_mult[t] * self.premium_pp(t)
                + self.initial_percent_sa_expense * self.expense_mult[t] * self.policy.Sum_Assured
            )
            * (1 + self.mad_expense)
            * self.A_begin(t)
            * (self.policy_month(t) == 1)
            * (t > 0)
        )

    def renewal_expenses(self, t):
        """The annual maintenance expense spread monthly from policy year 2 over every
        policy in force, whatever its state, inflated from the valuation date."""
        return (
            (self.renewal_fixed_expense + self.expense_add[t])
            * self.expense_mult[t]
            / 12
            * self.inflation_factor(t)
            * (1 + self.mad_expense)
            * (self.A_begin(t) + self.R_begin(t) + self.D_begin(t))
            * (self.policy_year(t) >= 2)
            * self.live(t)
        )

    def fund_expenses(self, t):
        """Investment expenses on the unit funds at the start of the month (last month's
        closing unit reserve; none at the valuation instant)."""
        return (
            self.fund_expense_rate
            / 12
            * self.expense_mult[t]
            * (1 + self.mad_expense)
            * prev(self.unit_reserve, 0.0)
            * (t > 0)
        )

    def claim_expenses(self, t):
        """The cost of settling each death claim in any state, inflated."""
        return (
            self.claim_expense
            * self.expense_mult[t]
            * self.inflation_factor(t)
            * (1 + self.mad_expense)
            * (self.deaths_A(t) + self.deaths_R(t) + self.deaths_D(t))
            * (t > 0)
        )

    def acquisition_cost(self, t):
        """The acquisition cost port: commission and the initial expense."""
        return self.commissions(t) + self.initial_expense(t)

    def expense_outgo(self, t):
        """The maintenance expense port: renewal and fund expenses."""
        return self.renewal_expenses(t) + self.fund_expenses(t)
