"""Discontinuance charges and the expected Discontinued Policy Fund."""

from avk.model.lang import Component, if_, on, prev
from avk.products.unit_linked.decrements import year_table


class DiscontinuedFund(Component):
    """Opening DPF holdings earn a credited return, then exits and transfers occur."""

    REQUIRES = (
        "fund_close_total",
        "fund_return_factor",
        "live",
        "lock_in",
        "lockin_due",
        "paid_out_A",
        "policy_year",
        "q",
        "to_dpf",
    )
    disc_pct_low = year_table("ul_charge_scales/disc_pct_low", "Variant_Id")
    disc_pct_high = year_table("ul_charge_scales/disc_pct_high", "Variant_Id")
    disc_cap_low = year_table("ul_charge_scales/disc_cap_low", "Variant_Id")
    disc_cap_high = year_table("ul_charge_scales/disc_cap_high", "Variant_Id")

    def disc_pct(self, t):
        """Annualised-premium charge percentage for the applicable band."""
        return if_(
            self.policy.Annualised_Premium > self.policy.V_disc_ap_threshold,
            self.disc_pct_high[self.policy_year(t), self.policy.Variant_Id],
            self.disc_pct_low[self.policy_year(t), self.policy.Variant_Id],
        )

    def disc_cap(self, t):
        """Absolute discontinuance charge limit for the applicable band."""
        return if_(
            self.policy.Annualised_Premium > self.policy.V_disc_ap_threshold,
            self.disc_cap_high[self.policy_year(t), self.policy.Variant_Id],
            self.disc_cap_low[self.policy_year(t), self.policy.Variant_Id],
        )

    def disc_charge_pp(self, t):
        """Discontinuance charge per active exit within the lock-in."""
        return (
            min(
                self.disc_pct(t) * self.policy.Annualised_Premium,
                self.fund_close_total(t),
                self.disc_cap(t),
            )
            * self.lock_in(t)
            * self.live(t)
        )

    def disc_charge_income(self, t):
        """Discontinuance charges before DPF transfer or direct payment."""
        return (self.to_dpf(t) + self.paid_out_A(t) * self.lock_in(t)) * self.disc_charge_pp(t)

    def dpf_market_return(self, t):
        """Monthly DPF asset-mix return including fund alpha."""
        return (
            self.policy.DPF_W_eq_large * self.ret_eq_large[t]
            + self.policy.DPF_W_eq_mid * self.ret_eq_mid[t]
            + self.policy.DPF_W_eq_small * self.ret_eq_small[t]
            + self.policy.DPF_W_eq_global * self.ret_eq_global[t]
            + self.policy.DPF_W_gov_long * self.ret_gov_long[t]
            + self.policy.DPF_W_gov_short * self.ret_gov_short[t]
            + self.policy.DPF_W_corp_bond * self.ret_corp_bond[t]
            + self.policy.DPF_W_money_market * self.ret_money_market[t]
            + self.policy.DPF_W_gold * self.ret_gold[t]
            + self.policy.DPF_W_real_assets * self.ret_real_assets[t]
        ) + ((1 + self.policy.DPF_Alpha) ** (1 / 12) - 1)

    def dpf_return(self, t):
        """Monthly gross return of the DPF assets."""
        return self.dpf_market_return(t) * self.live(t)

    def dpf_guaranteed(self, t):
        """Minimum monthly DPF return before fund management charges."""
        return ((1 + self.policy.R_dpf_min_rate) ** (1 / 12) - 1) * self.live(t)

    def dpf_open(self, t):
        """Opening expected value of the DPF."""
        return prev(self.dpf_close, self.policy.DPF_Value)

    def dpf_credited_return(self, t):
        """Gross investment return credited to opening DPF holdings."""
        return self.dpf_open(t) * max(self.dpf_return(t), self.dpf_guaranteed(t))

    def dpf_grown(self, t):
        """Value of the opening DPF after crediting monthly returns."""
        return self.dpf_open(t) + self.dpf_credited_return(t)

    def dpf_fmc(self, t):
        """Fund management charge on the grown DPF."""
        return self.dpf_grown(t) * (1 - (1 - self.policy.DPF_FMC) ** (1 / 12)) * self.live(t)

    def dpf_guarantee_cost(self, t):
        """General-fund cost of crediting the minimum return."""
        return self.dpf_open(t) * max(self.dpf_guaranteed(t) - self.dpf_return(t), 0)

    def dpf_after(self, t):
        """Opening DPF holdings after growth and the fund management charge."""
        return self.dpf_grown(t) - self.dpf_fmc(t)

    def dpf_death_paid(self, t):
        """DPF payment on deaths of opening discontinued lives."""
        return self.dpf_after(t) * self.q(t)

    def dpf_inflow(self, t):
        """Transfers from active funds net of the discontinuance charge."""
        return self.to_dpf(t) * (self.fund_close_total(t) - self.disc_charge_pp(t))

    def dpf_lockin_paid(self, t):
        """Release surviving balances and new transfers when due."""
        return (self.dpf_after(t) - self.dpf_death_paid(t) + self.dpf_inflow(t)) * self.lockin_due(
            t
        )

    def dpf_close(self, t):
        """Closing expected DPF after inflows and payouts."""
        return (
            self.dpf_after(t)
            - self.dpf_death_paid(t)
            + self.dpf_inflow(t)
            - self.dpf_lockin_paid(t)
        )

    @on("reserving", overrides="dpf_return")
    def dpf_reserving_return(self, t):
        """DPF return adjusted by the reserving margin."""
        return ((1 + self.dpf_market_return(t)) * self.fund_return_factor(t) - 1) * self.live(t)

    @on("mc", overrides="dpf_return")
    def dpf_mc_return(self, t):
        """DPF return using the selected MC source."""
        return if_(
            self.mc_fund_return_source == 0, self.reference_forward[t], self.dpf_market_return(t)
        ) * self.live(t)
