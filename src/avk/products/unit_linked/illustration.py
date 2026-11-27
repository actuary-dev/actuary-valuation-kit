"""One-life unit fund projection under a fixed gross return: reduction in yield (RIY),
residual additions and benefit illustration values.

The roll repeats the per-life unit fund of the projection (design 5.6) without decrements,
partial withdrawals or lifecycle strategies, so a life that survives and stays in force
earns exactly the engine's per-life fund path. Nothing here reads files or tables: a `Case`
carries the contract, the variant's design features, the fund slots and the per-year charge
arrays.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt

Array = npt.NDArray[np.float64]

# Completed policy years at which the reduction in yield is measured, and the first
# anniversary at which a residual addition may be credited. The product specification
# requires the first five policy years to comply by design, so year 5 is a design test.
FIRST_MEASUREMENT_YEAR = 5
FIRST_ADDITION_YEAR = 6

FEATURES = (
    "single_premium",
    "death_benefit_type",
    "min_db_premium_multiple",
    "lock_in_months",
    "dpf_enabled",
    "loyalty_on",
    "loyalty_basis",
    "loyalty_start_year",
    "loyalty_requires_full_premiums",
    "guaranteed_addition_rate",
    "romc_fraction",
    "ropac_fraction",
    "roadmin_fraction",
    "gmmb_on",
    "gmmb_premium_multiple",
    "guarantee_charge",
    "admin_escalation",
    "mortality_charge_multiplier",
    "disc_ap_threshold",
    "auto_rebalance",
    "riy_additions_on",
)


def monthly_rate(annual: float) -> float:
    """The monthly effective equivalent of an annual-effective rate (as the scenario library)."""
    if not math.isfinite(annual) or annual <= -1:
        raise ValueError("an annual rate must be finite and exceed -1")
    return math.expm1(math.log1p(annual) / 12)


@dataclass(frozen=True)
class Gross:
    """A fixed gross return on every fund: annual effective and its monthly equivalent."""

    annual: float
    monthly: float

    @classmethod
    def of(cls, annual: float) -> "Gross":
        return cls(annual, monthly_rate(annual))


@dataclass(frozen=True)
class ChargeSchedule:
    """Per policy year arrays (year 1 first; the last value repeats beyond the end) and the
    contractual mortality charge per 1,000 by attained age (age 0 first; the last repeats)."""

    pac_rate: tuple[float, ...]
    admin: tuple[float, ...]
    loyalty_rate: tuple[float, ...]
    booster_rate: tuple[float, ...]
    disc_pct_low: tuple[float, ...]
    disc_cap_low: tuple[float, ...]
    disc_pct_high: tuple[float, ...]
    disc_cap_high: tuple[float, ...]
    riy_cap: tuple[float, ...]
    mortality_per_mille: tuple[float, ...]

    def year(self, name: str, year: int) -> float:
        values: tuple[float, ...] = getattr(self, name)
        return values[min(year, len(values)) - 1]

    def mortality(self, age: int) -> float:
        return self.mortality_per_mille[min(age, len(self.mortality_per_mille) - 1)]


@dataclass(frozen=True)
class Case:
    """A policy as sold: contract, design features (`FEATURES`), fund slots and charges."""

    term_years: int
    payment_years: int
    frequency: int
    instalment: float
    annualised_premium: float
    instalments_payable: int
    sum_assured: float
    entry_age: int
    emr: float
    flat_extra: float
    flat_extra_months: int
    features: Mapping[str, float]
    allocations: tuple[float, ...]
    fmcs: tuple[float, ...]
    schedule: ChargeSchedule
    label: str = field(default="")

    def __post_init__(self) -> None:
        missing = [name for name in FEATURES if name not in self.features]
        if missing:
            raise ValueError(f"case is missing design features {missing}")
        if not self.allocations or len(self.allocations) != len(self.fmcs):
            raise ValueError("a case needs one allocation and one FMC per fund slot")
        if sum(self.allocations) <= 0:
            raise ValueError("fund allocations must be positive in total")
        if self.term_years < 1:
            raise ValueError("the policy term must be at least one year")

    @property
    def months(self) -> int:
        return self.term_years * 12

    @property
    def single(self) -> bool:
        return bool(self.features["single_premium"])

    def due(self, month: int) -> bool:
        """Whether an instalment is due at the start of policy month `month` (1-based)."""
        if self.single:
            return month == 1
        if month > self.payment_years * 12:
            return False
        if self.frequency == 12:
            return True
        return month % (12 // max(self.frequency, 1)) == 1


@dataclass(frozen=True)
class Projection:
    """Monthly arrays (index `month - 1`) of one life, plus year-end helpers."""

    case: Case
    gross: Gross
    risk_charges: bool
    premium: Array
    pac: Array
    admin: Array
    mortality: Array
    guarantee: Array
    fmc: Array
    loyalty: Array
    booster: Array
    guaranteed_addition: Array
    residual: Array
    fund: Array
    premiums_to_date: Array
    sum_at_risk: Array
    roc_to_date: Array

    @property
    def years(self) -> int:
        return self.case.term_years

    def year_end(self, values: Array) -> Array:
        """The value at the end of each policy year."""
        return values[11::12]

    def year_sum(self, values: Array) -> Array:
        """The total over each policy year."""
        return values.reshape(self.years, 12).sum(axis=1)


def _retention(after: float, requested: float) -> tuple[float, float]:
    """The scale applied to requested deductions and the fund fraction that stays."""
    scale = after / requested if requested > max(after, 0.0) else 1.0
    keep = 1.0 - requested * scale / after if (after > requested and after > 0.0) else 0.0
    return scale, keep


def project(
    case: Case,
    gross: Gross,
    *,
    risk_charges: bool = True,
    residual: bool = False,
    credited: Sequence[float] | Array | None = None,
) -> Projection:
    """Roll one life through the policy term. With `risk_charges` False the mortality charge
    (EMR and flat extra included) and the guarantee charge are not deducted, the basis of the
    RIY test. With `residual` True a non-negative addition is credited at each permitted
    anniversary so that RIY stays within the cap (only when the variant has the feature).
    `credited` instead credits given amounts at the end of month 12n (index `n - 1`), for
    example the additions solved on the RIY basis, in a run that keeps every charge."""
    f = case.features
    sched = case.schedule
    months = case.months
    total_alloc = sum(case.allocations)
    norm = [a / total_alloc for a in case.allocations]
    fmc_rate = [1 - (1 - c) ** (1 / 12) for c in case.fmcs]
    gc_rate = 1 - (1 - f["guarantee_charge"]) ** (1 / 12)
    slots = len(norm)

    names = (
        "premium pac admin mortality guarantee fmc loyalty booster guaranteed_addition "
        "residual fund premiums_to_date sum_at_risk roc_to_date"
    ).split()
    out = {name: np.zeros(months) for name in names}
    funds = [0.0] * slots
    total = 0.0
    tpp = 0.0
    paid = 0
    year_sum = 0.0
    cum_mc = cum_pac = cum_admin = 0.0
    premium_times: list[float] = []
    premium_amounts: list[float] = []
    admin_scale = 1 + f["admin_escalation"]
    for m in range(1, months + 1):
        year = (m - 1) // 12 + 1
        year_start = m > 1 and m % 12 == 1
        anniversary = m % 12 == 0
        due = case.due(m)
        premium = case.instalment * due
        paid += 1 if due else 0
        if due:
            premium_times.append((m - 1) / 12)
            premium_amounts.append(premium)
        pac = premium * sched.year("pac_rate", year)
        rebalance = bool(f["auto_rebalance"]) and year_start
        opening = [total * w for w in norm] if rebalance else funds
        after_premium = [o + (premium - pac) * w for o, w in zip(opening, norm, strict=True)]
        base = sum(after_premium)
        admin_req = sched.year("admin", year) * admin_scale ** (year - 1)
        gc_req = base * gc_rate if risk_charges else 0.0
        tpp += premium
        floor_db = f["min_db_premium_multiple"] * tpp
        reduced = base - admin_req - gc_req
        if f["death_benefit_type"] == 1:
            sar = max(max(case.sum_assured, floor_db) - reduced, 0.0)
        else:
            sar = max(case.sum_assured, floor_db - reduced)
        if risk_charges:
            rate = sched.mortality(case.entry_age + year - 1) * f["mortality_charge_multiplier"]
            rate = rate * case.emr + case.flat_extra * (m <= case.flat_extra_months)
            mc_req = sar * rate / 12000
        else:
            mc_req = 0.0
        requested = admin_req + gc_req + mc_req
        scale, keep = _retention(base, requested)
        admin, gc, mc = admin_req * scale, gc_req * scale, mc_req * scale
        after_charges = [value * keep for value in after_premium]
        after_total = sum(after_charges)
        additions = loyalty = booster = guaranteed = 0.0
        due_additions = anniversary and (after_total > 0 or total_alloc > 0)
        average = (year_sum + after_total) / 12
        if due_additions:
            full = paid >= (
                1 if case.single else min(year * case.frequency, case.instalments_payable)
            )
            if (
                f["loyalty_on"]
                and year >= f["loyalty_start_year"]
                and (not f["loyalty_requires_full_premiums"] or full)
            ):
                basis = average if f["loyalty_basis"] == 1 else case.annualised_premium
                loyalty = sched.year("loyalty_rate", year) * basis
            booster = sched.year("booster_rate", year) * average
            guaranteed = f["guaranteed_addition_rate"] * case.annualised_premium
            additions = loyalty + booster + guaranteed
        new_funds = []
        fmc_total = 0.0
        for k in range(slots):
            share = after_charges[k] / after_total if after_total > 0 else norm[k]
            grown = (after_charges[k] + additions * share) * (1 + gross.monthly)
            charge = grown * fmc_rate[k]
            fmc_total += charge
            new_funds.append(grown - charge)
        funds = new_funds
        total = sum(funds)
        added = 0.0
        if credited is not None and anniversary:
            added = float(credited[year - 1])
        elif (
            residual
            and f["riy_additions_on"]
            and anniversary
            and year >= FIRST_ADDITION_YEAR
            and year >= FIRST_MEASUREMENT_YEAR
        ):
            target = gross.annual - sched.year("riy_cap", year)
            wanted = accumulate(premium_times, premium_amounts, target, year)
            added = max(wanted - total, 0.0)
        if added > 0:
            funds = [
                value + added * (value / total if total > 0 else w)
                for value, w in zip(funds, norm, strict=True)
            ]
            total = sum(funds)
        year_sum = 0.0 if anniversary else year_sum + total
        cum_mc += mc
        cum_pac += pac
        cum_admin += admin
        roc = (
            f["romc_fraction"] * cum_mc
            + f["ropac_fraction"] * cum_pac
            + f["roadmin_fraction"] * cum_admin
        )
        i = m - 1
        out["premium"][i] = premium
        out["pac"][i] = pac
        out["admin"][i] = admin
        out["mortality"][i] = mc
        out["guarantee"][i] = gc
        out["fmc"][i] = fmc_total
        out["loyalty"][i] = loyalty
        out["booster"][i] = booster
        out["guaranteed_addition"][i] = guaranteed
        out["residual"][i] = added
        out["fund"][i] = total
        out["premiums_to_date"][i] = tpp
        out["sum_at_risk"][i] = sar
        out["roc_to_date"][i] = roc
    return Projection(case=case, gross=gross, risk_charges=risk_charges, **out)


def accumulate(times: list[float], amounts: list[float], rate: float, years: int) -> float:
    """The premiums paid so far, accumulated at `rate` to the end of year `years`."""
    t = np.asarray(times, dtype=np.float64)
    p = np.asarray(amounts, dtype=np.float64)
    return float(np.sum(p * (1.0 + rate) ** (years - t)))


def net_yield(times: Array, amounts: Array, years: float, value: float) -> float:
    """The annual-effective internal rate of return of premiums `amounts` paid at `times`
    (years from inception) and the fund `value` at time `years`. A fund of nothing returns -1."""
    if value <= 0:
        return -1.0
    exponents = years - times

    def excess(rate: float) -> float:
        return float(np.sum(amounts * (1.0 + rate) ** exponents)) - value

    low, high = -1.0 + 1e-12, 1.0
    while excess(high) < 0:
        high = high * 2 + 1
        if high > 1e12:
            raise ValueError("net yield does not exist for these cashflows")
    if excess(low) > 0:
        return low
    for _ in range(200):
        mid = 0.5 * (low + high)
        if excess(mid) < 0:
            low = mid
        else:
            high = mid
        if high - low <= 4e-16 * max(1.0, abs(mid)):
            break
    return 0.5 * (low + high)


@dataclass(frozen=True)
class Riy:
    """Net yield, RIY and the cap at each measurement point (policy years 5 to the term)."""

    years: Array
    net_yield: Array
    riy: Array
    cap: Array
    excess: Array
    residual: Array
    fund: Array
    premiums_to_date: Array


def riy(projection: Projection) -> Riy:
    """Measure the reduction in yield at the end of each policy year from year 5.
    Premiums come from the projection; the fund value is its fund at the year end."""
    case = projection.case
    first = FIRST_MEASUREMENT_YEAR
    premiums = projection.premium
    months = np.arange(case.months)
    due = premiums > 0
    times = months[due] / 12.0
    amounts = premiums[due]
    years = np.arange(first, case.term_years + 1, dtype=np.float64)
    fund = projection.year_end(projection.fund)
    yields = np.zeros(len(years))
    for i, year in enumerate(years):
        used = times < year
        yields[i] = net_yield(times[used], amounts[used], float(year), float(fund[int(year) - 1]))
    cap = np.array([case.schedule.year("riy_cap", int(y)) for y in years])
    value = projection.gross.annual - yields
    residual = projection.year_end(projection.residual)[first - 1 :]
    paid = projection.year_end(projection.premiums_to_date)[first - 1 :]
    return Riy(years, yields, value, cap, value - cap, residual, fund[first - 1 :], paid)


@dataclass(frozen=True)
class YearEnd:
    """Yearly sums and year-end values of one projection (index `year - 1`).

    `surrender_value` and `surrender_payable_month` are NaN in the maturity year, and
    `maturity_value` is NaN before it."""

    years: Array
    premiums: Array
    pac: Array
    admin: Array
    mortality: Array
    guarantee: Array
    fmc: Array
    loyalty: Array
    booster: Array
    guaranteed_addition: Array
    residual: Array
    fund: Array
    premiums_to_date: Array
    death_benefit: Array
    discontinuance_charge: Array
    surrender_value: Array
    surrender_payable_month: Array
    maturity_value: Array


def year_end(projection: Projection) -> YearEnd:
    """Benefit values at each policy year end (see the benefit illustration documentation)."""
    case = projection.case
    f = case.features
    n = case.term_years
    fund = projection.year_end(projection.fund)
    tpp = projection.year_end(projection.premiums_to_date)
    floor = f["min_db_premium_multiple"] * tpp
    if f["death_benefit_type"] == 1:
        death = np.maximum(np.maximum(case.sum_assured, floor), fund)
    else:
        death = np.maximum(case.sum_assured + fund, floor)
    high = case.annualised_premium > f["disc_ap_threshold"]
    charge = np.zeros(n)
    surrender = np.zeros(n)
    payable = np.zeros(n)
    for i in range(n):
        month, year = 12 * (i + 1), i + 1
        inside = month <= f["lock_in_months"]
        if inside:
            side = "high" if high else "low"
            pct = case.schedule.year(f"disc_pct_{side}", year)
            cap = case.schedule.year(f"disc_cap_{side}", year)
            charge[i] = min(pct * case.annualised_premium, fund[i], cap)
        surrender[i] = fund[i] - charge[i]
        payable[i] = min(f["lock_in_months"], case.months) if inside and f["dpf_enabled"] else month
    roc = projection.roc_to_date[-1]
    guarantee_top_up = f["gmmb_on"] * max(
        f["gmmb_premium_multiple"] * tpp[-1] - fund[-1] - roc, 0.0
    )
    maturity = np.full(n, np.nan)
    maturity[-1] = fund[-1] + roc + guarantee_top_up
    surrender[-1] = payable[-1] = np.nan
    return YearEnd(
        years=np.arange(1, n + 1, dtype=np.float64),
        premiums=projection.year_sum(projection.premium),
        pac=projection.year_sum(projection.pac),
        admin=projection.year_sum(projection.admin),
        mortality=projection.year_sum(projection.mortality),
        guarantee=projection.year_sum(projection.guarantee),
        fmc=projection.year_sum(projection.fmc),
        loyalty=projection.year_sum(projection.loyalty),
        booster=projection.year_sum(projection.booster),
        guaranteed_addition=projection.year_sum(projection.guaranteed_addition),
        residual=projection.year_sum(projection.residual),
        fund=fund,
        premiums_to_date=tpp,
        death_benefit=death,
        discontinuance_charge=charge,
        surrender_value=surrender,
        surrender_payable_month=payable,
        maturity_value=maturity,
    )


# A breach is an excess of RIY over the cap above this absolute amount (rate units). It is
# far above the root-finder's precision and below any rate that matters.
BREACH_TOLERANCE = 1e-12


@dataclass(frozen=True)
class Assessment:
    """The cap test of one case at one gross return.

    `design` measures the fund as designed (no additions); `with_additions` credits the
    residual additions of the variant (none when it does not have the feature). Status:
    `pass` (no breach), `pass_with_additions` (breaches only from the first addition year and
    additions restore every cap), `design_fail` (a breach before the first addition year),
    `fail` (a late breach that additions cannot or may not repair)."""

    status: str
    design: Riy
    with_additions: Riy
    first_breach_year: int | None
    worst_margin: float


def assess(case: Case, gross: Gross) -> Assessment:
    """Test a case against its caps at a gross return, on the RIY basis (no risk charges)."""
    design = riy(project(case, gross, risk_charges=False))
    added = riy(project(case, gross, risk_charges=False, residual=True))
    breach = design.excess > BREACH_TOLERANCE
    first = int(design.years[breach][0]) if breach.any() else None
    if first is None:
        status = "pass"
    elif first < FIRST_ADDITION_YEAR:
        status = "design_fail"
    elif case.features["riy_additions_on"] and not (added.excess > BREACH_TOLERANCE).any():
        status = "pass_with_additions"
    else:
        status = "fail"
    return Assessment(status, design, added, first, float(np.min(design.cap - design.riy)))
