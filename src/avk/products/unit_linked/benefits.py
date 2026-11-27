"""Unit and general-fund benefits and expected cashflow totals."""

from avk.model.lang import Component, if_


class UnitSegment(Component):
    """Separate payments from units from amounts borne by the general fund."""

    REQUIRES = (
        "A_begin",
        "A_end",
        "R_begin",
        "additions_pp",
        "admin_cum_pp",
        "admin_pp",
        "allocated_pp",
        "deaths_A",
        "disc_charge_income",
        "disc_charge_pp",
        "dpf_close",
        "dpf_death_paid",
        "dpf_fmc",
        "dpf_guarantee_cost",
        "dpf_lockin_paid",
        "expiries_R",
        "floor_db",
        "fund_close_total",
        "fund_fmc_total",
        "gc_pp",
        "maturities_A",
        "maturities_R",
        "mc_cum_pp",
        "mc_pp",
        "nav_excess_A_pp",
        "nav_excess_R",
        "pac_cum_pp",
        "pac_pp",
        "paid_out_A",
        "pusa_open",
        "pw_pp",
        "q",
        "rpu_admin",
        "rpu_after_fmc_total",
        "rpu_close_total",
        "rpu_floor_db",
        "rpu_fmc_total",
        "rpu_gc",
        "rpu_mc",
        "rpu_tpp_open",
        "sa_eff",
        "surrenders_R",
        "switch_charge_pp",
        "tpp_pp",
    )

    def death_unit_A(self, t):
        """Closing active units paid on death."""
        return self.deaths_A(t) * self.fund_close_total(t)

    def death_non_unit_A(self, t):
        """Active death benefit above the closing units."""
        return self.deaths_A(t) * if_(
            self.policy.V_death_benefit_type == 1,
            max(self.sa_eff(t), self.floor_db(t), self.fund_close_total(t))
            - self.fund_close_total(t),
            max(self.sa_eff(t) + self.fund_close_total(t), self.floor_db(t))
            - self.fund_close_total(t),
        )

    def surrender_unit_A(self, t):
        """Paid active discontinuances, net of any discontinuance charge."""
        return self.paid_out_A(t) * (self.fund_close_total(t) - self.disc_charge_pp(t))

    def maturity_unit_A(self, t):
        """Closing active units paid at maturity."""
        return self.maturities_A(t) * self.fund_close_total(t)

    def roc_pp(self, t):
        """Specified share of cumulative charges per active life."""
        return (
            self.policy.V_romc_fraction * self.mc_cum_pp(t)
            + self.policy.V_ropac_fraction * self.pac_cum_pp(t)
            + self.policy.V_roadmin_fraction * self.admin_cum_pp(t)
        )

    def return_of_charges(self, t):
        """General-fund refund of charges on active maturity."""
        return self.maturities_A(t) * self.roc_pp(t)

    def gmmb_pp(self, t):
        """Active maturity guarantee above closing units and the charge refund."""
        return self.policy.V_gmmb_on * max(
            self.policy.V_gmmb_premium_multiple * self.tpp_pp(t)
            - self.fund_close_total(t)
            - self.roc_pp(t)
            - self.nav_excess_A_pp(t),
            0,
        )

    def maturity_guarantee_A(self, t):
        """Expected general-fund maturity top-up for active lives."""
        return self.maturities_A(t) * self.gmmb_pp(t)

    def death_unit_R(self, t):
        """Share of the charged and grown paid-up funds released on death."""
        return self.q(t) * self.rpu_after_fmc_total(t)

    def death_non_unit_R(self, t):
        """Expected general-fund death top-up for the opening paid-up cohort."""
        return self.q(t) * if_(
            self.policy.V_death_benefit_type == 1,
            max(self.pusa_open(t), self.rpu_floor_db(t), self.rpu_after_fmc_total(t))
            - self.rpu_after_fmc_total(t),
            max(self.pusa_open(t) + self.rpu_after_fmc_total(t), self.rpu_floor_db(t))
            - self.rpu_after_fmc_total(t),
        )

    def surrender_unit_R(self, t):
        """Share of the charged and grown paid-up funds paid on surrender."""
        return if_(
            self.R_begin(t) > 0,
            self.rpu_after_fmc_total(t) * (self.surrenders_R(t) / self.R_begin(t)),
            0,
        )

    def expiry_unit_R(self, t):
        """Share of the charged and grown paid-up funds paid on expiry."""
        return if_(
            self.R_begin(t) > 0,
            self.rpu_after_fmc_total(t) * (self.expiries_R(t) / self.R_begin(t)),
            0,
        )

    def maturity_share_R(self, t):
        """Share of the opening paid-up cohort maturing this month."""
        return if_(self.R_begin(t) > 0, self.maturities_R(t) / self.R_begin(t), 0)

    def maturity_unit_R(self, t):
        """Share of the charged and grown paid-up funds paid on maturity."""
        return self.rpu_after_fmc_total(t) * self.maturity_share_R(t)

    def maturity_guarantee_R(self, t):
        """Expected general-fund maturity top-up for paid-up lives."""
        return self.policy.V_gmmb_on * max(
            self.policy.V_gmmb_premium_multiple * self.rpu_tpp_open(t) * self.maturity_share_R(t)
            - self.maturity_unit_R(t)
            - self.nav_excess_R(t) * self.maturity_share_R(t),
            0,
        )

    def highest_nav_cost(self, t):
        """Expected maturity payment above the active and paid-up unit values."""
        return self.maturities_A(t) * self.nav_excess_A_pp(t) + self.maturity_share_R(
            t
        ) * self.nav_excess_R(t)

    def partial_withdrawal_outgo(self, t):
        """Disbursements from active unit funds for withdrawals."""
        return self.A_begin(t) * self.pw_pp(t)

    def addition_outgo(self, t):
        """Expected cost of the additions credited to active units."""
        return self.A_begin(t) * self.additions_pp(t)

    def unit_exit_benefits(self, t):
        """Payments from units on active, discontinued and paid-up exits."""
        return (
            self.death_unit_A(t)
            + self.surrender_unit_A(t)
            + self.maturity_unit_A(t)
            + self.dpf_death_paid(t)
            + self.dpf_lockin_paid(t)
            + self.death_unit_R(t)
            + self.surrender_unit_R(t)
            + self.expiry_unit_R(t)
            + self.maturity_unit_R(t)
        )

    def unit_benefit_outgo(self, t):
        """Total claims and withdrawals paid from units."""
        return self.unit_exit_benefits(t) + self.partial_withdrawal_outgo(t)

    def non_unit_benefit_outgo(self, t):
        """General-fund benefit top-ups, refunds, additions and DPF guarantee cost."""
        return (
            self.death_non_unit_A(t)
            + self.death_non_unit_R(t)
            + self.return_of_charges(t)
            + self.maturity_guarantee_A(t)
            + self.maturity_guarantee_R(t)
            + self.addition_outgo(t)
            + self.dpf_guarantee_cost(t)
            + self.highest_nav_cost(t)
        )

    def allocated_premiums(self, t):
        """Expected premiums credited to active units after the allocation charge."""
        return self.A_begin(t) * self.allocated_pp(t)

    def pac_income(self, t):
        """Allocation charges on expected premiums."""
        return self.A_begin(t) * self.pac_pp(t)

    def admin_income(self, t):
        """Expected admin charges deducted from active and paid-up units."""
        return self.A_begin(t) * self.admin_pp(t) + self.rpu_admin(t)

    def mc_income(self, t):
        """Expected mortality charges deducted from active and paid-up units."""
        return self.A_begin(t) * self.mc_pp(t) + self.rpu_mc(t)

    def gc_income(self, t):
        """Expected guarantee charges deducted from active and paid-up units."""
        return self.A_begin(t) * self.gc_pp(t) + self.rpu_gc(t)

    def fmc_income_A(self, t):
        """Expected fund management charges from the active slots."""
        return self.A_begin(t) * self.fund_fmc_total(t)

    def charge_income(self, t):
        """Expected charge income across premiums and all policy states."""
        return (
            self.pac_income(t)
            + self.admin_income(t)
            + self.mc_income(t)
            + self.gc_income(t)
            + self.fmc_income_A(t)
            + self.rpu_fmc_total(t)
            + self.dpf_fmc(t)
            + self.disc_charge_income(t)
            + self.switch_charge_income(t)
        )

    def switch_charge_income(self, t):
        """Switch charges funded from the active units sold."""
        return self.switch_charge_pp(t) * self.A_begin(t)

    def unit_reserve_A(self, t):
        """Expected active unit reserve after exits."""
        return self.A_end(t) * self.fund_close_total(t)

    def unit_reserve(self, t):
        """Closing expected value of the unit funds across the three states."""
        return self.unit_reserve_A(t) + self.rpu_close_total(t) + self.dpf_close(t)
