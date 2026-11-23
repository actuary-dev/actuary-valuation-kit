"""Shared rider formula components.

Mortality/lapse/calendar and instalment-premium ports extend Term components. The
single LivesAndExits recursion is composed by each product. No Rider_Option reaches
compiled formulas. RiderBase is the shared composition for the CI and disability factories.
"""

from avk.model.lang import (
    Component,
    RiderProduct,
    at_basis,
    by_basis,
    clip,
    curve,
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
from avk.products.common.upr import UnearnedPremiumReserve
from avk.products.term.formulas import Term, TermCashflows


class RiderRates(CaseShocks):
    """Rider mortality, lapse eligibility and a separate table for morbidity."""

    REQUIRES = ("policy_month", "age")
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
        """Day-adjusted elapsed months plus the projection month."""
        return self.policy.Duration_in_Months + t

    def policy_year(self, t):
        """Policy year, from 1."""
        return (self.policy_month(t) - 1) // 12 + 1

    def age(self, t):
        """Entry age plus completed policy years."""
        return self.policy.Age_at_Entry + (self.policy_month(t) - 1) // 12

    def term_months(self, t):
        """Rider term in months."""
        return self.policy.Policy_Term * 12

    def maturity(self, t):
        """All remaining lives mature in the rider's last policy month."""
        return self.policy_month(t) == self.term_months(t)

    def lapse_rate(self, t):
        """Annual lapse rate by policy year/channel on a lapse-due month."""
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
            * (self.lapse_due(t))
            * (1 + self.mad_lapse)
            * if_(
                self.lapses_after_payment_term,
                1.0,
                self.policy_month(t) <= self.policy.Premium_Payment_Term * 12,
            )
        )

    def w(self, t):
        """Monthly lapse rate, with the payment frequency exponent; none at step 0."""
        return (1 - (1 - self.lapse_rate(t)) ** (1 / self.policy.Premium_Frequency)) * (t > 0)

    mortality_proportion = param("Qx Mortality Proportion")
    mad_morbidity = by_basis(reserving=param("prudent_margin_morbidity"), be=0.0)
    morbidity = table(
        "morbidity",
        axes=(
            int_axis("age", below="zero_rows", above="clamp"),
            keymap("Gender_Code", unknown="error", above="clamp"),
        ),
    )
    reinsurance_morbidity = table(
        "reinsurance_morbidity",
        axes=(
            int_axis("age", below="zero_rows", above="clamp"),
            keymap("Gender_Code", unknown="error", above="clamp"),
        ),
    )

    def mortality_rate(self, t):
        """Annual mortality times the rider proportion and basis margin, capped at 1."""
        return min(
            min(
                clip(
                    (self.mortality[self.age(t), self.policy.Gender_Code] + self.mortality_add[t])
                    * self.mortality_mult[t],
                    0.0,
                    1.0,
                )
                * self.mortality_proportion,
                1.0,
            )
            * (1 + self.mad_mortality),
            1.0,
        )

    def q(self, t):
        """Monthly mortality is zero at the valuation instant and before inception."""
        return (1 - (1 - self.mortality_rate(t)) ** (1 / 12)) * (self.policy_month(t) > 0) * (t > 0)

    def lapse_due(self, t):
        """Rider lapses start after policy month 1."""
        return (
            (self.policy_month(t) + 1) % (12 / self.policy.Premium_Frequency)
            == if_(self.policy.Premium_Frequency == 12, 0, 1)
        ) * (self.policy_month(t) > 1)

    def morbidity_rate(self, t):
        """Annual morbidity with the basis margin applied after clipping the shocked rate."""
        return clip(
            (self.morbidity[self.age(t), self.policy.Gender_Code] + self.morbidity_add[t])
            * self.morbidity_mult[t],
            0.0,
            1.0,
        ) * (1 + self.mad_morbidity)

    def morbidity_monthly(self, t):
        """Monthly morbidity; the event component masks the valuation instant."""
        return 1 - (1 - self.morbidity_rate(t)) ** (1 / 12)

    def reins_rate(self, t):
        """Reinsurance morbidity, masked before inception, without a margin."""
        return (
            1
            - (
                1
                - clip(
                    (
                        self.reinsurance_morbidity[self.age(t), self.policy.Gender_Code]
                        + self.morbidity_add[t]
                    )
                    * self.morbidity_mult[t],
                    0.0,
                    1.0,
                )
            )
            ** (1 / 12)
        ) * (self.policy_month(t) > 0)


class RiderCashflows(TermCashflows):
    """Rider premium ports and expenses, with claim expenses on the rider event."""

    REQUIRES = (*TermCashflows.REQUIRES, "rider_event", "term_months")
    wop_discount = param("Int rate to calculate PV of WOP")
    initial_expense_rates = table("expenses_rider", axes=())
    renewal_expense_rates = table("expenses_rider/renewal", axes=())
    ifrs_initial_expense_rates = table("ifrs17_initial_expenses_rider", axes=())

    @override
    def renewal_expenses(self, t):
        """Rider expense, including its unmasked valuation-instant value."""
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
        )

    @override
    def claim_expenses(self, t):
        """Settlement expense on the rider's own event."""
        return (
            self.policy.Sum_Assured
            * ((self.policy.claim_expense_percent * self.expense_mult[t]) / 100)
            * self.rider_event(t)
        )

    def base_premium_due(self, t):
        """Base premium eligible for waiver, stopped at the payment term."""
        return (
            self.policy.Base_Premium
            * self.modal_factor(t)
            * self.premium_due(t)
            * (self.policy_month(t) <= self.term_months(t))
        )

    def pv_waiver_premiums(self, t):
        """Reusable backward PV of eligible base premiums at the strict waiver rate."""
        return (nxt(self.pv_waiver_premiums, 0.0) + self.base_premium_due(t)) / (
            1 + ((1 + self.wop_discount) ** (1 / 12) - 1) * (t > 0)
        )

    def npv_wop(self, t):
        """Waiver PV at the month's end; zero at the valuation instant."""
        return nxt(self.pv_waiver_premiums, 0.0) * (t > 0)


class RiderReinsurance(SurplusReinsurance):
    """Surplus cover on morbidity, retaining the rider retention proportion."""

    REQUIRES = (*SurplusReinsurance.REQUIRES, "rider_event", "reinsured_benefit")
    retention_proportion = param("Reinsurance Retention Limit proportion")

    @override
    def reins_sum_assured(self, t):
        """Ceded benefit net of retention and opening reserve; unmasked at step 0."""
        return (
            max(
                self.reinsured_benefit(t)
                - self.retention
                - prev(at_basis("reserving", self.ceding_reserve_pp), 0.0),
                0.0,
            )
            * self.retention_proportion
        )

    @override
    def reins_recoveries(self, t):
        """Recovery on the rider's event."""
        return self.reins_sum_assured(t) * self.rider_event(t) * (t > 0)


class RiderReserves(PolicyReserves, UnearnedPremiumReserve):
    """Reuse the single reserve discounting formulas and apply the rider UPR floor."""

    REQUIRES = (*PolicyReserves.REQUIRES, "upr")

    @override
    def gross_reserve_amount(self, t):
        """Gross held amount including the UPR floor for eligible lives."""
        return max(self.discounted_net_cf(t), 0.0, self.upr(t) * self.eligible_reserve_lives(t))

    @override
    def net_reserve_amount(self, t):
        """Net held amount including the UPR floor for eligible lives."""
        return max(
            self.discounted_cf_with_reins(t), 0.0, self.upr(t) * self.eligible_reserve_lives(t)
        )

    @override
    def gross_reserve_pp(self, t):
        """The gross prospective reserve, floored at UPR."""
        return max(self.discounted_net_cf(t) / self.reserve_lives(t), 0.0, self.upr(t))

    @override
    def ceding_reserve_pp(self, t):
        """The reserve the cession nets off, floored at UPR; at month 0 the reserve held at
        the valuation date."""
        return max(nxt(self.pv_net_cashflows, 0.0) / self.reserve_lives(t), 0.0, self.upr(t))

    @override
    def net_reserve_pp(self, t):
        """The net prospective reserve, floored at UPR."""
        return max(self.discounted_cf_with_reins(t) / self.reserve_lives(t), 0.0, self.upr(t))


class RiderSolvency(SolvencyCapital):
    """Rider SAR includes the lives maturing this month."""

    REQUIRES = (*SolvencyCapital.REQUIRES, "maturities")

    @override
    def gross_sar(self, t):
        """Gross SAR on closing and maturing BE lives."""
        return max(
            self.sum_assured(t)
            * (at_basis("be", self.lives_end)(t) + at_basis("be", self.maturities)(t))
            - self.be_reserves(t),
            0.0,
        )

    @override
    def net_sar(self, t):
        """Net SAR on closing and maturing BE lives."""
        return max(
            (self.sum_assured(t) - at_basis("be", self.reins_sum_assured)(t))
            * (at_basis("be", self.lives_end)(t) + at_basis("be", self.maturities)(t))
            - self.be_reserves(t),
            0.0,
        )


class RiderMcev(MarketConsistentValue):
    """Rider FCC retains the valuation reference curve; PVs retain their masks."""

    @override
    def fcc_rate(self, t):
        """Discount rider FCC on the valuation reference forward curve."""
        return self.reference_forward[t]

    @override
    def pvfp(self, t):
        """Rider PVFP, without Term's policy-month mask."""
        return nxt(self.pv_net_profit, 0.0)

    @override
    def pv_premium(self, t):
        """Rider premium PV, without Term's policy-month mask."""
        return nxt(self.pv_premiums_from, 0.0)

    @override
    def bel(self, t):
        """Rider BEL, without Term's policy-month mask."""
        return nxt(self.pv_mcev_net_cf, 0.0)

    @override
    def fcc(self, t):
        """Rider FCC, without Term's policy-month mask."""
        return nxt(self.pv_coc, 0.0)


class RiderIfrsBel(IfrsBestEstimate):
    """Shared IFRS BEL formulas with onerous discounting separate from rider FCC."""

    REQUIRES = (*IfrsBestEstimate.REQUIRES, "ifrs_onerous_rate")

    def ifrs_onerous_rate(self, t):
        """The policy's own IFRS reference curve, separate from rider FCC."""
        return if_(
            (t >= 1) and (self.policy_month(t) >= 1),
            self.ifrs_reference_forward[self.policy_month(t) - 1],
            0.0,
        )

    @override
    def ifrs_onerous_cf(self, t):
        """IFRS cashflow interest at the policy's own onerous-tagging rate."""
        return self.ifrs_bel_cf(t) - (
            self.ifrs_premiums(t) - self.ifrs_initial_expense(t) - self.ifrs_renewal_expenses(t)
        ) * self.ifrs_onerous_rate(t)

    @override
    def pv_ifrs_onerous(self, t):
        """Shared backward idiom, discounted on the policy's own curve."""
        return (nxt(self.pv_ifrs_onerous, 0.0) + self.ifrs_onerous_cf(t)) / (
            1 + self.ifrs_onerous_rate(t)
        )


class RiderBase(
    RiderRates,
    RiderCashflows,
    NetCashflows,
    RiderReinsurance,
    RiderReserves,
    ProfitSignature,
    RiderSolvency,
    RiderMcev,
    RiderIfrsBel,
):
    """Shared rider components; a concrete product supplies its event and benefit ports."""

    interest_curve = curve("interest_rates")
    ifrs_curve = curve("ifrs17_interest_rates")


class AccidentalDeathBenefit(Component):
    """The accidental-death event is an additional benefit on opening lives."""

    REQUIRES = ("lives_begin", "morbidity_monthly", "sum_assured", "lives_end", "maturities")

    def rider_event(self, t):
        """Accidental deaths, with no event at the valuation instant."""
        return self.lives_begin(t) * self.morbidity_monthly(t) * (t > 0)

    def adb_benefit(self, t):
        """Sum assured on each accidental death."""
        return self.sum_assured(t) * self.rider_event(t) * (t > 0)

    def reinsured_benefit(self, t):
        """ADB reinsures only its sum assured, excluding any waiver PV."""
        return self.sum_assured(t)

    def coverage_units(self, t):
        """Rider benefit in force on closing best-estimate active lives."""
        return self.sum_assured(t) * at_basis("be", self.lives_end)(t) * (t > 0)


class AccidentalDeathCashflows(RiderCashflows):
    """ADB implements the benefit port at composition time."""

    REQUIRES = (*RiderCashflows.REQUIRES, "adb_benefit")

    @override
    def benefit_outgo(self, t):
        """ADB pays its accidental-death lump sum, with no waiver."""
        return self.adb_benefit(t)


class AccidentalDeath(
    AccidentalDeathBenefit, AccidentalDeathCashflows, RiderBase, LivesAndExits, RiderProduct
):
    CODE, LABEL, BASES = "ACCIDENTAL_DEATH_RIDER", "Accidental death rider", ("reserving", "be")
    FIELDS = tuple(name for name in Term.FIELDS if name not in ("EMR", "reins_EMR")) + (
        "Base_Premium",
        "Rider_Option",
    )


class IfrsAccidentalDeath(IfrsMeasurement, AccidentalDeath):
    """ADB plus the shared IFRS measurement adapters."""
