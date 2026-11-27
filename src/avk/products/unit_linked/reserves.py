"""The general fund (non-unit) reserve, its regulatory floors and the total reserve.

The discounted cashflow accumulates backwards from the end of the projection with the net
cashflow at the end of the month: `pv(t) = (pv(t + 1) + cf(t)) / (1 + i(t))`. The reserve at
month `t` is next month's present value (reserves stand at the end of the month), shown at
the valuation instant too. The held value is never below zero, nor below a number of days of
the annual mortality charge on the lives in force; a strain provision for likely revivals is
held on the discontinued and paid-up funds.
"""

from avk.model.lang import nxt, param
from avk.products.unit_linked.gf_interest import GeneralFundInterest


class GeneralFundReserves(GeneralFundInterest):
    """Discounted cashflow, floors, revival provision and reserves per policy."""

    REQUIRES = (
        "A_end",
        "R_survival",
        "dpf_close",
        "lives_end",
        "maturities",
        "mc_income",
        "net_cashflows",
        "rpu_close_total",
        "rpu_sar",
        "sar",
        "unit_reserve",
    )
    reserve_floor_days = param("reserve_floor_days")
    revival_strain_dpf = param("revival_strain_dpf")
    revival_strain_rpu = param("revival_strain_rpu")

    def pv_net_cashflows(self, t):
        """Present value at the start of month `t` of the net cashflows from `t` onwards."""
        return (nxt(self.pv_net_cashflows, 0.0) + self.net_cashflows(t)) / (
            1 + self.interest_rate[t]
        )

    def gf_reserve_dcf(self, t):
        """The discounted cashflow general fund reserve at the end of month `t` (often
        negative: future charges exceed future costs)."""
        return nxt(self.pv_net_cashflows, 0.0)

    def annual_mortality_charge(self, t):
        """A year of the mortality charge on the lives in force at the end of month `t`."""
        return 12 * nxt(self.mc_income, 0.0)

    def gf_reserve_floor(self, t):
        """The floor: the stated number of days of the annual mortality charge."""
        return self.reserve_floor_days / 365 * self.annual_mortality_charge(t)

    def gf_reserve_held(self, t):
        """The general fund reserve held: the DCF, never below zero or the floor."""
        return max(self.gf_reserve_dcf(t), 0.0, self.gf_reserve_floor(t))

    def revival_provision(self, t):
        """Strain provision for revivals of discontinued and paid-up policies."""
        return self.revival_strain_dpf * self.dpf_close(
            t
        ) + self.revival_strain_rpu * self.rpu_close_total(t)

    def non_unit_reserve(self, t):
        """The general fund reserve held plus the revival provision."""
        return self.gf_reserve_held(t) + self.revival_provision(t)

    def total_reserve(self, t):
        """The unit reserve plus the non-unit reserve."""
        return self.unit_reserve(t) + self.non_unit_reserve(t)

    def reserve_lives(self, t):
        """The lives a reserve is held for: those in force at the month's end plus those
        maturing in it, never below 1e-6 (so a reserve after the last exit is zero)."""
        return max(self.lives_end(t) + self.maturities(t), 1e-6)

    def gf_reserve_pp(self, t):
        """The general fund reserve held per policy."""
        return self.gf_reserve_held(t) / self.reserve_lives(t)

    def non_unit_reserve_pp(self, t):
        """The non-unit reserve per policy."""
        return self.non_unit_reserve(t) / self.reserve_lives(t)

    def total_reserve_pp(self, t):
        """The total reserve per policy."""
        return self.total_reserve(t) / self.reserve_lives(t)

    def sum_at_risk(self, t):
        """The expected sum at risk of the lives in force at the end of the month: active
        cover above the units, plus the paid-up cohort's cover scaled to its survivors."""
        return self.A_end(t) * self.sar(t) + self.rpu_sar(t) * self.R_survival(t)
