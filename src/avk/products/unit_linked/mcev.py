"""Market-consistent embedded value of unit-linked business on the `mc` basis.

The `mc` basis projects the whole model again with the general fund earning, and (when
`mc_fund_return_source` is 0) every fund growing at, the risk-free reference forward rate:
the BE path is not re-discounted. Present values use discounting variant A (cashflow at the
end of the month), `pv(t) = (pv(t + 1) + cf(t)) / (1 + i(t))`, except premiums, which use
variant B (`pv(t) = cf(t) + pv(t + 1) / (1 + i(t))`). Each present value is reported at the
end of month `t`.

- PVFP: the profit chain at the reference rate.
- Frictional cost: what tax and the profit transfer take from the investment income on
  required capital. Holding the capital is not itself charged here.
- Cost of residual non-hedgeable risk: a cost-of-capital charge on required capital.
- VIF = PVFP - frictional cost - CRNHR.
- BEL: the unit reserve plus the present value of the general fund's net outgo.
"""

from avk.model.lang import at_basis, nxt, param, prev, scen
from avk.products.unit_linked.profit import UnitLinkedProfitRates


class UnitLinkedMarketConsistentValue(UnitLinkedProfitRates):
    """The profit chain on the `mc` basis and its present values."""

    REQUIRES = (
        "interest_on_solvency_capital",
        "lives_end",
        "maturities",
        "net_cashflows",
        "non_unit_reserve_pp",
        "premium_income",
        "required_solvency_capital",
        "unit_reserve",
    )
    reference_forward = scen("reference_forward")
    cost_of_capital_rate = param("cost_of_capital_rate")

    def mc_lives(self, t):
        """The `mc` basis's lives in force at the month's end plus those maturing in it."""
        return at_basis("mc", self.lives_end)(t) + at_basis("mc", self.maturities)(t)

    def mc_net_cf(self, t):
        """The general fund's income less outgo on the `mc` basis, interest included at
        the reference rate."""
        return -at_basis("mc", self.net_cashflows)(t) * (t > 0)

    def mc_reserves(self, t):
        """The reserving basis's non-unit reserve per policy held for the `mc` lives."""
        return max(at_basis("reserving", self.non_unit_reserve_pp)(t) * self.mc_lives(t), 0.0) * (
            t > 0
        )

    def mc_increase_in_reserves(self, t):
        """This month's `mc` reserve less last month's."""
        return self.mc_reserves(t) - prev(self.mc_reserves, 0.0)

    def mcev_interest_on_reserve(self, t):
        """Interest at the reference rate on the reserve held at the start of the month."""
        return prev(self.mc_reserves, 0.0) * self.reference_forward[t] * (t > 0)

    def mcev_profit_before_tax(self, t):
        """Emerging profit at the reference rate before the profit transfer and tax."""
        return (
            self.mc_net_cf(t) - self.mc_increase_in_reserves(t) + self.mcev_interest_on_reserve(t)
        )

    def mcev_profit_transfer(self, t):
        """The profit transfer at the reference rate."""
        return self.mcev_profit_before_tax(t) * self.profit_transfer_rate

    def mcev_tax(self, t):
        """Tax at the reference rate, after the profit transfer."""
        return (self.mcev_profit_before_tax(t) - self.mcev_profit_transfer(t)) * self.tax_rate

    def mcev_net_profit(self, t):
        """Profit at the reference rate after the profit transfer and tax."""
        return self.mcev_profit_before_tax(t) - self.mcev_profit_transfer(t) - self.mcev_tax(t)

    def pv_net_profit(self, t):
        """Present value at the start of month `t` of the profits from `t` on (variant A)."""
        return (nxt(self.pv_net_profit, 0.0) + self.mcev_net_profit(t)) / (
            1 + self.reference_forward[t]
        )

    def pvfp(self, t):
        """Present value of future profits at the end of month `t`."""
        return nxt(self.pv_net_profit, 0.0)

    def pv_premiums_from(self, t):
        """Present value at the start of month `t` of the `mc` premiums from `t` on
        (variant B: premiums are received at the start of the month)."""
        return at_basis("mc", self.premium_income)(t) + nxt(self.pv_premiums_from, 0.0) / (
            1 + self.reference_forward[t]
        )

    def pv_premium(self, t):
        """Present value of future premiums at the end of month `t`."""
        return nxt(self.pv_premiums_from, 0.0)

    def interest_on_sm_mc(self, t):
        """Interest at the reference rate on the `mc` capital held at the month's start."""
        return at_basis("mc", self.interest_on_solvency_capital)(t)

    def frictional_cost(self, t):
        """The tax and profit-transfer leakage on the interest earned by capital."""
        return self.interest_on_sm_mc(t) * (
            self.tax_rate + (1 - self.tax_rate) * self.profit_transfer_rate
        )

    def pv_frictional_cost(self, t):
        """Present value at the start of month `t` of the frictional costs from `t` on."""
        return (nxt(self.pv_frictional_cost, 0.0) + self.frictional_cost(t)) / (
            1 + self.reference_forward[t]
        )

    def fcc(self, t):
        """Frictional cost of capital at the end of month `t`."""
        return nxt(self.pv_frictional_cost, 0.0)

    def crnhr_charge(self, t):
        """The month's cost-of-capital charge on the `mc` required capital."""
        return self.cost_of_capital_rate / 12 * at_basis("mc", self.required_solvency_capital)(t)

    def pv_crnhr_charge(self, t):
        """Present value at the start of month `t` of the CRNHR charges from `t` on."""
        return (nxt(self.pv_crnhr_charge, 0.0) + self.crnhr_charge(t)) / (
            1 + self.reference_forward[t]
        )

    def crnhr(self, t):
        """Cost of residual non-hedgeable risk at the end of month `t`."""
        return nxt(self.pv_crnhr_charge, 0.0)

    def vif(self, t):
        """Value of in-force: PVFP less the frictional cost and the CRNHR."""
        return self.pvfp(t) - self.fcc(t) - self.crnhr(t)

    def pv_mc_net_cf(self, t):
        """Present value at the start of month `t` of the `mc` net cashflows from `t` on."""
        return (nxt(self.pv_mc_net_cf, 0.0) + self.mc_net_cf(t)) / (1 + self.reference_forward[t])

    def gf_bel(self, t):
        """The non-unit best-estimate liability at the end of month `t`: positive when the
        general fund owes."""
        return -nxt(self.pv_mc_net_cf, 0.0)

    def bel(self, t):
        """The best-estimate liability: the `mc` unit reserve plus the non-unit BEL."""
        return at_basis("mc", self.unit_reserve)(t) + self.gf_bel(t)

    def bel_pp(self, t):
        """The best-estimate liability per policy held: NaN once no life remains (0 / 0),
        which the aggregate skips."""
        return self.bel(t) / self.mc_lives(t)

    def coverage_units(self, t):
        """Investment-related service: the best-estimate fund value in force across the
        active, paid-up and discontinued states; none at the valuation instant."""
        return at_basis("be", self.unit_reserve)(t) * (t > 0)
