"""Factor-based solvency capital for unit-linked business, on each basis's own lives.

- **Part 1** is a factor times the mathematical reserves: the unit reserve plus the non-unit
  reserve held for the basis's lives.
- **Part 2** is a factor times the sum at risk, until the month of maturity.

Variants with a maturity guarantee use the with-guarantee factors. Both parts are scaled by
the target capital ratio. Capital is zero at the valuation instant; its movement and the
interest it earns (at the basis's general fund rate) are on an opening-balance basis.
"""

from avk.model.lang import at_basis, if_, param, prev
from avk.products.unit_linked.gf_interest import GeneralFundInterest


class UnitLinkedCapital(GeneralFundInterest):
    """Part 1 and Part 2 solvency margins, the capital they require and its movement."""

    REQUIRES = (
        "lives_end",
        "maturities",
        "non_unit_reserve_pp",
        "policy_month",
        "sum_at_risk",
        "term_months",
        "unit_reserve",
    )
    reserve_factor_no_guarantee = param("reserve_capital_factor_no_guarantee")
    sar_factor_no_guarantee = param("sar_capital_factor_no_guarantee")
    reserve_factor_guarantee = param("reserve_capital_factor_guarantee")
    sar_factor_guarantee = param("sar_capital_factor_guarantee")
    solvency_ratio = param("target_capital_ratio")

    def guaranteed(self, t):
        """Whether the variant carries an investment (maturity) guarantee."""
        return self.policy.V_gmmb_on == 1

    def reserve_capital_factor(self, t):
        """Part 1's factor, with or without a guarantee."""
        return if_(
            self.guaranteed(t), self.reserve_factor_guarantee, self.reserve_factor_no_guarantee
        )

    def sar_capital_factor(self, t):
        """Part 2's factor, with or without a guarantee."""
        return if_(self.guaranteed(t), self.sar_factor_guarantee, self.sar_factor_no_guarantee)

    def capital_reserves(self, t):
        """The reserving basis's non-unit reserve per policy, held for this basis's lives."""
        return at_basis("reserving", self.non_unit_reserve_pp)(t) * (
            self.lives_end(t) + self.maturities(t)
        )

    def part1_sm(self, t):
        """Part 1: the reserve-based margin."""
        return (
            self.reserve_capital_factor(t)
            * (self.unit_reserve(t) + self.capital_reserves(t))
            * self.solvency_ratio
        )

    def part2_sm(self, t):
        """Part 2: the sum-at-risk margin, until the month of maturity."""
        return (
            self.sar_capital_factor(t)
            * self.sum_at_risk(t)
            * self.solvency_ratio
            * (self.policy_month(t) < self.term_months(t))
        )

    def required_solvency_capital(self, t):
        """Both parts, never negative; none at the valuation instant."""
        return if_(t > 0, max(self.part1_sm(t) + self.part2_sm(t), 0.0), 0.0)

    def increase_in_solvency_capital(self, t):
        """This month's required capital less last month's."""
        return (self.required_solvency_capital(t) - prev(self.required_solvency_capital, 0.0)) * (
            t > 0
        )

    def interest_on_solvency_capital(self, t):
        """Interest earned on the capital held at the start of the month."""
        return prev(self.required_solvency_capital, 0.0) * self.interest_rate[t] * (t > 0)
