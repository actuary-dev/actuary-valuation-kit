"""Paid-up cover and deductions on the aggregate expected fund."""

from avk.model.lang import Component, if_, prev


class PaidUpCashflows(Component):
    """Cover, premium history and unit charges of the opening paid-up cohort."""

    REQUIRES = (
        "R_begin",
        "R_survival",
        "admin_req_rate",
        "gc_rate",
        "instalments_pp",
        "live",
        "mc_rate",
        "rpu_open_total",
        "to_rpu",
        "tpp_pp",
    )

    def pusa_open(self, t):
        """Opening aggregate paid-up sum assured."""
        return prev(
            self.pusa_close, self.policy.Paid_Up_Sum_Assured * (self.policy.Policy_Status == 2)
        )

    def pusa_close(self, t):
        """Paid-up cover of survivors plus cover converted at cessation."""
        return self.pusa_open(t) * self.R_survival(t) + self.to_rpu(
            t
        ) * self.policy.Sum_Assured * self.instalments_pp(t) / max(
            self.policy.Instalments_Payable, 1
        )

    def rpu_tpp_open(self, t):
        """Opening aggregate premiums paid for the paid-up cohort."""
        return prev(
            self.rpu_tpp_close, self.policy.Premiums_Paid_To_Date * (self.policy.Policy_Status == 2)
        )

    def rpu_tpp_close(self, t):
        """Aggregate premiums paid of survivors and new paid-up entrants."""
        return self.rpu_tpp_open(t) * self.R_survival(t) + self.to_rpu(t) * self.tpp_pp(t)

    def rpu_admin_req(self, t):
        """Scheduled admin charge on the opening paid-up lives."""
        return self.R_begin(t) * self.admin_req_rate(t)

    def rpu_gc_req(self, t):
        """Guarantee charge requested from the opening paid-up funds."""
        return self.rpu_open_total(t) * self.gc_rate(t)

    def rpu_before_mortality(self, t):
        """Paid-up fund used for the mortality calculation."""
        return self.rpu_open_total(t) - self.rpu_admin_req(t) - self.rpu_gc_req(t)

    def rpu_floor_db(self, t):
        """Death benefit floor for the opening paid-up cohort."""
        return self.policy.V_min_db_premium_multiple * self.rpu_tpp_open(t)

    def rpu_sar(self, t):
        """Aggregate sum at risk for the paid-up mortality charge."""
        return if_(
            self.policy.V_death_benefit_type == 1,
            max(max(self.pusa_open(t), self.rpu_floor_db(t)) - self.rpu_before_mortality(t), 0),
            max(self.pusa_open(t), self.rpu_floor_db(t) - self.rpu_before_mortality(t)),
        )

    def rpu_mc_req(self, t):
        """Mortality charge requested from paid-up funds."""
        return self.rpu_sar(t) * self.mc_rate(t) / 12000 * self.live(t)

    def rpu_deduction_req(self, t):
        """Requested unit deductions on paid-up funds."""
        return self.rpu_admin_req(t) + self.rpu_gc_req(t) + self.rpu_mc_req(t)

    def rpu_deduction_scale(self, t):
        """Common reduction factor when the paid-up fund cannot meet the requests."""
        return if_(
            self.rpu_deduction_req(t) > max(self.rpu_open_total(t), 0),
            self.rpu_open_total(t) / self.rpu_deduction_req(t),
            1,
        )

    def rpu_admin(self, t):
        """Administration charge actually taken from paid-up funds."""
        return self.rpu_admin_req(t) * self.rpu_deduction_scale(t)

    def rpu_gc(self, t):
        """Guarantee charge actually taken from paid-up funds."""
        return self.rpu_gc_req(t) * self.rpu_deduction_scale(t)

    def rpu_mc(self, t):
        """Mortality charge actually taken from paid-up funds."""
        return self.rpu_mc_req(t) * self.rpu_deduction_scale(t)

    def rpu_deduction_total(self, t):
        """Total charges funded by opening paid-up units."""
        return self.rpu_admin(t) + self.rpu_gc(t) + self.rpu_mc(t)

    def rpu_retention(self, t):
        """Fraction of each paid-up slot retained after deductions."""
        return if_(
            self.rpu_open_total(t) > self.rpu_deduction_req(t) and self.rpu_open_total(t) > 0,
            1 - self.rpu_deduction_total(t) / self.rpu_open_total(t),
            0,
        )
