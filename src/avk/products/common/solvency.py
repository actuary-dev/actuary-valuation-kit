"""Optional factor-based capital on best-estimate cashflows.

- **Part 1** is a percentage of the reserve held.
- **Part 2** is a percentage of the sum at risk: the benefit payable on death over and above the
  reserve already set aside. It stops in the month of maturity.

Reinsurance reduces both, but only down to a floor: the credit is a net-to-gross ratio never
below the product's explicit reinsurance credit floor, so capital cannot be ceded away entirely. The
capital is zero at the valuation instant; its movement and the interest it earns are on the
same opening-balance basis as the reserve.
"""

from avk.model.lang import at_basis, if_, param, prev
from avk.products.common.profit import ProfitRates


class SolvencyCapital(ProfitRates):
    """Part 1 and Part 2 solvency margins, the capital they require and its movement."""

    REQUIRES = (
        "sum_assured",
        "reins_sum_assured",
        "lives_end",
        "be_reserves",
        "gross_reserve_pp",
        "net_reserve_pp",
        "policy_month",
        "term_months",
    )
    part1_factor = param("reserve_capital_factor")
    part2_factor = param("sum_at_risk_capital_factor")
    part1_net_to_gross = param("reserve_reinsurance_credit_floor")
    part2_net_to_gross = param("sum_at_risk_reinsurance_credit_floor")
    solvency_ratio = param("target_capital_ratio")

    def gross_sar(self, t):
        """Sum at risk: the benefit payable on the lives in force less the reserve held,
        never negative."""
        return max(
            self.sum_assured(t) * at_basis("be", self.lives_end)(t) - self.be_reserves(t), 0.0
        )

    def net_sar(self, t):
        """The sum at risk the insurer retains after reinsurance, never negative."""
        return max(
            (self.sum_assured(t) - at_basis("be", self.reins_sum_assured)(t))
            * at_basis("be", self.lives_end)(t)
            - self.be_reserves(t),
            0.0,
        )

    def reserve_credit(self, t):
        """Part 1's reinsurance credit: the reserving basis's net-to-gross reserve ratio,
        1 where there is no gross reserve, between the declared credit floor and 1."""
        return min(
            max(
                min(
                    1.0,
                    if_(
                        at_basis("reserving", self.gross_reserve_pp)(t) != 0,
                        at_basis("reserving", self.net_reserve_pp)(t)
                        / (at_basis("reserving", self.gross_reserve_pp)(t) + 1e-6),
                        1.0,
                    ),
                ),
                self.part1_net_to_gross,
            ),
            1.0,
        )

    def sar_credit(self, t):
        """Part 2's reinsurance credit: the net-to-gross sum-at-risk ratio, 1 where nothing is
        at risk, at most 1 and never below the declared credit floor."""
        return max(
            min(
                1.0,
                if_(self.gross_sar(t) != 0, self.net_sar(t) / (self.gross_sar(t) + 1e-6), 1),
            ),
            self.part2_net_to_gross,
        )

    def part1_sm(self, t):
        """Part 1: the reserve-based margin."""
        return (
            self.be_reserves(t) * self.part1_factor * self.reserve_credit(t) * self.solvency_ratio
        )

    def part2_sm(self, t):
        """Part 2: the sum-at-risk margin, until the month of maturity."""
        return (
            self.gross_sar(t)
            * self.part2_factor
            * self.sar_credit(t)
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
        return prev(self.required_solvency_capital, 0.0) * self.expected_return[t] * (t > 0)
