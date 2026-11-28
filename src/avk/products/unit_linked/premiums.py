"""Active premiums, histories and deductions before investment growth."""

from avk.model.lang import Component, if_, int_axis, keymap, prev, table
from avk.products.unit_linked.decrements import year_table


class ActiveCashflows(Component):
    """Deductions are requested on the policy fund and taken pro rata across slots."""

    REQUIRES = (
        "allocation_total",
        "anniversary",
        "fund_after_charges_total",
        "fund_close_total",
        "A_begin",
        "age",
        "fund_after_premium_total",
        "live",
        "policy_month",
        "policy_year",
        "premium_due",
        "pw_rate",
        "withdrawable_total",
        "year_start",
    )
    premium_allocation_rate = year_table("ul_charge_scales/premium_allocation_rate", "Variant_Id")
    topup_allocation_rate = year_table("ul_charge_scales/topup_allocation_rate", "Variant_Id")
    admin_charge_monthly = year_table("ul_charge_scales/admin_charge_monthly", "Variant_Id")
    loyalty_rate = year_table("ul_charge_scales/loyalty_rate", "Variant_Id")
    booster_rate = year_table("ul_charge_scales/booster_rate", "Variant_Id")
    mortality_charges = table(
        "mortality_charges_ul",
        axes=(
            int_axis("age", below="error", above="clamp"),
            keymap("Charge_Column", unknown="error", above="error"),
        ),
    )

    def premium_pp(self, t):
        """Instalment received per opening active life."""
        return self.policy.Instalment_Premium * self.premium_due(t) * (self.A_begin(t) > 0)

    def premium_income(self, t):
        """Expected premiums from opening active lives."""
        return (self.premium_pp(t) + self.topup_pp(t)) * self.A_begin(t)

    def topup_pp(self, t):
        """Total gross scheduled and regular top-ups per active life."""
        return if_(
            self.policy.V_topup_on and self.live(t) and self.A_begin(t) > 0,
            self.policy.Single_Top_Up_Premium
            * (self.policy_month(t) == self.policy.Single_Top_Up_Policy_Month)
            + self.policy.Regular_Top_Up_Premium * self.premium_due(t),
            0,
        )

    def topup_pac_pp(self, t):
        """Allocation charge on gross top-ups using their own scale."""
        return (
            self.topup_pp(t)
            * self.topup_allocation_rate[self.policy_year(t), self.policy.Variant_Id]
        )

    def allocated_topup_pp(self, t):
        """Top-up premium invested in the funds."""
        return self.topup_pp(t) - self.topup_pac_pp(t)

    def topup_paid_pp(self, t):
        """Gross top-up premium history per active life, including this month."""
        return prev(self.topup_paid_pp, self.policy.Top_Up_Premiums_Paid_To_Date) + self.topup_pp(t)

    def topup_sa_pp(self, t):
        """Cover bought with the accumulated gross top-ups."""
        return self.policy.V_topup_on * self.policy.V_topup_sa_multiple * self.topup_paid_pp(t)

    def topup_last_month(self, t):
        """Most recent policy month with a positive top-up."""
        return if_(
            self.topup_pp(t) > 0,
            self.policy_month(t),
            prev(self.topup_last_month, self.policy.Last_Top_Up_Policy_Month),
        )

    def topup_lock_active(self, t):
        """Whether the top-up units are currently ineligible for partial withdrawal."""
        return (
            self.policy.V_topup_on
            and self.topup_last_month(t) > 0
            and self.policy_month(t) - self.topup_last_month(t) < self.policy.V_topup_lock_in_months
        )

    def pac_pp(self, t):
        """Allocation charge per active life."""
        return self.premium_pp(t) * self.premium_allocation_rate[
            self.policy_year(t), self.policy.Variant_Id
        ] + self.topup_pac_pp(t)

    def allocated_pp(self, t):
        """Premium credited to the funds."""
        return self.premium_pp(t) + self.topup_pp(t) - self.pac_pp(t)

    def tpp_pp(self, t):
        """Cumulative premiums, including this month's payment."""
        return (
            prev(self.tpp_pp, self.policy.Premiums_Paid_To_Date)
            + self.premium_pp(t)
            + self.topup_pp(t)
        )

    def instalments_pp(self, t):
        """Cumulative instalments paid by the active life."""
        return prev(self.instalments_pp, self.policy.Instalments_Paid) + self.premium_due(t) * (
            self.A_begin(t) > 0
        )

    def pw_this_year_open_pp(self, t):
        """Carried withdrawals still in the current policy year."""
        return if_(self.year_start(t), 0, prev(self.pw_this_year_pp, self.policy.PW_Current_Year))

    def pw_this_year_pp(self, t):
        """Current-year withdrawals including this month."""
        return self.pw_this_year_open_pp(t) + self.pw_pp(t)

    def pw_last_year_pp(self, t):
        """Withdrawals from the previous policy year."""
        return if_(
            self.year_start(t),
            prev(self.pw_this_year_pp, self.policy.PW_Current_Year),
            prev(self.pw_last_year_pp, self.policy.PW_Previous_Year),
        )

    def sa_eff(self, t):
        """Cover after earlier withdrawals still within the two-year window."""
        return max(
            self.policy.Sum_Assured
            - self.policy.V_pw_reduces_sa
            * (self.pw_this_year_open_pp(t) + self.pw_last_year_pp(t)),
            0,
        ) + self.topup_sa_pp(t)

    def floor_db(self, t):
        """Death benefit floor based on total premiums."""
        return self.policy.V_min_db_premium_multiple * self.tpp_pp(t)

    def pw_req(self, t):
        """Requested withdrawal."""
        return if_(
            self.topup_lock_active(t),
            min(self.fund_after_premium_total(t) * self.pw_rate(t), self.withdrawable_total(t)),
            self.fund_after_premium_total(t) * self.pw_rate(t),
        )

    def admin_req_rate(self, t):
        """Scheduled admin charge per life including escalation."""
        return (
            self.admin_charge_monthly[self.policy_year(t), self.policy.Variant_Id]
            * (1 + self.policy.V_admin_escalation) ** (self.policy_year(t) - 1)
            * self.live(t)
        )

    def admin_req(self, t):
        """Requested admin charge per active life."""
        return self.admin_req_rate(t) * (self.A_begin(t) > 0)

    def gc_rate(self, t):
        """Effective monthly guarantee charge rate."""
        return (1 - (1 - self.policy.V_guarantee_charge) ** (1 / 12)) * self.live(t)

    def gc_req(self, t):
        """Requested guarantee charge on the fund after premium allocation."""
        return self.fund_after_premium_total(t) * self.gc_rate(t)

    def fund_before_mortality(self, t):
        """Fund used to price mortality after earlier requested deductions."""
        return (
            self.fund_after_premium_total(t) - self.pw_req(t) - self.admin_req(t) - self.gc_req(t)
        )

    def sar(self, t):
        """Mortality-charge sum at risk per active life."""
        return if_(
            self.policy.V_death_benefit_type == 1,
            max(max(self.sa_eff(t), self.floor_db(t)) - self.fund_before_mortality(t), 0),
            max(self.sa_eff(t), self.floor_db(t) - self.fund_before_mortality(t)),
        )

    def mc_rate(self, t):
        """Contractual annual mortality charge per thousand, with underwriting loadings."""
        return self.mortality_charges[
            self.age(t), self.policy.Charge_Column
        ] * self.policy.V_mortality_charge_multiplier * self.policy.EMR + self.policy.Flat_Extra * (
            self.policy_month(t) <= self.policy.Flat_Extra_Term_Months
        )

    def mc_req(self, t):
        """Requested mortality charge per active life."""
        return self.sar(t) * self.mc_rate(t) / 12000 * self.live(t) * (self.A_begin(t) > 0)

    def deduction_req(self, t):
        """Requested deductions from active units."""
        return self.pw_req(t) + self.admin_req(t) + self.gc_req(t) + self.mc_req(t)

    def deduction_scale(self, t):
        """Fund all deductions at a common reduced rate if they exceed the fund."""
        return if_(
            self.deduction_req(t) > max(self.fund_after_premium_total(t), 0),
            self.fund_after_premium_total(t) / self.deduction_req(t),
            1,
        )

    def pw_pp(self, t):
        """Withdrawal actually deducted per active life."""
        return self.pw_req(t) * self.deduction_scale(t)

    def admin_pp(self, t):
        """Admin charge actually deducted per active life."""
        return self.admin_req(t) * self.deduction_scale(t)

    def gc_pp(self, t):
        """Guarantee charge actually deducted per active life."""
        return self.gc_req(t) * self.deduction_scale(t)

    def mc_pp(self, t):
        """Mortality charge actually deducted per active life."""
        return self.mc_req(t) * self.deduction_scale(t)

    def deduction_total(self, t):
        """Total deductions funded by active units."""
        return self.pw_pp(t) + self.admin_pp(t) + self.gc_pp(t) + self.mc_pp(t)

    def active_retention(self, t):
        """Fraction of each active slot retained after deductions."""
        return if_(
            self.fund_after_premium_total(t) > self.deduction_req(t)
            and self.fund_after_premium_total(t) > 0,
            1 - self.deduction_total(t) / self.fund_after_premium_total(t),
            0,
        )

    def retention_after_withdrawal(self, t):
        """Retention against the remaining balance after the allocated withdrawal."""
        return if_(
            self.fund_after_premium_total(t) > self.pw_pp(t),
            max(
                1
                - (self.admin_pp(t) + self.gc_pp(t) + self.mc_pp(t))
                / (self.fund_after_premium_total(t) - self.pw_pp(t)),
                0,
            ),
            0,
        )

    def mc_cum_pp(self, t):
        """Cumulative charges of this type per active life."""
        return prev(self.mc_cum_pp, self.policy.MC_To_Date) + self.mc_pp(t)

    def pac_cum_pp(self, t):
        """Cumulative charges of this type per active life."""
        return prev(self.pac_cum_pp, self.policy.PAC_To_Date) + self.pac_pp(t)

    def admin_cum_pp(self, t):
        """Cumulative charges of this type per active life."""
        return prev(self.admin_cum_pp, self.policy.Admin_To_Date) + self.admin_pp(t)

    def fund_sum_year_pp(self, t):
        """Eligible month-end values accumulated since the last policy anniversary."""
        return if_(
            self.year_start(t), 0, prev(self.fund_sum_year_pp, self.policy.FV_Sum_Current_Year)
        ) + self.fund_close_total(t) * (t > 0)

    def average_fund(self, t):
        """Anniversary average using the current post-deduction balance before additions."""
        return (
            prev(self.fund_sum_year_pp, self.policy.FV_Sum_Current_Year)
            + self.fund_after_charges_total(t)
        ) / 12

    def full_premiums(self, t):
        """Whether all scheduled instalments through this anniversary have been paid."""
        return self.instalments_pp(t) >= if_(
            self.policy.V_single_premium,
            1,
            min(
                self.policy_year(t) * self.policy.Premium_Frequency, self.policy.Instalments_Payable
            ),
        )

    def additions_due(self, t):
        """An active anniversary with fund value or allocation weights to receive additions."""
        return (
            self.anniversary(t)
            and self.A_begin(t) > 0
            and (self.fund_after_charges_total(t) > 0 or self.allocation_total(t) > 0)
        )

    def loyalty_pp(self, t):
        """Loyalty addition on averaged funds or annualised premium, subject to eligibility."""
        return if_(
            self.additions_due(t)
            and self.policy.V_loyalty_on
            and self.policy_year(t) >= self.policy.V_loyalty_start_year
            and (self.policy.V_loyalty_requires_full_premiums == 0 or self.full_premiums(t)),
            self.loyalty_rate[self.policy_year(t), self.policy.Variant_Id]
            * if_(
                self.policy.V_loyalty_basis == 1,
                self.average_fund(t),
                self.policy.Annualised_Premium,
            ),
            0,
        )

    def booster_pp(self, t):
        """Booster on the average fund at the policy anniversary."""
        return if_(
            self.additions_due(t),
            self.booster_rate[self.policy_year(t), self.policy.Variant_Id] * self.average_fund(t),
            0,
        )

    def guaranteed_addition_pp(self, t):
        """Guaranteed anniversary addition on annualised premium."""
        return (
            self.additions_due(t)
            * self.policy.V_guaranteed_addition_rate
            * self.policy.Annualised_Premium
        )

    def additions_pp(self, t):
        """All active additions credited per opening life."""
        return self.loyalty_pp(t) + self.booster_pp(t) + self.guaranteed_addition_pp(t)
