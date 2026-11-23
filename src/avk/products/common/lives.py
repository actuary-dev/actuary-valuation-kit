"""Lives and exits: the survival recursion every decrement-based product shares.

Each policy starts as one life. Each month, deaths come out of opening lives,
lapses come out of the survivors of death, and maturity takes whoever is left.
"""

from avk.model.lang import Component, if_, prev, run_param


class LivesAndExits(Component):
    """Opening lives, deaths, lapses, maturities and closing lives, from the product's monthly
    rates `q` (mortality) and `w` (lapse) and its `maturity` indicator."""

    REQUIRES = ("q", "w", "maturity", "policy_month")
    case_mass_lapse = run_param("case_mass_lapse")

    def lives_begin(self, t):
        """Opening lives: last month's closing lives; one life before the projection starts."""
        return prev(self.lives_end, 1.0)

    def deaths(self, t):
        """Deaths from the opening lives."""
        return self.lives_begin(t) * self.q(t)

    def lapses(self, t):
        """Lapses from the survivors of death; none in a month with no decrement at all."""
        return if_(
            t == 1 and self.policy_month(t) > 0 and self.case_mass_lapse > 0,
            (self.lives_begin(t) - self.deaths(t))
            * (self.w(t) + (1 - self.w(t)) * self.case_mass_lapse),
            if_(self.q(t) + self.w(t) > 0, (self.lives_begin(t) - self.deaths(t)) * self.w(t), 0.0),
        )

    def maturities(self, t):
        """Every remaining life exits in the month the policy reaches the end of its term."""
        return (self.lives_begin(t) - self.deaths(t) - self.lapses(t)) * self.maturity(t)

    def lives_end(self, t):
        """Closing lives, floored at zero."""
        return max(self.lives_begin(t) - self.deaths(t) - self.lapses(t) - self.maturities(t), 0.0)
