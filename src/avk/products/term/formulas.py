"""Level term assurance (TERM). One method = one projected column.

Column map: 138 columns (74 shared, 64 basis-specific), six passes. Rate
components own direct/reinsurance mortality and lapse; LivesAndExits owns the single
lives recursion; TermCashflows owns modal factor, premium_due and premium_pp and the
cashflow ports; common components own net cashflows, reinsurance, reserves, profit,
solvency capital, MCEV present values and the IFRS BEL group. premium_pp is the reusable
instalment premium port for ReturnOfPremium, factored from the unchanged premiums rule.
Generate the current column map with `avk compile TERM --explain`.

Term's own formulas are its monthly rates (`TermDecrementRates`, `TermReinsuranceRate`) and its
cashflow items (`TermCashflows`, which implements the protection family's ports); the shared
components project lives, the net cashflow, the reserves, the reinsurance, the profit
signature, solvency capital, the market-consistent present values and the IFRS 17 BEL group.
All bindings used by the current Valuation, StressCapital and IFRS17 compositions are checked
before projection.
"""

from avk.model.lang import (
    ProtectionProduct,
    at_basis,
    by_basis,
    clip,
    curve,
    if_,
    int_axis,
    keymap,
    param,
    scen,
    table,
)
from avk.products.common.case_shocks import CaseShocks
from avk.products.common.cashflows import NetCashflows
from avk.products.common.ifrs17 import IfrsMeasurement
from avk.products.common.ifrs_bel import IfrsBestEstimate
from avk.products.common.lives import LivesAndExits
from avk.products.common.mcev import MarketConsistentValue
from avk.products.common.profit import ProfitSignature
from avk.products.common.reinsurance import SurplusReinsurance
from avk.products.common.reserves import PolicyReserves
from avk.products.common.solvency import SolvencyCapital


class TermDecrementRates(CaseShocks):
    """Monthly mortality and lapse rates and the maturity month.

    The reserving basis loads each annual rate by (1 + MAD). The BE basis uses the
    rate without a margin.
    """

    mortality = table(
        "mortality",
        axes=(
            int_axis("age", below="error", above="clamp"),
            keymap("Gender_Code", unknown="error", above="error"),
        ),
    )
    persistency = table(
        "lapse_rates_term",
        value="Lapse Rate",
        axes=(
            int_axis("policy_year", below="clamp", above="clamp"),
            keymap("Distribution_Channel", unknown="error", above="error"),
        ),
    )
    mad_mortality = by_basis(reserving=param("prudent_margin_mortality"), be=0.0)
    mad_lapse = by_basis(reserving=param("prudent_margin_lapse"), be=0.0)

    def policy_month(self, t):
        """Months since the policy started: those already elapsed plus the projection month."""
        return self.policy.Duration_in_Months + t

    def policy_year(self, t):
        """Policy year, from 1."""
        return (self.policy_month(t) - 1) // 12 + 1

    def age(self, t):
        """Age: entry age plus completed policy years."""
        return self.policy.Age_at_Entry + (self.policy_month(t) - 1) // 12

    def mortality_rate(self, t):
        """Annual mortality: table rate times EMR, from policy month 1, loaded by (1 + MAD),
        and a probability, so never above 1."""
        return min(
            clip(
                (self.mortality[self.age(t), self.policy.Gender_Code] + self.mortality_add[t])
                * self.mortality_mult[t],
                0.0,
                1.0,
            )
            * self.policy.EMR
            * (self.policy_month(t) > 0)
            * (1 + self.mad_mortality),
            1.0,
        )

    def q(self, t):
        """Monthly mortality, decremented rather than divided; none at the valuation instant."""
        return (1 - (1 - self.mortality_rate(t)) ** (1 / 12)) * (t > 0)

    def lapse_due(self, t):
        """1 in a month when a premium falls due: lapses are tested only then."""
        return (
            (self.policy_month(t) + 1) % (12 / self.policy.Premium_Frequency)
            == if_(self.policy.Premium_Frequency == 12, 0, 1)
        ) * (self.policy_month(t) > 0)

    def lapse_rate(self, t):
        """Annual lapse rate on a premium due month, loaded by (1 + MAD)."""
        return (
            clip(
                (
                    self.persistency[self.policy_year(t), self.policy.Distribution_Channel]
                    + self.lapse_add[t]
                )
                * self.lapse_mult[t],
                max(
                    0.0,
                    self.persistency[self.policy_year(t), self.policy.Distribution_Channel]
                    - self.lapse_maximum_decrease[t],
                ),
                1.0,
            )
            * self.lapse_due(t)
            * (1 + self.mad_lapse)
            * if_(
                self.lapses_after_payment_term,
                1.0,
                self.policy_month(t) <= self.policy.Premium_Payment_Term * 12,
            )
        )

    def w(self, t):
        """Monthly lapse, with the premium frequency as the exponent; none at month 0."""
        return (1 - (1 - self.lapse_rate(t)) ** (1 / self.policy.Premium_Frequency)) * (t > 0)

    def term_months(self, t):
        """The policy term in months."""
        return self.policy.Policy_Term * 12

    def maturity(self, t):
        """1 in the month the policy reaches the end of its term."""
        return self.policy_month(t) == self.term_months(t)


class TermReinsuranceRate(CaseShocks):
    """The reinsurer's monthly death rate, on its own table and EMR, with no margin."""

    REQUIRES = ("age", "policy_month")
    reinsurance_mortality = table(
        "reinsurance_mortality",
        axes=(
            int_axis("age", below="error", above="clamp"),
            keymap("Gender_Code", unknown="error", above="error"),
        ),
    )

    def reins_mortality_rate(self, t):
        """Annual reinsurance death rate: table rate times the reinsurance EMR, from policy
        month 1, never above 1."""
        return min(
            clip(
                (
                    self.reinsurance_mortality[self.age(t), self.policy.Gender_Code]
                    + self.mortality_add[t]
                )
                * self.mortality_mult[t],
                0.0,
                1.0,
            )
            * self.policy.reins_EMR
            * (self.policy_month(t) > 0),
            1.0,
        )

    def reins_rate(self, t):
        """Monthly reinsurance death rate, decremented rather than divided."""
        return 1 - (1 - self.reins_mortality_rate(t)) ** (1 / 12)


class TermCashflows(CaseShocks):
    """Premiums, commissions, expenses and benefits for the lives in force, and the protection
    family's ports. Every item is an
    expected amount for the projected lives; month 0 carries none."""

    REQUIRES = ("lives_begin", "lives_end", "deaths", "policy_month", "policy_year")
    commission = table(
        "commissions_term",
        value="Commission Rates",
        axes=(
            int_axis("policy_year", below="clamp", above="clamp"),
            keymap("Distribution_Channel", unknown="error", above="error"),
        ),
    )
    modal_factors = table(
        "premium_frequency_factors",
        axes=(keymap("Premium_Frequency", unknown="error", above="error"),),
    )
    mad_expense = by_basis(reserving=param("prudent_margin_expense"), be=0.0)
    inflation = param("Inflation")

    def sum_assured(self, t):
        """The level sum assured."""
        return self.policy.Sum_Assured

    def modal_factor(self, t):
        """The loading of an instalment paid more often than yearly."""
        return self.modal_factors[self.policy.Premium_Frequency]

    def premium_due(self, t):
        """1 in a month a premium falls due: every month for monthly premiums, otherwise the
        first month of each payment period; none at the valuation instant and none after the
        premium payment term."""
        return (
            if_(
                self.policy.Premium_Frequency == 12,
                1,
                self.policy_month(t) % (12 / self.policy.Premium_Frequency) == 1,
            )
            * (t > 0)
            * (self.policy_month(t) <= self.policy.Premium_Payment_Term * 12)
        )

    def premium_pp(self, t):
        """The instalment premium per opening life, before the payment indicator."""
        return self.policy.Premium_Amount * self.modal_factor(t)

    def premiums(self, t):
        """Instalment premiums falling due, for the opening lives."""
        return (self.premium_pp(t) * self.premium_due(t)) * self.lives_begin(t)

    def commission_rate(self, t):
        """Commission rate by policy year and channel."""
        return self.commission[self.policy_year(t), self.policy.Distribution_Channel]

    def commissions(self, t):
        """Commission on the premiums collected."""
        return self.premiums(t) * self.commission_rate(t)

    def initial_expense(self, t):
        """A fixed amount plus shares of the premium and the sum assured (rates interpolated
        by sum assured), once, in policy month 1: never for policies already in force."""
        return (
            (
                (
                    (self.policy.initial_fixed_expense_rate + self.expense_add[t])
                    * self.expense_mult[t]
                )
                + (self.policy.initial_percent_prem_expense_rate * self.expense_mult[t])
                * self.policy.Premium_Amount
                + (self.policy.initial_percent_sa_expense_rate * self.expense_mult[t])
                * self.policy.Sum_Assured
            )
            * (self.policy_month(t) == 1)
            * self.lives_begin(t)
            * (t > 0)
        )

    def renewal_expenses(self, t):
        """The annual renewal expense spread monthly from policy year 2, inflated from the
        valuation date and loaded by the expense margin on the reserving basis."""
        return (
            (
                (
                    (
                        (self.policy.renewal_fixed_expense + self.expense_add[t])
                        * self.expense_mult[t]
                    )
                    + self.policy.renewal_percent_prem_expense_rate
                    * self.expense_mult[t]
                    * self.policy.Premium_Amount
                    * if_(
                        self.renewal_premium_expense_after_payment_term,
                        1.0,
                        self.policy_month(t) <= self.policy.Premium_Payment_Term * 12,
                    )
                )
                / 12
            )
            * self.inflation_factor(t)
            * (1 + self.mad_expense)
            * self.lives_begin(t)
            * (self.policy_year(t) > 1)
            * (t > 0)
        )

    def claim_expenses(self, t):
        """The cost of settling each death claim, a percentage of the sum assured."""
        return (
            self.policy.Sum_Assured
            * ((self.policy.claim_expense_percent * self.expense_mult[t]) / 100)
            * self.deaths(t)
            * (t > 0)
        )

    def death_benefits(self, t):
        """The sum assured on each death."""
        return self.policy.Sum_Assured * self.deaths(t) * (t > 0)

    def surrender_benefits(self, t):
        """Level term has zero surrender value."""
        return 0.0

    def premium_income(self, t):
        """The protection family's premium income port."""
        return self.premiums(t)

    def acquisition_cost(self, t):
        """The acquisition cost port: commissions and the initial expense."""
        return self.commissions(t) + self.initial_expense(t)

    def expense_outgo(self, t):
        """The maintenance expense port: renewal expenses."""
        return self.renewal_expenses(t)

    def benefit_outgo(self, t):
        """The benefit outgo port: death and surrender benefits."""
        return self.death_benefits(t) + self.surrender_benefits(t)

    def annualised_premium(self, t):
        """The year's premium: the best-estimate instalment falling due, without its modal
        loading, times the instalments a year (the seriatim file reads it at step 1, so a
        month with no premium due, or past the payment term, shows 0)."""
        return (
            at_basis("be", self.premiums)(t) / self.modal_factor(t)
        ) * self.policy.Premium_Frequency


class Term(
    TermDecrementRates,
    LivesAndExits,
    TermCashflows,
    TermReinsuranceRate,
    NetCashflows,
    SurplusReinsurance,
    PolicyReserves,
    ProfitSignature,
    SolvencyCapital,
    MarketConsistentValue,
    IfrsBestEstimate,
    ProtectionProduct,
):
    def coverage_units(self, t):
        """Level cover on surviving best-estimate lives; no service at month zero."""
        return self.policy.Sum_Assured * at_basis("be", self.lives_end)(t) * (t > 0)

    CODE, LABEL, BASES = "TERM", "Term assurance", ("reserving", "be")
    FIELDS = (
        "Policy_Term",
        "Premium_Payment_Term",
        "Sum_Assured",
        "Premium_Amount",
        "Premium_Frequency",
        "Distribution_Channel",
        "Age_at_Entry",
        "Gender_Code",
        "Smoking_Status_Code",
        "EMR",
        "reins_EMR",
        "Policy_Status",
        "Duration_in_Months",
        "initial_fixed_expense_rate",
        "initial_percent_prem_expense_rate",
        "initial_percent_sa_expense_rate",
        "renewal_fixed_expense",
        "renewal_percent_prem_expense_rate",
        "claim_expense_percent",
    )
    # Declared for later sessions' formulas; validated by `avk check` meanwhile.
    support = table(
        "mortality_loadings_term",
        axes=(keymap("Smoking_Status_Code", unknown="error", above="error"),),
    )
    reins_support = table(
        "reinsurance_mortality_loadings_term",
        axes=(keymap("Smoking_Status_Code", unknown="error", above="error"),),
    )
    initial_expense_rates = table("expenses_term", axes=())
    renewal_expense_rates = table("expenses_term/renewal", axes=())
    ifrs_initial_expense_rates = table("ifrs17_initial_expenses_term", axes=())
    interest_curve = curve("interest_rates")
    ifrs_curve = curve("ifrs17_interest_rates")
    ifrs_current = scen("ifrs_current")
    use_male = param("Use Male Mortality for Female")
    setback = param("Setback in years")
    reserving_method = param("Reserving Method")
    retention_proportion = param("Reinsurance Retention Limit proportion")
    operational_premium = param("Operational Risk Charge - Earned Premium")
    operational_provision = param("Operational risk charge - Technical provisions")
    cost_capital = param("Cost of Capital Charge")
    sa_multiplier = param("Minimum SA Multiplier")
    expense_sensitivity = param("Capital Expense Multiplier")
    expense_inflation = param("Capital Expense Inflation Addition")
    mass_lapse = param("Mass Lapse Stress Factor")
    catastrophe = param("Catastrophe Risk Factor")
    diversification = param("Diversification Floor Factor")
    ifrs_renewal_multiplier = param("IFRS17 Multiplier Renewal Expenses")
    ifrs_renewal_addition = param("IFRS17 Addition Renewal Expenses")
    ifrs_ra = param("IFRS 17 RA Ratio")
    ifrs_ri_ra = param("IFRS 17 RI RA Ratio")
    ifrs_commission_multiplier = param("IFRS17 Multiplier Initial Commission")


class IfrsTerm(IfrsMeasurement, Term):
    """Term plus the shared IFRS17 measurement port adapters."""
