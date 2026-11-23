"""A named Term composition and a reusable return-of-premium benefit."""

from avk.model.lang import Component, override
from avk.products.term.formulas import Term


class LevelTermBenefit(Component):
    """A term benefit column: amount of cover times expected deaths."""

    REQUIRES = ("deaths",)

    def insured_death_benefit(self, t):
        """Pay the level sum assured on deaths after the valuation instant."""
        return self.policy.Sum_Assured * self.deaths(t) * (t > 0)


class MyTerm(LevelTermBenefit, Term):
    """Join our benefit component to the existing Term composition."""

    @override
    def death_benefits(self, t):
        """Connect the new component to Term's benefit cashflow port."""
        return self.insured_death_benefit(t)

    CODE = "TUTORIAL_TERM"
    LABEL = "My term assurance"


class ReturnOfPremium(Component):
    """Return all contractual premiums to surviving policies at maturity."""

    REQUIRES = ("maturities", "death_benefits", "surrender_benefits")

    def returned_premiums(self, t):
        """Annual premium times payment years, paid only to maturing lives."""
        return (
            self.policy.Premium_Amount
            * self.policy.Premium_Payment_Term
            * self.maturities(t)
            * (t > 0)
        )


class ReturnTerm(ReturnOfPremium, MyTerm):
    """Add the benefit to the same Term cashflow and reserve components."""

    @override
    def benefit_outgo(self, t):
        """Death and surrender benefits plus the maturity refund."""
        return self.death_benefits(t) + self.surrender_benefits(t) + self.returned_premiums(t)

    CODE = "TUTORIAL_ROP"
    LABEL = "My return-of-premium term"
