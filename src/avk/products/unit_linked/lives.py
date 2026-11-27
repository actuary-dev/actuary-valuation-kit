"""Expected lives and exits for the active, discontinued and reduced paid-up states."""

from avk.model.lang import Component, if_, prev, run_param


class UnitLinkedLives(Component):
    """Three linked recursions, with entries credited after the opening lives decrement."""

    REQUIRES = (
        "live",
        "maturity",
        "lock_in",
        "lockin_due",
        "q",
        "w_surrender",
        "w_surrender_full",
        "w_cessation",
    )
    case_mass_lapse = run_param("case_mass_lapse")

    def A_begin(self, t):
        """Opening active lives."""
        return prev(self.A_end, self.policy.Policy_Status == 0)

    def deaths_A(self, t):
        """Active deaths from opening lives."""
        return self.A_begin(t) * self.q(t)

    def surrenders_A(self, t):
        """Surrenders from active survivors of death, including a first-month mass lapse."""
        return (self.A_begin(t) - self.deaths_A(t)) * (
            self.w_surrender(t)
            + (1 - self.w_surrender(t))
            * if_(t == 1 and self.live(t) and self.case_mass_lapse > 0, self.case_mass_lapse, 0)
        )

    def cessations_A(self, t):
        """Cessations from active survivors of death and surrender."""
        return (self.A_begin(t) - self.deaths_A(t) - self.surrenders_A(t)) * self.w_cessation(t)

    def maturities_A(self, t):
        """Active policies still in force at the end of their term."""
        return (
            self.A_begin(t) - self.deaths_A(t) - self.surrenders_A(t) - self.cessations_A(t)
        ) * self.maturity(t)

    def A_end(self, t):
        """Closing active lives after exits."""
        return max(
            self.A_begin(t)
            - self.deaths_A(t)
            - self.surrenders_A(t)
            - self.cessations_A(t)
            - self.maturities_A(t),
            0,
        )

    def to_dpf(self, t):
        """Active discontinuances transferred to the DPF."""
        return (
            (self.surrenders_A(t) + self.cessations_A(t))
            * self.lock_in(t)
            * self.policy.V_dpf_enabled
        )

    def to_rpu(self, t):
        """Active cessations converted to paid-up after lock-in when the variant allows."""
        return self.cessations_A(t) * (1 - self.lock_in(t)) * (self.policy.V_rpu_mode >= 1)

    def paid_out_A(self, t):
        """Active discontinuances paid on exit."""
        return self.surrenders_A(t) + self.cessations_A(t) - self.to_dpf(t) - self.to_rpu(t)

    def D_begin(self, t):
        """Opening DPF lives."""
        return prev(self.D_end, self.policy.Policy_Status == 1)

    def deaths_D(self, t):
        """DPF deaths from opening lives."""
        return self.D_begin(t) * self.q(t)

    def lockin_exits_D(self, t):
        """Release both survivors and new entrants when the DPF is due."""
        return (self.D_begin(t) - self.deaths_D(t) + self.to_dpf(t)) * self.lockin_due(t)

    def D_end(self, t):
        """Closing DPF lives after exits and transfers."""
        return max(self.D_begin(t) - self.deaths_D(t) + self.to_dpf(t) - self.lockin_exits_D(t), 0)

    def R_begin(self, t):
        """Opening reduced paid-up lives."""
        return prev(self.R_end, self.policy.Policy_Status == 2)

    def deaths_R(self, t):
        """Paid-up deaths from opening lives."""
        return self.R_begin(t) * self.q(t)

    def surrenders_R(self, t):
        """Paid-up surrenders from survivors of death."""
        return (self.R_begin(t) - self.deaths_R(t)) * self.w_surrender_full(t)

    def expiries_R(self, t):
        """Paid-up revival expiries for surviving lives in mode 2."""
        return (
            (self.R_begin(t) - self.deaths_R(t) - self.surrenders_R(t))
            * (self.policy.V_rpu_mode == 2)
            * self.live(t)
            / max(self.policy.V_revival_period_months, 1)
        )

    def R_before_maturity(self, t):
        """Opening paid-up lives after death, surrender and revival expiries."""
        return self.R_begin(t) - self.deaths_R(t) - self.surrenders_R(t) - self.expiries_R(t)

    def maturities_R(self, t):
        """Remaining opening paid-up lives due to mature."""
        return self.R_before_maturity(t) * self.maturity(t)

    def R_end(self, t):
        """Closing paid-up lives after exits and transfers."""
        return max(self.R_before_maturity(t) - self.maturities_R(t) + self.to_rpu(t), 0)

    def R_survival(self, t):
        """Share of the opening paid-up cohort retained after all exits."""
        return if_(
            self.R_begin(t) > 0,
            (self.R_before_maturity(t) - self.maturities_R(t)) / self.R_begin(t),
            0,
        )

    def lives_end(self, t):
        """Total closing lives across all three states."""
        return self.A_end(t) + self.D_end(t) + self.R_end(t)

    def maturities(self, t):
        """Maturities across both insured states."""
        return self.maturities_A(t) + self.maturities_R(t)
