"""Case parameters prepared once by the run, shared across every policy.

Monthly add/mult schedules shock mortality, morbidity, lapse and expenses month by month.
Inflation is a level, not a monthly rate: `inflation_months[t]` counts the months up to `t`
that grew at the shocked rate, so the price level a window reaches persists after it.
"""

from avk.model.lang import Component, param, run_param


class CaseShocks(Component):
    renewal_premium_expense_after_payment_term = param("renewal_premium_expense_after_payment_term")
    lapses_after_payment_term = param("lapses_after_payment_term")
    mortality_add = run_param("mortality_add", monthly=True)
    mortality_mult = run_param("mortality_mult", monthly=True)
    morbidity_add = run_param("morbidity_add", monthly=True)
    morbidity_mult = run_param("morbidity_mult", monthly=True)
    lapse_add = run_param("lapse_add", monthly=True)
    lapse_mult = run_param("lapse_mult", monthly=True)
    lapse_maximum_decrease = run_param("lapse_maximum_decrease", monthly=True)
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
