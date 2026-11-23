"""Credit Life valuation formulas.

All best-estimate output columns use `_BE`. Flat annual mortality is
loaded from required basis inputs. Reserves reuse PolicyReserves
once, overriding only CREDIT_LIFE epsilon and statutory floors.
"""

from avk.model.lang import (
    Component,
    LoanLinkedProduct,
    at_basis,
    by_basis,
    clip,
    curve,
    fma,
    if_,
    int_axis,
    keymap,
    nxt,
    override,
    param,
    prev,
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


class CreditLifeRates(CaseShocks):
    # Validated strictly, but the support component supplies the reserving loading.
    mad_mortality = param("prudent_margin_mortality")
    mortality = table(
        "mortality",
        axes=(
            int_axis("age", below="error", above="clamp"),
            keymap("Gender_Code", unknown="error", above="error"),
        ),
    )
    support = by_basis(
        reserving=table(
            "mortality_loadings_credit_life/reserving",
            axes=(
                int_axis("age", below="error", above="clamp"),
                keymap("Support_Code", unknown="error", above="error"),
            ),
        ),
        be=table(
            "mortality_loadings_credit_life/be",
            axes=(
                int_axis("age", below="error", above="clamp"),
                keymap("Support_Code", unknown="error", above="error"),
            ),
        ),
    )
    flat_mortality = by_basis(
        reserving=param("flat_mortality_reserving"), be=param("flat_mortality_be")
    )
    mad_lapse = by_basis(reserving=param("prudent_margin_lapse"), be=0.0)
    persistency = table(
        "lapse_rates_credit_life",
        value="Lapse Rate",
        axes=(
            int_axis("policy_year", below="clamp", above="clamp"),
            keymap("Distribution_Channel", unknown="error", above="error"),
        ),
    )
    reinsurance_mortality = table(
        "reinsurance_mortality_credit_life",
        axes=(
            int_axis("age", below="error", above="clamp"),
            keymap("Gender_Code", unknown="error", above="error"),
        ),
    )

    def policy_month(self, t):
        """Inclusive calendar months, no day adjustment."""
        return self.policy.Duration_in_Months + t

    def policy_year(self, t):
        """Policy year starting at one."""
        return (self.policy_month(t) - 1) // 12 + 1

    def age(self, t):
        """Entry age plus complete policy years."""
        return self.policy.Age_at_Policy_Start + (self.policy_month(t) - 1) // 12

    def term_months(self, t):
        """Positive term truncated to integer months."""
        return (self.policy.Policy_Term * 12) // 1

    def maturity(self, t):
        """All survivors exit at maturity."""
        return self.policy_month(t) == self.term_months(t)

    def mortality_rate(self, t):
        """Support already carries reserving loading; MAD mortality is not applied again."""
        return if_(
            self.policy.Mortality_Flag == 0,
            self.flat_mortality,
            min(
                clip(
                    (self.mortality[self.age(t), self.policy.Gender_Code] + self.mortality_add[t])
                    * self.mortality_mult[t],
                    0.0,
                    1.0,
                )
                * self.support[self.age(t), self.policy.Support_Code],
                1.0,
            ),
        )

    def monthly_mortality(self, t):
        """Monthly mortality is zero before the loan starts."""
        return (1 - (1 - self.mortality_rate(t)) ** (1 / 12)) * (self.policy_month(t) > 0)

    def q(self, t):
        """No mortality decrement at the valuation instant."""
        return self.monthly_mortality(t) * (t > 0)

    def monthly_lapse(self, t):
        """CREDIT_LIFE lapses each month, including before the loan starts."""
        return 1 - (
            1
            - clip(
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
            * (1 + self.mad_lapse)
        ) ** (1 / 12)

    def w(self, t):
        """No lapse decrement at the valuation instant."""
        return (
            self.monthly_lapse(t)
            * (t > 0)
            * if_(self.lapses_after_payment_term, 1.0, self.policy_month(t) <= 1)
        )

    def reins_rate(self, t):
        """Use the credit-life reinsurance table, cap at 1 and mask months before inception."""
        return (
            1
            - (
                1
                - clip(
                    (
                        self.reinsurance_mortality[self.age(t), self.policy.Gender_Code]
                        + self.mortality_add[t]
                    )
                    * self.mortality_mult[t],
                    0.0,
                    1.0,
                )
            )
            ** (1 / 12)
        ) * (self.policy_month(t) > 0)


class LoanCover(Component):
    REQUIRES = ("policy_month",)

    def loan_balance(self, t):
        """Use outstanding principal and the remaining payment holiday; accrue from inception."""
        return if_(
            t == 0,
            if_(self.policy.Reducing_SA == 1, self.policy.loan_os, self.policy.Loan_Amount),
            if_(
                self.policy.Reducing_SA == 1,
                max(
                    fma(
                        prev(self.loan_balance, self.policy.loan_os),
                        1
                        + self.policy.Interest_Rate
                        / 12
                        * self.policy.Interest_Accrue
                        * (self.policy_month(t) >= 1),
                        -self.policy.EMI_amount
                        * (t >= self.policy.Moratorium_Period_ind)
                        * (self.policy_month(t) >= 1),
                    ),
                    0.0,
                ),
                self.policy.Loan_Amount,
            ),
        )

    def sum_assured(self, t):
        """Required right shift, zero at month zero."""
        return prev(self.loan_balance, 0.0)


class CreditLifeCashflows(CaseShocks):
    def coverage_units(self, t):
        """Outstanding insured cover on closing best-estimate lives."""
        return at_basis("be", self.sum_assured)(t) * at_basis("be", self.lives_end)(t) * (t > 0)

    REQUIRES = (
        "lives_begin",
        "lives_end",
        "deaths",
        "lapses",
        "policy_month",
        "policy_year",
        "term_months",
        "sum_assured",
    )
    commission = table(
        "commissions_credit_life",
        value="Commission Rates",
        axes=(
            int_axis("policy_year", below="clamp", above="clamp"),
            keymap("Distribution_Channel", unknown="error", above="error"),
        ),
    )
    mad_expense = by_basis(reserving=param("prudent_margin_expense"), be=0.0)
    inflation = param("Inflation")

    def modal_factor(self, t):
        """Single-pay CREDIT_LIFE has no modal loading."""
        return 1.0

    def commission_rate(self, t):
        """Commission only at policy inception."""
        return self.commission[self.policy_year(t), self.policy.Distribution_Channel] * (
            self.policy_month(t) == 1
        )

    def premiums(self, t):
        """Single premium in policy month 1, including step 0 when it falls in that month."""
        return (
            self.policy.Premium
            * (self.policy.Mode == 1)
            * (self.policy_month(t) == 1)
            * self.lives_begin(t)
        )

    def commissions(self, t):
        """Commission on received premiums."""
        return self.premiums(t) * self.commission_rate(t)

    def initial_expense(self, t):
        """Initial expense rates use the shifted month-one sum assured, resolved in preparation."""
        return (
            (
                (
                    (self.policy.initial_fixed_expense_rate + self.expense_add[t])
                    * self.expense_mult[t]
                )
                + (self.policy.initial_percent_prem_expense_rate * self.expense_mult[t])
                * self.policy.Premium
                + (self.policy.initial_percent_sa_expense_rate * self.expense_mult[t])
                * self.policy.loan_os
            )
            * self.lives_begin(t)
            * (self.policy_month(t) == 1)
        )

    def renewal_expenses(self, t):
        """Fixed maintenance expense applies after policy month one."""
        return (
            ((self.policy.renewal_fixed_expense + self.expense_add[t]) * self.expense_mult[t])
            / 12
            * self.inflation_factor(t)
            * (1 + self.mad_expense)
            * self.lives_begin(t)
            * (self.policy_month(t) > 1)
        )

    def claim_expenses(self, t):
        """Percentage of current cover on death."""
        return (
            self.sum_assured(t)
            * ((self.policy.claim_expense_percent * self.expense_mult[t]) / 100)
            * self.deaths(t)
        )

    def death_benefits(self, t):
        """Cover paid on death up to maturity."""
        return (self.sum_assured(t) * (self.policy_month(t) <= self.term_months(t))) * self.deaths(
            t
        )

    def sv(self, t):
        """Half premium times remaining-term and reducing-cover proportions."""
        return (
            0.5
            * self.policy.Premium
            * max(0.0, self.term_months(t) - self.policy_month(t))
            / self.term_months(t)
            * min(self.sum_assured(t) / self.policy.Loan_Amount, 1.0)
        )

    def surrender_benefits(self, t):
        """Surrender value paid on lapse."""
        return self.sv(t) * self.lapses(t)

    def premium_income(self, t):
        """Family premium port."""
        return self.premiums(t)

    def acquisition_cost(self, t):
        """Family acquisition port."""
        return self.commissions(t) + self.initial_expense(t)

    def expense_outgo(self, t):
        """Family maintenance port."""
        return self.renewal_expenses(t)

    def benefit_outgo(self, t):
        """Family benefit port."""
        return self.death_benefits(t) + self.surrender_benefits(t)


class CreditLifeNetCashflows(NetCashflows):
    @override
    def net_cashflows(self, t):
        """Retain CREDIT_LIFE's unmasked month-zero premium/maintenance cashflow."""
        return -(
            self.premium_income(t)
            - self.acquisition_cost(t)
            - self.expense_outgo(t)
            - self.claim_expenses(t)
            - self.benefit_outgo(t)
            + self.interest_on_cashflows(t)
        )


class CreditLifeReserves(PolicyReserves, CaseShocks):
    REQUIRES = (*PolicyReserves.REQUIRES, "sv", "policy_month", "term_months")
    max_upr_term = param("Max term for which UPR to be held (months)")

    @override
    def reserve_lives(self, t):
        """CREDIT_LIFE adds 1e-8, rather than a denominator floor."""
        return self.lives_end(t) + self.maturities(t) + 1e-8

    def upr(self, t):
        """Commission uses the first projection month, without decrement weighting; the
        cover-based initial expense takes the case expense multiplier in force that month."""
        return (
            max(
                0.0,
                (
                    self.policy.Premium
                    - self.policy.upr_commission
                    - (self.policy.initial_percent_sa_expense_rate * self.expense_mult[t])
                    * self.policy.Loan_Amount
                )
                * (self.term_months(t) - self.policy_month(t) + 0.5)
                / self.term_months(t),
            )
            * (t > 0)
            * (self.term_months(t) <= self.max_upr_term)
        )

    @override
    def gross_reserve_amount(self, t):
        """Gross held amount including surrender and UPR floors, masked at zero."""
        return max(
            self.discounted_net_cf(t),
            0.0,
            self.upr(t) * self.eligible_reserve_lives(t),
            self.sv(t) * self.eligible_reserve_lives(t),
        ) * (t > 0)

    @override
    def net_reserve_amount(self, t):
        """Net held amount including surrender and UPR floors."""
        return max(
            self.discounted_cf_with_reins(t),
            0.0,
            self.upr(t) * self.eligible_reserve_lives(t),
            self.sv(t) * self.eligible_reserve_lives(t),
        )

    @override
    def gross_reserve_pp(self, t):
        """UPR and surrender floors, gross zero at valuation instant."""
        return max(
            self.sv(t),
            max(self.upr(t), max(self.discounted_net_cf(t) / self.reserve_lives(t), 0.0)),
        ) * (t > 0)

    @override
    def ceding_reserve_pp(self, t):
        """The gross reserve with its floors, without the step-zero mask: at month 0 the
        reserve held at the valuation date, which the cession nets off."""
        return max(
            self.sv(t),
            max(self.upr(t), max(nxt(self.pv_net_cashflows, 0.0) / self.reserve_lives(t), 0.0)),
        )

    @override
    def net_reserve_pp(self, t):
        """Same statutory floors on net reserves, without gross's step-zero mask."""
        return max(
            self.sv(t),
            max(self.upr(t), max(self.discounted_cf_with_reins(t) / self.reserve_lives(t), 0.0)),
        )


class CreditLifeReinsurance(SurplusReinsurance):
    retention_proportion = param("Reinsurance Retention Limit proportion")

    @override
    def reins_sum_assured(self, t):
        """CREDIT_LIFE cedes only the retained proportion of surplus cover."""
        return (
            max(
                self.sum_assured(t)
                - self.retention
                - prev(at_basis("reserving", self.ceding_reserve_pp), 0.0),
                0.0,
            )
            * self.retention_proportion
        )

    @override
    def net_cf_with_reinsurance(self, t):
        """Retain unmasked CREDIT_LIFE cashflow at month zero."""
        return (
            at_basis("reserving", self.net_cashflows)(t)
            + self.reins_premiums(t)
            - self.reins_recoveries(t)
        )


class CreditLifeProfit(ProfitSignature):
    REQUIRES = (*ProfitSignature.REQUIRES, "policy_month", "term_months")

    def policy_mask(self, t):
        """The CREDIT_LIFE interest mask includes start and maturity boundaries."""
        return (self.policy_month(t) > 0) and (self.policy_month(t) <= self.term_months(t))

    @override
    def interest_on_reserves(self, t):
        """Opening reserve earns shifted ROI only while the policy is covered."""
        return prev(self.be_reserves, 0.0) * self.expected_return[t] * (t > 0) * self.policy_mask(t)


class CreditLifeSolvency(SolvencyCapital):
    REQUIRES = (*SolvencyCapital.REQUIRES, "maturities", "policy_mask")
    max_upr_term = param("Max term for which UPR to be held (months)")

    def sar_lives(self, t):
        """Short UPR terms retain maturity lives in sum at risk (:1392–1404)."""
        return at_basis("be", self.lives_end)(t) + at_basis("be", self.maturities)(t) * (
            self.term_months(t) <= self.max_upr_term
        )

    @override
    def gross_sar(self, t):
        """CREDIT_LIFE sum at risk includes eligible maturity lives."""
        return max(self.sum_assured(t) * self.sar_lives(t) - self.be_reserves(t), 0.0)

    @override
    def net_sar(self, t):
        """Retained CREDIT_LIFE sum at risk after reinsurance."""
        return max(
            (self.sum_assured(t) - at_basis("be", self.reins_sum_assured)(t)) * self.sar_lives(t)
            - self.be_reserves(t),
            0.0,
        )

    @override
    def part2_sm(self, t):
        """CREDIT_LIFE's part-2 mask includes the maturity month (:1446–1457)."""
        return (
            self.gross_sar(t)
            * self.part2_factor
            * self.sar_credit(t)
            * self.solvency_ratio
            * (self.policy_month(t) <= self.term_months(t))
        )

    @override
    def interest_on_solvency_capital(self, t):
        """Opening capital earns shifted ROI inside CREDIT_LIFE's policy mask."""
        return (
            prev(self.required_solvency_capital, 0.0)
            * self.expected_return[t]
            * (t > 0)
            * self.policy_mask(t)
        )


class CreditLifeMarketValue(MarketConsistentValue):
    @override
    def pvfp(self, t):
        """CREDIT_LIFE reports the shifted PV without Term's pre-start mask (:1543)."""
        return nxt(self.pv_net_profit, 0.0)

    @override
    def pv_premium(self, t):
        """CREDIT_LIFE's unmasked shifted premium PV (:1544)."""
        return nxt(self.pv_premiums_from, 0.0)

    @override
    def bel(self, t):
        """CREDIT_LIFE's unmasked shifted net cashflow PV (:1545)."""
        return nxt(self.pv_mcev_net_cf, 0.0)


class CreditLifeIfrsValue(IfrsBestEstimate):
    """Credit-life IFRS best-estimate and expense columns for the valuation run."""

    REQUIRES = (*IfrsBestEstimate.REQUIRES, "inflation_factor")

    inflation = param("Inflation")

    def ifrs_fixed_block_rate(self, t):
        """Delayed schedule's first nonzero rate per projection block, carried (:1465–1490)."""
        return if_(
            t >= 2,
            if_(
                self.ifrs_fixed_schedule[12 * (1 + (t - 2) // 12)] != 0,
                self.ifrs_fixed_schedule[12 * (1 + (t - 2) // 12)],
                prev(self.ifrs_fixed_block_rate, 0.0),
            ),
            0.0,
        )

    def ifrs_fixed_undec(self, t):
        """Step 1 retains year-one annual amount; from step 2 express the carry monthly."""
        return if_(t == 1, self.ifrs_fixed_schedule[0], self.ifrs_fixed_block_rate(t) / 12)

    @override
    def ifrs_renewal_fixed(self, t):
        """First two steps undecremented; later monthly fixed expense on opening BE lives."""
        return (
            (self.ifrs_fixed_undec(t) + self.expense_add[t] * if_(t == 1, 1.0, 1.0 / 12) * (t > 0))
            * if_(t < 2, 1.0, at_basis("be", self.lives_begin)(t))
            * self.expense_mult[t]
            * self.ifrs_case_price(t)
        )

    @override
    def ifrs_premium_rate(self, t):
        """Single-pay CREDIT_LIFE keeps the policy-month schedule, without monthly-premium carry."""
        return self.ifrs_premium_schedule[self.policy_month(t) - 1]

    @override
    def ifrs_stressed_expenses(self, t):
        """Explicit stressed fixed and premium costs; commission cancels at the locked curve."""
        return at_basis("be", self.commissions)(t) + (
            self.ifrs_renewal_expenses(t) - at_basis("be", self.commissions)(t)
        ) * self.ifrs_stress_expense * self.ifrs_stress_inflation_factor(t)


class CreditLife(
    CreditLifeRates,
    LoanCover,
    LivesAndExits,
    CreditLifeCashflows,
    CreditLifeNetCashflows,
    CreditLifeReserves,
    CreditLifeReinsurance,
    CreditLifeProfit,
    CreditLifeSolvency,
    CreditLifeMarketValue,
    CreditLifeIfrsValue,
    LoanLinkedProduct,
):
    CODE, LABEL, BASES = "CREDIT_LIFE", "Group credit life", ("reserving", "be")
    FIELDS = (
        "Policy_Term",
        "Premium",
        "Loan_Amount",
        "EMI_amount",
        "Interest_Rate",
        "Mode",
        "Premium_Frequency",
        "Age_at_Policy_Start",
        "Moratorium_Period_ind",
        "Interest_Accrue",
        "Reducing_SA",
        "Mortality_Flag",
        "Gender_Code",
        "Smoking_Status_Code",
        "Support_Code",
        "Duration_in_Months",
        "Distribution_Channel",
        "loan_os",
        "upr_commission",
        "initial_fixed_expense_rate",
        "initial_percent_prem_expense_rate",
        "initial_percent_sa_expense_rate",
        "renewal_fixed_expense",
        "claim_expense_percent",
    )
    initial_expense_rates = table("expenses_credit_life", axes=())
    renewal_expense_rates = table("expenses_credit_life/renewal", axes=())
    interest_curve = curve("interest_rates")
    ifrs_interest_curve = curve("ifrs17_interest_rates")


class IfrsCreditLife(IfrsMeasurement, CreditLife):
    """Credit life plus the shared IFRS measurement adapters."""
