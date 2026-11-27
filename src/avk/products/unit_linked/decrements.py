"""Timing and decrements for the three unit-linked policy states."""

from avk.model.lang import Component, by_basis, clip, if_, int_axis, keymap, param, run_param, table


def year_table(name: str, key: str) -> object:
    return table(
        name,
        axes=(
            int_axis("policy_year", below="clamp", above="clamp"),
            keymap(key, unknown="error", above="error"),
        ),
    )


def channel_table(name: str) -> object:
    return table(
        name,
        value="rate",
        axes=(
            int_axis("policy_year", below="clamp", above="clamp"),
            keymap("Distribution_Channel", unknown="error", above="error"),
        ),
    )


class UnitLinkedDecrements(Component):
    """Contract timing, modal premiums and monthly rates on each basis."""

    REQUIRES = ("policy_month", "policy_year", "age")

    mortality = table(
        "mortality",
        axes=(
            int_axis("age", below="error", above="clamp"),
            keymap("Gender_Code", unknown="error", above="error"),
        ),
    )
    discontinuance = channel_table("lapse_rates_ul")
    partial_withdrawals = channel_table("partial_withdrawals_ul")
    experience_mortality_pct = param("experience_mortality_pct")
    smoker_mortality_loading = param("smoker_mortality_loading")
    surrender_share = param("surrender_share")
    mad_mortality = by_basis(reserving=param("prudent_margin_mortality"), be=0.0, mc=0.0)
    mad_lapse = by_basis(reserving=param("prudent_margin_lapse"), be=0.0, mc=0.0)
    mad_pw = by_basis(reserving=param("prudent_margin_partial_withdrawal"), be=0.0, mc=0.0)
    mortality_add = run_param("mortality_add", monthly=True)
    mortality_mult = run_param("mortality_mult", monthly=True)
    lapse_add = run_param("lapse_add", monthly=True)
    lapse_mult = run_param("lapse_mult", monthly=True)
    lapse_maximum_decrease = run_param("lapse_maximum_decrease", monthly=True)

    def term_months(self, t):
        """Number of months in the policy term."""
        return self.policy.Policy_Term * 12

    def live(self, t):
        """Projected months in the policy term, including the maturity month."""
        return t > 0 and self.policy_month(t) >= 1 and self.policy_month(t) <= self.term_months(t)

    def matured_at_valuation(self, t):
        """The valuation instant is in the final month of the policy term."""
        return self.policy.Duration_in_Months == self.term_months(t)

    def maturity(self, t):
        """Settle at term end, or at step 1 if the term ended at valuation."""
        return (self.live(t) and self.policy_month(t) == self.term_months(t)) or (
            t == 1 and self.matured_at_valuation(t)
        )

    def year_start(self, t):
        """First month of a new policy year after issue."""
        return self.live(t) and self.policy_month(t) > 1 and self.policy_month(t) % 12 == 1

    def anniversary(self, t):
        """Last month of a policy year."""
        return self.live(t) and self.policy_month(t) % 12 == 0

    def lock_in(self, t):
        """Discontinuances through the last month of lock-in are within the lock-in."""
        return self.policy_month(t) <= self.policy.V_lock_in_months

    def lockin_due(self, t):
        """Release at the earlier of lock-in end and term end, or at step 1 if overdue."""
        return t > 0 and self.policy_month(t) >= min(
            self.policy.V_lock_in_months, self.term_months(t)
        )

    def in_premium_term(self, t):
        """Whether the current policy month falls within the recurring payment term."""
        return self.policy_month(t) <= self.policy.Premium_Payment_Term * 12

    def paying(self, t):
        """Recurring-premium contracts are exposed to premium cessation within the term."""
        return self.in_premium_term(t) and self.policy.V_single_premium == 0

    def premium_due(self, t):
        """The modal schedule starts in month 1, including for a single premium."""
        return self.live(t) and if_(
            self.policy.V_single_premium,
            self.policy_month(t) == 1,
            self.in_premium_term(t)
            and (
                self.policy.Premium_Frequency == 12
                or self.policy_month(t) % (12 / max(self.policy.Premium_Frequency, 1)) == 1
            ),
        )

    def mortality_rate(self, t):
        """Annual experience mortality including case shocks, EMR and the basis margin."""
        return min(
            clip(
                (
                    self.mortality[self.age(t), self.policy.Gender_Code]
                    * self.experience_mortality_pct
                    * if_(self.policy.Smoker_Code == 1, self.smoker_mortality_loading, 1)
                    + self.mortality_add[t]
                )
                * self.mortality_mult[t],
                0,
                1,
            )
            * self.policy.EMR
            * (1 + self.mad_mortality),
            1,
        )

    def q(self, t):
        """Monthly experience mortality for policies within the projection term."""
        return (1 - (1 - self.mortality_rate(t)) ** (1 / 12)) * self.live(t)

    def discontinuance_rate(self, t):
        """Annual discontinuance including the case decrease limit and the basis margin."""
        return min(
            clip(
                (
                    self.discontinuance[self.policy_year(t), self.policy.Distribution_Channel]
                    + self.lapse_add[t]
                )
                * self.lapse_mult[t],
                max(
                    0,
                    self.discontinuance[self.policy_year(t), self.policy.Distribution_Channel]
                    - self.lapse_maximum_decrease[t],
                ),
                1,
            )
            * (1 + self.mad_lapse),
            1,
        )

    def surrender_rate(self, t):
        """Annual surrender uses the full rate once recurring premiums stop."""
        return self.discontinuance_rate(t) * if_(self.paying(t), self.surrender_share, 1)

    def w_surrender(self, t):
        """Monthly active surrender rate, excluding the maturity month."""
        return (
            (1 - (1 - self.surrender_rate(t)) ** (1 / 12)) * self.live(t) * (1 - self.maturity(t))
        )

    def w_surrender_full(self, t):
        """Monthly paid-up surrender rate, based on the full discontinuance rate."""
        return (
            (1 - (1 - self.discontinuance_rate(t)) ** (1 / 12))
            * self.live(t)
            * (1 - self.maturity(t))
        )

    def w_cessation(self, t):
        """Cessation on recurring-premium due months before maturity."""
        return (
            (
                1
                - (1 - self.discontinuance_rate(t) * (1 - self.surrender_share))
                ** (1 / max(self.policy.Premium_Frequency, 1))
            )
            * self.premium_due(t)
            * self.paying(t)
            * (1 - self.maturity(t))
        )

    def pw_rate(self, t):
        """Monthly partial-withdrawal rate after the variant's start year is reached."""
        return (
            (
                1
                - (
                    1
                    - min(
                        self.partial_withdrawals[
                            self.policy_year(t), self.policy.Distribution_Channel
                        ]
                        * (1 + self.mad_pw),
                        1,
                    )
                )
                ** (1 / 12)
            )
            * self.policy.V_pw_allowed
            * (self.policy_year(t) >= self.policy.V_pw_start_year)
            * self.live(t)
        )
