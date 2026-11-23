"""The IFRS 17 best estimate liability at the onerous-tagging rate, and the expense capital.

Every column reads the best-estimate basis explicitly, so each is computed once.

- The IFRS cashflow is the BE benefit outgo, the grossed-up initial expense, the renewal
  expenses (commission, a fixed schedule and a %-of-premium schedule) and a claim-expense
  schedule, less the BE premiums. Commission is counted once, in the renewal expenses;
  the initial expense is multiplied by the IFRS 17 multiplier `m` itself.
- The onerous-tagging rate uses the policy's IFRS 17 reference forward curve; the FCC rate
  of `MarketConsistentValue`, which keeps the curve's last rate flat beyond its end.
- The fixed renewal expense falls on each policy anniversary, per life in force, and
  every death attracts its policy year's claim-expense rate.
- The expense capital is the present value at the locked-in rate of the stressed renewal
  expenses less that of the renewal expenses (discounting variant B); commission is on both
  sides, unstressed, so it cancels.

The three schedules are monthly curves built before the kernel from the product's annual IFRS 17
renewal-expense table: each year's amount in the first month of the year, zero in the other
months and beyond the projection. Each is read along the policy's own months (index
`policy_month - 1`), so a year's amount falls on the policy anniversary.
"""

from avk.model.lang import Component, at_basis, curve, if_, nxt, param, prev, scen


class IfrsBestEstimate(Component):
    """The IFRS 17 BEL at the onerous-tagging rate, per policy, and the expense capital."""

    REQUIRES = (
        "premium_income",
        "benefit_outgo",
        "commissions",
        "initial_expense",
        "deaths",
        "lives_begin",
        "lives_end",
        "maturities",
        "policy_month",
        "fcc_rate",
        "inflation_factor",
    )
    ifrs_fixed_schedule = curve("ifrs17_renewal_fixed", below="zero_rows", above="zero")
    ifrs_premium_schedule = curve("ifrs17_renewal_premium", below="zero_rows", above="zero")
    ifrs_claim_schedule = curve("ifrs17_renewal_claim", below="zero_rows", above="zero")
    ifrs_locked_in = scen("ifrs_locked_in")
    ifrs_initial_multiplier = param("ifrs_initial_expense_multiplier")
    ifrs_stress_expense = param("IFRS 17 stress expense")
    ifrs_stress_inflation = param("IFRS 17 stress inflation")

    def ifrs_premiums(self, t):
        """The best-estimate premiums."""
        return at_basis("be", self.premium_income)(t)

    def ifrs_initial_expense(self, t):
        """The BE initial expense times the IFRS 17 multiplier, as `m`; commission
        is not added here."""
        return at_basis("be", self.initial_expense)(t) * self.ifrs_initial_multiplier

    def ifrs_case_price(self, t):
        """Persistent case inflation relative to inflation already in the schedules."""
        return if_(
            t > 0,
            self.inflation_factor(t) / (1 + self.inflation) ** ((t - 1) / 12),
            1.0,
        )

    def ifrs_fixed_addition(self, t):
        """Annual fixed expense addition on the policy anniversary, per opening BE life."""
        return (
            self.expense_add[t]
            * ((self.policy_month(t) - 1) % 12 == 0)
            * (self.policy_month(t) > 0)
            * (t > 0)
            * at_basis("be", self.lives_begin)(t)
        )

    def ifrs_renewal_fixed(self, t):
        """The fixed renewal expense: the policy year's amount on the policy anniversary (policy
        months 1, 13, 25, ...), per life in force at the start of the month."""
        return (
            (
                self.ifrs_fixed_schedule[self.policy_month(t) - 1]
                * at_basis("be", self.lives_begin)(t)
                + self.ifrs_fixed_addition(t)
            )
            * self.expense_mult[t]
            * self.ifrs_case_price(t)
        )

    def ifrs_premium_block_pulse(self, t):
        """From month 2, the %-of-premium rate falling in the 12-month block holding month `t`,
        read along the policy's own months (zero where the schedule has none)."""
        return self.ifrs_premium_schedule[
            12 * ((self.policy_month(t) - t) // 12 + 1 + (t - 2) // 12)
        ]

    def ifrs_premium_block_rate(self, t):
        """The block's rate where it is nonzero, else the previous block's; none before month 2
        (`adjust_prem_expenses`)."""
        return if_(
            t >= 2,
            if_(
                self.ifrs_premium_block_pulse(t) != 0,
                self.ifrs_premium_block_pulse(t),
                prev(self.ifrs_premium_block_rate, 0.0),
            ),
            0.0,
        )

    def ifrs_premium_rate(self, t):
        """The %-of-premium renewal rate: the schedule at the policy's month for yearly
        premiums (and every premium before month 2); the block rate for premiums paid more
        often than yearly."""
        return if_(
            (self.policy.Premium_Frequency > 1) and (t >= 2),
            self.ifrs_premium_block_rate(t),
            self.ifrs_premium_schedule[self.policy_month(t) - 1],
        )

    def ifrs_renewal_expenses(self, t):
        """Commission, the fixed renewal expense and the %-of-premium renewal expense."""
        return (
            at_basis("be", self.commissions)(t)
            + self.ifrs_renewal_fixed(t)
            + self.ifrs_premium_rate(t)
            * self.ifrs_premiums(t)
            * self.expense_mult[t]
            * self.ifrs_case_price(t)
        )

    def ifrs_claim_expense(self, t):
        """The month's BE deaths at their policy year's claim-expense rate, read at the policy
        year's first month."""
        return (
            self.ifrs_claim_schedule[12 * ((self.policy_month(t) - 1) // 12)]
            * at_basis("be", self.deaths)(t)
            * self.expense_mult[t]
            * self.ifrs_case_price(t)
        )

    def ifrs_bel_cf(self, t):
        """The IFRS 17 cashflow, gross of reinsurance: outgo positive, premiums negative."""
        return (
            at_basis("be", self.benefit_outgo)(t)
            + self.ifrs_initial_expense(t)
            + self.ifrs_renewal_expenses(t)
            + self.ifrs_claim_expense(t)
            - self.ifrs_premiums(t)
        )

    def ifrs_onerous_cf(self, t):
        """The cashflow less the month's interest on premiums net of expenses, at the policy's
        onerous-tagging rate."""
        return self.ifrs_bel_cf(t) - (
            self.ifrs_premiums(t) - self.ifrs_initial_expense(t) - self.ifrs_renewal_expenses(t)
        ) * self.fcc_rate(t)

    def pv_ifrs_onerous(self, t):
        """Present value at the start of month `t` of those cashflows from `t` on (variant A),
        on the policy's own reference forward curve."""
        return (nxt(self.pv_ifrs_onerous, 0.0) + self.ifrs_onerous_cf(t)) / (1 + self.fcc_rate(t))

    def ifrs_bel(self, t):
        """The IFRS 17 BEL at the onerous-tagging rate, at the end of month `t`."""
        return nxt(self.pv_ifrs_onerous, 0.0)

    def ifrs_bel_pp(self, t):
        """The IFRS 17 BEL per policy held: NaN once no life remains (0 / 0)."""
        return self.ifrs_bel(t) / (
            at_basis("be", self.lives_end)(t) + at_basis("be", self.maturities)(t)
        )

    def pv_ifrs_expenses(self, t):
        """Present value at the start of month `t` of the renewal expenses from `t` on, at the
        locked-in rate (variant B)."""
        return self.ifrs_renewal_expenses(t) + nxt(self.pv_ifrs_expenses, 0.0) / (
            1 + self.ifrs_locked_in[t]
        )

    def ifrs_stress_inflation_factor(self, t):
        """Stress inflation: none for two months, then compounding monthly."""
        return if_(t < 2, 1.0, (1 + self.ifrs_stress_inflation) ** (t - 1))

    def ifrs_stressed_expenses(self, t):
        """The stressed renewal expenses: the fixed expense, the stressed, inflated %-of-premium
        expense and commission unstressed, as in the base expenses."""
        return (
            self.ifrs_renewal_fixed(t)
            + self.ifrs_premium_rate(t)
            * self.ifrs_premiums(t)
            * self.expense_mult[t]
            * self.ifrs_case_price(t)
            * self.ifrs_stress_expense
            * self.ifrs_stress_inflation_factor(t)
            + at_basis("be", self.commissions)(t)
        )

    def pv_ifrs_stressed(self, t):
        """Present value at the start of month `t` of the stressed expenses (variant B)."""
        return self.ifrs_stressed_expenses(t) + nxt(self.pv_ifrs_stressed, 0.0) / (
            1 + self.ifrs_locked_in[t]
        )

    def ifrs_expense_capital(self, t):
        """The expense capital at the end of month `t`: stressed less base present value."""
        return nxt(self.pv_ifrs_stressed, 0.0) - nxt(self.pv_ifrs_expenses, 0.0)
