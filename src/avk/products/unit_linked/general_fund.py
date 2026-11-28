"""General-fund (non-unit) cashflows: charge income, outgo and interest.

`net_cashflows` is outgo less income, interest included, so it is positive when the
general fund reserve pays out. Charges other than the fund management and discontinuance
charges are deducted at the start of the month and earn a month's interest with the
acquisition and maintenance expenses; the rest arrive or are paid at the month's end.
"""

from avk.products.unit_linked.gf_interest import GeneralFundInterest


class GeneralFundCashflows(GeneralFundInterest):
    """Income, outgo and the net cashflow the general fund reserve funds."""

    REQUIRES = (
        "acquisition_cost",
        "admin_income",
        "charge_income",
        "claim_expenses",
        "dpf_fmc",
        "disc_charge_income",
        "expense_outgo",
        "fmc_income_A",
        "gc_income",
        "mc_income",
        "non_unit_benefit_outgo",
        "pac_income",
        "rpu_fmc_total",
        "switch_charge_income",
    )

    def residual_additions(self, t):
        """Reduction-in-yield residual additions: none until phase P3 replaces this."""
        return 0.0

    def charges_start(self, t):
        """Charges deducted at the start of the month: allocation, administration,
        mortality and guarantee charges, active and paid-up, and switch charges on
        strategy sales."""
        return (
            self.pac_income(t)
            + self.admin_income(t)
            + self.mc_income(t)
            + self.gc_income(t)
            + self.switch_charge_income(t)
        )

    def charges_end(self, t):
        """Charges taken at the end of the month: fund management charges on every state
        and discontinuance charges."""
        return (
            self.fmc_income_A(t)
            + self.rpu_fmc_total(t)
            + self.dpf_fmc(t)
            + self.disc_charge_income(t)
        )

    def interest_earning_cashflow(self, t):
        """The start-of-month cashflow: those charges less acquisition costs and
        maintenance expenses."""
        return self.charges_start(t) - self.acquisition_cost(t) - self.expense_outgo(t)

    def interest_on_cashflows(self, t):
        """A month's interest on the interest-earning cashflow, at the basis's rate."""
        return self.interest_earning_cashflow(t) * self.interest_rate[t] * (t > 0)

    def net_cashflows(self, t):
        """Outgo less income, interest included: positive when the reserve pays out."""
        return -(
            self.charge_income(t)
            - self.acquisition_cost(t)
            - self.expense_outgo(t)
            - self.claim_expenses(t)
            - self.non_unit_benefit_outgo(t)
            - self.residual_additions(t)
            + self.interest_on_cashflows(t)
        ) * (t > 0)
