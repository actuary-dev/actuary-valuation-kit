"""Market-consistent present values at the valuation date: PVFP, PV of premiums, BEL and FCC.

The best-estimate profit chain is projected with interest at the
risk-free reference curve in place of the expected return on investments, then discounted
at that reference curve:

- discounting variant A (cashflow at the end of the month) for profits, the net cashflow (BEL)
  and the cost of capital (FCC): `pv(t) = (pv(t + 1) + cf(t)) / (1 + i(t))`;
- variant B (cashflow at the start) for premiums: `pv(t) = cf(t) + pv(t + 1) / (1 + i(t))`;

and each present value is reported shifted up one month, at the end of month `t`. The FCC is
discounted on each policy's own IFRS 17 reference forward curve, indexed by policy month.
The curve holds its last rate beyond its end. Every column reads the best-estimate
basis explicitly, so each is computed once.
"""

from avk.model.lang import at_basis, if_, nxt, prev, scen
from avk.products.common.profit import ProfitRates


class MarketConsistentValue(ProfitRates):
    """The profit chain at reference forward curve and its present values."""

    REQUIRES = (
        "interest_earning_cashflow",
        "interest_on_cashflows",
        "premiums",
        "lives_end",
        "maturities",
        "policy_month",
        "be_net_cf",
        "be_reserves",
        "increase_in_reserves",
        "required_solvency_capital",
        "increase_in_solvency_capital",
    )
    reference_forward = scen("reference_forward")
    ifrs_reference_forward = scen("ifrs_reference_forward")

    def mcev_interest_on_cashflows(self, t):
        """Best-estimate interest on opening cashflows at the reference curve."""
        return (
            at_basis("be", self.interest_earning_cashflow)(t) * self.reference_forward[t] * (t > 0)
        )

    def mcev_interest_on_reserve(self, t):
        """Interest at reference forward curve on the reserve held at the start of the month."""
        return prev(self.be_reserves, 0.0) * self.reference_forward[t] * (t > 0)

    def mcev_net_cf(self, t):
        """The BE net cashflow with its interest re-earned at reference forward curve."""
        return (
            self.be_net_cf(t)
            - at_basis("be", self.interest_on_cashflows)(t)
            + self.mcev_interest_on_cashflows(t)
        )

    def mcev_profit_before_tax(self, t):
        """Emerging profit at reference forward curve before the profit transfer and tax."""
        return self.mcev_net_cf(t) - self.increase_in_reserves(t) + self.mcev_interest_on_reserve(t)

    def mcev_profit_transfer(self, t):
        """The profit transfer at reference forward curve."""
        return self.mcev_profit_before_tax(t) * self.profit_transfer_rate

    def mcev_tax(self, t):
        """Tax at reference forward curve, after the profit transfer."""
        return (self.mcev_profit_before_tax(t) - self.mcev_profit_transfer(t)) * self.tax_rate

    def mcev_net_profit(self, t):
        """Profit at reference forward curve after the profit transfer and tax."""
        return self.mcev_profit_before_tax(t) - self.mcev_profit_transfer(t) - self.mcev_tax(t)

    def pv_net_profit(self, t):
        """Present value at the start of month `t` of the profits from `t` on (variant A)."""
        return (nxt(self.pv_net_profit, 0.0) + self.mcev_net_profit(t)) / (
            1 + self.reference_forward[t]
        )

    def pvfp(self, t):
        """Present value of future profits at the end of month `t`."""
        return nxt(self.pv_net_profit, 0.0) * (self.policy_month(t) >= 0)

    def pv_premiums_from(self, t):
        """Present value at the start of month `t` of the BE premiums from `t` on (variant B:
        premiums are collected at the start of the month)."""
        return at_basis("be", self.premiums)(t) + nxt(self.pv_premiums_from, 0.0) / (
            1 + self.reference_forward[t]
        )

    def pv_premium(self, t):
        """Present value of future premiums at the end of month `t`."""
        return nxt(self.pv_premiums_from, 0.0) * (self.policy_month(t) >= 0)

    def pv_mcev_net_cf(self, t):
        """Present value at the start of month `t` of the net cashflows from `t` on."""
        return (nxt(self.pv_mcev_net_cf, 0.0) + self.mcev_net_cf(t)) / (
            1 + self.reference_forward[t]
        )

    def bel(self, t):
        """Present value of the net cashflows at the end of month `t`: income positive, so
        profitable business has a positive value here (the liability is its negative)."""
        return nxt(self.pv_mcev_net_cf, 0.0) * (self.policy_month(t) >= 0)

    def bel_pp(self, t):
        """The best estimate liability per policy held: NaN once no life remains (0 / 0),
        which the aggregate skips."""
        return -self.bel(t) / (
            at_basis("be", self.lives_end)(t) + at_basis("be", self.maturities)(t)
        )

    def interest_on_sm(self, t):
        """Interest on opening solvency capital at the reference curve."""
        return prev(self.required_solvency_capital, 0.0) * self.reference_forward[t]

    def tax_interest_on_sm(self, t):
        """Tax on that interest."""
        return self.interest_on_sm(t) * self.tax_rate

    def profit_transfer_interest_on_sm(self, t):
        """The profit transfer on that interest."""
        return self.interest_on_sm(t) * self.profit_transfer_rate

    def coc(self, t):
        """The cost of capital at the reference curve: capital held, less interest, plus
        the tax and profit transfer on the interest."""
        return (
            self.increase_in_solvency_capital(t)
            - self.interest_on_sm(t)
            + self.tax_interest_on_sm(t)
            + self.profit_transfer_interest_on_sm(t)
        )

    def fcc_rate(self, t):
        """The FCC discount rate: the IFRS 17 reference curve read from the policy's own
        month (rate `policy_month - 1`); zero at the valuation instant."""
        return if_(
            (t >= 1) and (self.policy_month(t) >= 1),
            self.ifrs_reference_forward[self.policy_month(t) - 1],
            0.0,
        )

    def pv_coc(self, t):
        """Present value at the start of month `t` of the cost of capital from `t` on."""
        return (nxt(self.pv_coc, 0.0) + self.coc(t)) / (1 + self.fcc_rate(t))

    def fcc(self, t):
        """Frictional cost of capital at the end of month `t`."""
        return nxt(self.pv_coc, 0.0) * (self.policy_month(t) >= 0)
