"""Reserves per policy, gross and net of reinsurance: one discounting idiom for both.

A present value
accumulates backwards from the end of the projection with the cashflow at the end of the month
(discounting variant A): `pv(t) = (pv(t + 1) + cf(t)) / (1 + i(t))`. The reported value at
month `t` is next month's present value (reserves stand at the end of the month), and the
reserve per policy divides by the lives still in force, floored at 1e-6, then floors at zero.
"""

from avk.model.lang import nxt, run_param
from avk.products.common.cashflows import ValuationInterest


class PolicyReserves(ValuationInterest):
    """Gross and net reserves per surviving policy, on the basis's interest rate."""

    REQUIRES = ("net_cashflows", "net_cf_with_reinsurance", "lives_end", "maturities")
    # IFRS 17 masks the net reserve at the valuation instant. Valuation and stress
    # capital retain the opening reserve.
    mask_step0_reserve = run_param("mask_step0_reserve")

    def eligible_reserve_lives(self, t):
        """Unfloored lives eligible for the book reserve and BEL ratios."""
        return self.lives_end(t) + self.maturities(t)

    def gross_reserve_amount(self, t):
        """Gross held reserve amount, before division into policy reserves."""
        return max(self.discounted_net_cf(t), 0.0)

    def net_reserve_amount(self, t):
        """Net held reserve amount, before division into policy reserves."""
        return max(self.discounted_cf_with_reins(t), 0.0)

    def reserve_lives(self, t):
        """The lives a reserve is held for: those in force at the month's end, plus those
        maturing in it, never below 1e-6 (so a reserve after the last exit is zero)."""
        return max(self.lives_end(t) + self.maturities(t), 1e-6)

    def pv_net_cashflows(self, t):
        """Present value at the start of month `t` of the net cashflows from `t` onwards."""
        return (nxt(self.pv_net_cashflows, 0.0) + self.net_cashflows(t)) / (
            1 + self.interest_rate[t]
        )

    def discounted_net_cf(self, t):
        """End-of-month gross reserve for the group, set to zero at the valuation instant."""
        return nxt(self.pv_net_cashflows, 0.0) * (t > 0)

    def gross_reserve_pp(self, t):
        """Gross reserve per surviving policy, never negative."""
        return max(self.discounted_net_cf(t) / self.reserve_lives(t), 0.0)

    def ceding_reserve_pp(self, t):
        """The gross reserve per policy that next month's cession nets off: equal to
        `gross_reserve_pp` after month 0, and at month 0 the reserve held at the valuation
        date, which the reported gross reserve shows as zero."""
        return max(nxt(self.pv_net_cashflows, 0.0) / self.reserve_lives(t), 0.0)

    def pv_net_cf_with_reinsurance(self, t):
        """Present value at the start of month `t` of the cashflows net of reinsurance."""
        return (nxt(self.pv_net_cf_with_reinsurance, 0.0) + self.net_cf_with_reinsurance(t)) / (
            1 + self.interest_rate[t]
        )

    def discounted_cf_with_reins(self, t):
        """The net reserve for the whole group at the end of the month. A Valuation shows the
        valuation instant's value; a run type setting `mask_step0_reserve` to 1 zeroes it."""
        return nxt(self.pv_net_cf_with_reinsurance, 0.0) * (1 - self.mask_step0_reserve * (t == 0))

    def net_reserve_pp(self, t):
        """Net reserve per surviving policy, never negative: the statutory reserve held."""
        return max(self.discounted_cf_with_reins(t) / self.reserve_lives(t), 0.0)
