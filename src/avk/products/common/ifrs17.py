"""Shared measurement adapters over family ports and the corrected IFRS expense component.

The existing IfrsBestEstimate owns the IFRS expense basis: its acquisition and maintenance
columns adapt acquisition_cost/expense_outgo to the declared IFRS schedules. Never duplicate
those schedules in a product or in the measurement. Discounting and group balances are measures.
"""

from avk.model.lang import Component, at_basis, if_, scen


class IfrsMeasurement(Component):
    ifrs_current = scen("ifrs_current")
    REQUIRES = (
        "premium_income",
        "benefit_outgo",
        "coverage_units",
        "reins_premiums",
        "reins_recoveries",
        "ifrs_initial_expense",
        "ifrs_renewal_expenses",
        "ifrs_claim_expense",
        "commissions",
        "lives_begin",
        "policy_month",
        "inflation_factor",
    )

    def measurement_premiums(self, t):
        """Direct premiums through the family port on the best-estimate basis."""
        return at_basis("be", self.premium_income)(t)

    def measurement_claims(self, t):
        """Direct benefits through the family port on the best-estimate basis."""
        return at_basis("be", self.benefit_outgo)(t)

    def measurement_acquisition(self, t):
        """IFRS initial expenses adjusted for measurement inflation."""
        return self.ifrs_initial_expense(t) * self.measurement_inflation_adjustment(t)

    def measurement_inflation_adjustment(self, t):
        """Case price-level change relative to the already-declared IFRS schedules."""
        return if_(
            t > 0,
            self.inflation_factor(t) / (1 + self.inflation) ** ((t - 1) / 12),
            1.0,
        )

    def measurement_maintenance(self, t):
        """Shared case-adjusted IFRS renewal expense, including unstressed commission once."""
        return self.ifrs_renewal_expenses(t)

    def measurement_claim_expense(self, t):
        """Shared case-adjusted settlement expense, with no second shock."""
        return self.ifrs_claim_expense(t)

    def measurement_coverage(self, t):
        """Insurance service through the family's coverage-units port."""
        return self.coverage_units(t)

    def measurement_ri_premiums(self, t):
        """Premiums on the reinsurance held."""
        return at_basis("be", self.reins_premiums)(t)

    def measurement_ri_recoveries(self, t):
        """Recoveries on the reinsurance held."""
        return at_basis("be", self.reins_recoveries)(t)
