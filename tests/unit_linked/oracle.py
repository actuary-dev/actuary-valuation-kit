"""An independent scalar model of UNIT_LINKED, one policy and one month at a time.

Written from the product design (`docs/superpowers/specs/2026-11-26-unit-linked-product-design.md`)
and the P2a and P2b plans, not from the formula modules. It reads the raw policy and holding
rows and the basis CSV files itself (polars only), builds its own monthly scenarios, and
returns, per basis, every quantity the valuation output reports under the product's column
names. It uses no `avk` code.

Case shocks are not modelled: the oracle reproduces the base case only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import polars as pl

ASSETS = (
    "eq_large",
    "eq_mid",
    "eq_small",
    "eq_global",
    "gov_long",
    "gov_short",
    "corp_bond",
    "money_market",
    "gold",
    "real_assets",
)
GENDERS = {"M": 0, "F": 1, "T": 2}
SMOKERS = {"NS": 0, "S": 1}
MORTALITY_FIELDS = ("male", "female", "transgender")
CHARGE_FIELDS = (
    "male_non_smoker",
    "male_smoker",
    "female_non_smoker",
    "female_smoker",
    "transgender_non_smoker",
    "transgender_smoker",
)
BASES = ("reserving", "be", "mc")
RATE_FIELDS = {"roi": "roi", "vroi": "vroi", "reference_forward": "reference_forward_rates"}


def monthly(annual: float) -> float:
    return (1 + annual) ** (1 / 12) - 1


def decrement(annual: float, periods: float = 12) -> float:
    return 1 - (1 - annual) ** (1 / periods)


@dataclass
class Basis:
    """The demo basis tables in plain dictionaries."""

    params: dict[str, float]
    funds: dict[str, dict[str, float]]
    fund_order: list[str]
    variants: dict[str, dict[str, float]]
    regimes: dict[int, dict[str, float]]
    scales: dict[str, dict[tuple[int, int], float]]
    mortality: dict[tuple[int, int], float]
    charges: dict[tuple[int, int], float]
    lapse: dict[tuple[int, int], float]
    withdrawals: dict[tuple[int, int], float]
    commission: dict[tuple[int, int], float]
    rates: dict[str, list[float]]
    returns: dict[str, list[float]]

    @classmethod
    def read(cls, folder: Path) -> Basis:
        def frame(name: str) -> pl.DataFrame:
            return pl.read_csv(folder / f"{name}.csv")

        parameters = frame("product_parameters").filter(pl.col("product") == "UNIT_LINKED")
        params = {row["parameter"]: float(row["value"]) for row in parameters.iter_rows(named=True)}

        def keyed(name: str) -> tuple[dict[str, dict[str, float]], list[str]]:
            out: dict[str, dict[str, float]] = {}
            order: list[str] = []
            for row in frame(name).iter_rows(named=True):
                if row["key"] not in out:
                    out[row["key"]] = {}
                    order.append(row["key"])
                out[row["key"]][row["field"]] = float(row["value"])
            return out, order

        funds, fund_order = keyed("ul_funds")
        variants, _ = keyed("ul_variants")
        caps, _ = keyed("ul_regulatory_caps")
        regimes = {int(v["regime_id"]): v for v in caps.values()}
        scales: dict[str, dict[tuple[int, int], float]] = {}
        for row in frame("ul_charge_scales").iter_rows(named=True):
            scales.setdefault(row["field"], {})[(int(row["year"]), int(row["key"]))] = float(
                row["value"]
            )

        def by_age(name: str, fields: tuple[str, ...]) -> dict[tuple[int, int], float]:
            return {
                (int(r["age"]), fields.index(r["field"])): float(r["value"])
                for r in frame(name).iter_rows(named=True)
            }

        def by_channel(name: str) -> dict[tuple[int, int], float]:
            return {
                (int(r["year"]), int(r["channel"])): float(r["value"])
                for r in frame(name).iter_rows(named=True)
            }

        def curve(name: str) -> dict[str, list[float]]:
            out: dict[str, list[float]] = {}
            for row in frame(name).sort("year").iter_rows(named=True):
                out.setdefault(row["field"], []).append(float(row["value"]))
            return out

        return cls(
            params,
            funds,
            fund_order,
            variants,
            regimes,
            scales,
            by_age("mortality", MORTALITY_FIELDS),
            by_age("mortality_charges_ul", CHARGE_FIELDS),
            by_channel("lapse_rates_ul"),
            by_channel("partial_withdrawals_ul"),
            by_channel("commissions_ul"),
            curve("interest_rates"),
            curve("ul_asset_returns"),
        )

    def scenario(self, annual: list[float], horizon: int) -> list[float]:
        """Monthly effective rates by projection month, lagged one month."""
        out = [0.0] * horizon
        for t in range(1, horizon):
            out[t] = monthly(annual[(t - 1) // 12])
        return out


def clamp_year(table: dict[tuple[int, int], float], year: int, key: int) -> float:
    years = sorted({y for y, k in table if k == key})
    return table[(min(max(year, years[0]), years[-1]), key)]


def clamp_age(table: dict[tuple[int, int], float], age: int, key: int) -> float:
    ages = sorted({a for a, k in table if k == key})
    if age < ages[0]:
        raise ValueError(f"age {age} below the table")
    return table[(min(age, ages[-1]), key)]


def months_elapsed(start: date, valuation: date) -> int:
    return (valuation.year - start.year) * 12 + valuation.month - start.month + 1


def parse(value: object) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


@dataclass
class Policy:
    """A policy row and its holdings, prepared the way the design describes."""

    number: str
    variant: dict[str, float]
    dpf_min_rate: float
    duration: int
    term: int
    ppt: int
    frequency: int
    annual_premium: float
    instalment: float
    instalments_payable: int
    sum_assured: float
    channel: int
    age_entry: int
    gender: int
    smoker: int
    emr: float
    flat_extra: float
    flat_extra_months: int
    status: int
    paid_up_sa: float
    tpp: float
    instalments_paid: float
    pac_to_date: float
    admin_to_date: float
    mc_to_date: float
    pw_current: float
    pw_previous: float
    fv_sum: float
    dpf_value: float
    dpf_fund: dict[str, float]
    slots: list[dict[str, float]]

    @classmethod
    def prepare(cls, row: dict, holdings: list[dict], basis: Basis, valuation: date) -> Policy:
        variant = basis.variants[row["Product Variant"]]
        regime = basis.regimes[int(variant["regime_id"])]
        frequency = int(row["Premium Frequency"])
        single = frequency == 0
        dpf_key = next(k for k in basis.fund_order if basis.funds[k]["is_dpf"] == 1)
        dpf_value = sum(
            float(h["Units"]) * basis.funds[dpf_key]["unit_price"]
            for h in holdings
            if h["Fund Code"] == dpf_key
        )
        slots = []
        for key in basis.fund_order:
            for h in holdings:
                if h["Fund Code"] == key and key != dpf_key:
                    fund = basis.funds[key]
                    slots.append(
                        {
                            "allocation": float(h["Premium Allocation"]),
                            "value": float(h["Units"]) * fund["unit_price"],
                            "fmc": fund["fmc"],
                            "alpha": fund["alpha"],
                            **{a: fund[f"w_{a}"] for a in ASSETS},
                        }
                    )
        return cls(
            number=str(row["Policy Number"]),
            variant=variant,
            dpf_min_rate=regime["dpf_min_rate"],
            duration=months_elapsed(parse(row["Policy Start Date"]), valuation),
            term=int(row["Policy Term (Years)"]),
            ppt=int(row["Premium Payment Term (Years)"]),
            frequency=frequency,
            annual_premium=float(row["Annualised Premium"]),
            instalment=float(row["Annualised Premium"]) / (1 if single else frequency),
            instalments_payable=1
            if single
            else frequency * int(row["Premium Payment Term (Years)"]),
            sum_assured=float(row["Sum Assured"]),
            channel=int(row["Distribution Channel"]),
            age_entry=int(row["Age at Policy Start"]),
            gender=GENDERS[row["Gender"]],
            smoker=SMOKERS[row["Smoking Status"]],
            emr=float(row["EMR"]),
            flat_extra=float(row["Flat Extra"]),
            flat_extra_months=int(row["Flat Extra Term (Years)"]) * 12,
            status=int(row["Policy Status"]),
            paid_up_sa=float(row["Paid Up Sum Assured"]),
            tpp=float(row["Premiums Paid To Date"]),
            instalments_paid=float(row["Instalments Paid"]),
            pac_to_date=float(row["Premium Allocation Charges To Date"]),
            admin_to_date=float(row["Policy Administration Charges To Date"]),
            mc_to_date=float(row["Mortality Charges To Date"]),
            pw_current=float(row["Withdrawals Current Policy Year"]),
            pw_previous=float(row["Withdrawals Previous Policy Year"]),
            fv_sum=float(row["Fund Value Sum Current Policy Year"]),
            dpf_value=dpf_value,
            dpf_fund=basis.funds[dpf_key],
            slots=slots,
        )


def project_basis(p: Policy, b: Basis, basis: str, horizon: int) -> dict[str, list[float]]:
    """Every monthly quantity of one basis, forward then backward."""
    v, par = p.variant, b.params
    reserving = basis == "reserving"
    mad_q = par["prudent_margin_mortality"] if reserving else 0.0
    mad_w = par["prudent_margin_lapse"] if reserving else 0.0
    mad_pw = par["prudent_margin_partial_withdrawal"] if reserving else 0.0
    mad_e = par["prudent_margin_expense"] if reserving else 0.0
    share = par["surrender_share"]
    returns = {a: b.scenario(b.returns[a], horizon) for a in ASSETS}
    rate = {k: b.scenario(b.rates[f], horizon) for k, f in RATE_FIELDS.items()}
    rf = rate["reference_forward"]
    gf_rate = rate[{"reserving": "vroi", "be": "roi", "mc": "reference_forward"}[basis]]
    margin_factor = (1 + par["fund_return_margin"]) ** (1 / 12)
    mc_source = par["mc_fund_return_source"]
    term_m = p.term * 12
    vid = int(v["variant_id"])
    single = v["single_premium"] == 1
    lock = v["lock_in_months"]
    n = len(p.slots)
    alloc_total = sum(s["allocation"] for s in p.slots)
    weights = [s["allocation"] / alloc_total if alloc_total > 0 else 0.0 for s in p.slots]

    def growth(market: float, t: int, live: bool) -> float:
        if basis == "be":
            g = market
        elif basis == "reserving":
            g = (1 + market) * margin_factor - 1
        else:
            g = rf[t] if mc_source == 0 else market
        return g * live

    out: dict[str, list[float]] = {}

    def put(name: str, value: float) -> None:
        out.setdefault(name, []).append(float(value))

    # State carried from one month to the next.
    A = 1.0 if p.status == 0 else 0.0
    D = 1.0 if p.status == 1 else 0.0
    R = 1.0 if p.status == 2 else 0.0
    close = [s["value"] * (p.status == 0) for s in p.slots]
    close_total_prev = 0.0
    rpu = [s["value"] * (p.status == 2) for s in p.slots]
    pusa = p.paid_up_sa * (p.status == 2)
    rpu_tpp = p.tpp * (p.status == 2)
    dpf = p.dpf_value
    tpp, inst = p.tpp, p.instalments_paid
    pw_this, pw_last = p.pw_current, p.pw_previous
    fv_sum = p.fv_sum
    mc_cum, pac_cum, admin_cum = p.mc_to_date, p.pac_to_date, p.admin_to_date
    unit_reserve_prev = 0.0

    for t in range(horizon):
        pm = p.duration + t
        py = (pm - 1) // 12 + 1
        age = p.age_entry + (pm - 1) // 12
        live = t > 0 and 1 <= pm <= term_m
        maturity = (live and pm == term_m) or (t == 1 and p.duration == term_m)
        year_start = live and pm > 1 and pm % 12 == 1
        anniversary = live and pm % 12 == 0
        lock_in = pm <= lock
        lockin_due = t > 0 and pm >= min(lock, term_m)
        in_pt = pm <= p.ppt * 12
        paying = in_pt and not single
        if single:
            due = live and pm == 1
        else:
            due = live and in_pt and (p.frequency == 12 or pm % (12 / max(p.frequency, 1)) == 1)

        # Rates.
        base_q = clamp_age(b.mortality, age, p.gender) * par["experience_mortality_pct"]
        base_q *= par["smoker_mortality_loading"] if p.smoker == 1 else 1
        annual_q = min(min(max(base_q, 0), 1) * p.emr * (1 + mad_q), 1)
        q = decrement(annual_q) * live
        disc = min(min(max(clamp_year(b.lapse, py, p.channel), 0), 1) * (1 + mad_w), 1)
        w_surr = decrement(disc * (share if paying else 1)) * live * (1 - maturity)
        w_full = decrement(disc) * live * (1 - maturity)
        w_cess = decrement(disc * (1 - share), max(p.frequency, 1)) * due * paying * (1 - maturity)
        pw_annual = min(clamp_year(b.withdrawals, py, p.channel) * (1 + mad_pw), 1)
        pw_rate = decrement(pw_annual) * v["pw_allowed"] * (py >= v["pw_start_year"]) * live

        # Lives.
        A_begin, D_begin, R_begin = A, D, R
        deaths_A = A_begin * q
        surrenders_A = (A_begin - deaths_A) * w_surr
        cessations_A = (A_begin - deaths_A - surrenders_A) * w_cess
        maturities_A = (A_begin - deaths_A - surrenders_A - cessations_A) * maturity
        A_end = max(A_begin - deaths_A - surrenders_A - cessations_A - maturities_A, 0)
        to_dpf = (surrenders_A + cessations_A) * lock_in * v["dpf_enabled"]
        to_rpu = cessations_A * (1 - lock_in) * (v["rpu_mode"] >= 1)
        paid_out_A = surrenders_A + cessations_A - to_dpf - to_rpu
        deaths_D = D_begin * q
        lockin_exits_D = (D_begin - deaths_D + to_dpf) * lockin_due
        D_end = max(D_begin - deaths_D + to_dpf - lockin_exits_D, 0)
        deaths_R = R_begin * q
        surrenders_R = (R_begin - deaths_R) * w_full
        expiries_R = (
            (R_begin - deaths_R - surrenders_R)
            * (v["rpu_mode"] == 2)
            * live
            / max(v["revival_period_months"], 1)
        )
        R_before = R_begin - deaths_R - surrenders_R - expiries_R
        maturities_R = R_before * maturity
        R_end = max(R_before - maturities_R + to_rpu, 0)
        R_survival = (R_before - maturities_R) / R_begin if R_begin > 0 else 0.0
        A, D, R = A_end, D_end, R_end

        # Active premium and deductions per life.
        has_A = A_begin > 0
        premium_pp = p.instalment * due * has_A
        pac_pp = premium_pp * clamp_year(b.scales["premium_allocation_rate"], py, vid)
        allocated_pp = premium_pp - pac_pp
        tpp = tpp + premium_pp
        inst = inst + due * has_A
        pw_this_open = 0.0 if year_start else pw_this
        if year_start:
            pw_last = pw_this
        sa_eff = max(p.sum_assured - v["pw_reduces_sa"] * (pw_this_open + pw_last), 0)
        floor_db = v["min_db_premium_multiple"] * tpp
        rebalance = v["auto_rebalance"] and year_start and alloc_total > 0
        if t == 0 or ((live or maturity) and has_A):
            if rebalance:
                opening = [close_total_prev * w for w in weights]
            else:
                opening = list(close)
        else:
            opening = [0.0] * n
        after_premium = [opening[k] + allocated_pp * weights[k] for k in range(n)]
        fap = sum(after_premium)
        pw_req = fap * pw_rate
        admin_rate = (
            clamp_year(b.scales["admin_charge_monthly"], py, vid)
            * (1 + v["admin_escalation"]) ** (py - 1)
            * live
        )
        admin_req = admin_rate * has_A
        gc_rate = decrement(v["guarantee_charge"]) * live
        gc_req = fap * gc_rate
        before_mortality = fap - pw_req - admin_req - gc_req
        if v["death_benefit_type"] == 1:
            sar = max(max(sa_eff, floor_db) - before_mortality, 0)
        else:
            sar = max(sa_eff, floor_db - before_mortality)
        mc_rate = clamp_age(b.charges, age, 2 * p.gender + p.smoker) * v[
            "mortality_charge_multiplier"
        ] * p.emr + p.flat_extra * (pm <= p.flat_extra_months)
        mc_req = sar * mc_rate / 12000 * live * has_A
        requested = pw_req + admin_req + gc_req + mc_req
        scale = fap / requested if requested > max(fap, 0) else 1.0
        pw_pp, admin_pp, gc_pp, mc_pp = (x * scale for x in (pw_req, admin_req, gc_req, mc_req))
        deducted = pw_pp + admin_pp + gc_pp + mc_pp
        retention = 1 - deducted / fap if fap > requested and fap > 0 else 0.0
        after_charges = [x * retention for x in after_premium]
        fac = sum(after_charges)
        pw_this = pw_this_open + pw_pp
        mc_cum += mc_pp
        pac_cum += pac_pp
        admin_cum += admin_pp
        average = (fv_sum + fac) / 12
        full = inst >= (1 if single else min(py * p.frequency, p.instalments_payable))
        additions_due = anniversary and has_A and (fac > 0 or alloc_total > 0)
        loyalty = 0.0
        if (
            additions_due
            and v["loyalty_on"]
            and py >= v["loyalty_start_year"]
            and (v["loyalty_requires_full_premiums"] == 0 or full)
        ):
            loyalty = clamp_year(b.scales["loyalty_rate"], py, vid) * (
                average if v["loyalty_basis"] == 1 else p.annual_premium
            )
        booster = clamp_year(b.scales["booster_rate"], py, vid) * average if additions_due else 0
        guaranteed_addition = additions_due * v["guaranteed_addition_rate"] * p.annual_premium
        additions_pp = loyalty + booster + guaranteed_addition
        rates_k = []
        for s in p.slots:
            market = sum(s[a] * returns[a][t] for a in ASSETS) + monthly(s["alpha"])
            rates_k.append(growth(market, t, live))
        fmc_rates = [decrement(s["fmc"]) * live for s in p.slots]
        additions_k = [
            additions_pp * (after_charges[k] / fac if fac > 0 else weights[k]) for k in range(n)
        ]
        grown = [(after_charges[k] + additions_k[k]) * (1 + rates_k[k]) for k in range(n)]
        fmc_k = [grown[k] * fmc_rates[k] for k in range(n)]
        close = [grown[k] - fmc_k[k] for k in range(n)]
        fund_close = sum(close)
        fund_growth = sum((after_charges[k] + additions_k[k]) * rates_k[k] for k in range(n))
        fund_fmc = sum(fmc_k)
        close_total_prev = fund_close
        fv_sum = (0.0 if year_start else fv_sum) + fund_close * (t > 0)

        # Reduced paid-up cohort.
        rpu_open = sum(rpu)
        rpu_admin_req = R_begin * admin_rate
        rpu_gc_req = rpu_open * gc_rate
        rpu_before = rpu_open - rpu_admin_req - rpu_gc_req
        rpu_floor = v["min_db_premium_multiple"] * rpu_tpp
        if v["death_benefit_type"] == 1:
            rpu_sar = max(max(pusa, rpu_floor) - rpu_before, 0)
        else:
            rpu_sar = max(pusa, rpu_floor - rpu_before)
        rpu_mc_req = rpu_sar * mc_rate / 12000 * live
        rpu_requested = rpu_admin_req + rpu_gc_req + rpu_mc_req
        rpu_scale = rpu_open / rpu_requested if rpu_requested > max(rpu_open, 0) else 1.0
        rpu_admin, rpu_gc, rpu_mc = (x * rpu_scale for x in (rpu_admin_req, rpu_gc_req, rpu_mc_req))
        rpu_deducted = rpu_admin + rpu_gc + rpu_mc
        rpu_retention = (
            1 - rpu_deducted / rpu_open if rpu_open > rpu_requested and rpu_open > 0 else 0.0
        )
        rpu_after = [x * rpu_retention for x in rpu]
        rpu_grown = [rpu_after[k] * (1 + rates_k[k]) for k in range(n)]
        rpu_fmc_k = [rpu_grown[k] * fmc_rates[k] for k in range(n)]
        rpu_after_fmc = [rpu_grown[k] - rpu_fmc_k[k] for k in range(n)]
        rpu_after_fmc_total = sum(rpu_after_fmc)
        rpu_fmc = sum(rpu_fmc_k)
        rpu_growth = sum(rpu_after[k] * rates_k[k] for k in range(n))
        rpu = [rpu_after_fmc[k] * R_survival + to_rpu * close[k] for k in range(n)]
        rpu_close = sum(rpu)
        pusa_open, rpu_tpp_open = pusa, rpu_tpp
        pusa = pusa * R_survival + to_rpu * p.sum_assured * inst / max(p.instalments_payable, 1)
        rpu_tpp = rpu_tpp * R_survival + to_rpu * tpp

        # Discontinuance charge and the DPF.
        high = p.annual_premium > v["disc_ap_threshold"]
        band = "high" if high else "low"
        disc_pct = clamp_year(b.scales[f"disc_pct_{band}"], py, vid)
        disc_cap = clamp_year(b.scales[f"disc_cap_{band}"], py, vid)
        disc_charge_pp = min(disc_pct * p.annual_premium, fund_close, disc_cap) * lock_in * live
        disc_income = (to_dpf + paid_out_A * lock_in) * disc_charge_pp
        f = p.dpf_fund
        dpf_market = sum(f[f"w_{a}"] * returns[a][t] for a in ASSETS) + monthly(f["alpha"])
        dpf_return = growth(dpf_market, t, live)
        dpf_guaranteed = monthly(p.dpf_min_rate) * live
        dpf_open = dpf
        dpf_credited = dpf_open * max(dpf_return, dpf_guaranteed)
        dpf_grown = dpf_open + dpf_credited
        dpf_fmc = dpf_grown * decrement(f["fmc"]) * live
        dpf_guarantee_cost = dpf_open * max(dpf_guaranteed - dpf_return, 0)
        dpf_after = dpf_grown - dpf_fmc
        dpf_death = dpf_after * q
        dpf_inflow = to_dpf * (fund_close - disc_charge_pp)
        dpf_release = (dpf_after - dpf_death + dpf_inflow) * lockin_due
        dpf = dpf_after - dpf_death + dpf_inflow - dpf_release

        # Benefits.
        if v["death_benefit_type"] == 1:
            db = max(sa_eff, floor_db, fund_close)
            db_R = max(pusa_open, rpu_floor, rpu_after_fmc_total)
        else:
            db = max(sa_eff + fund_close, floor_db)
            db_R = max(pusa_open + rpu_after_fmc_total, rpu_floor)
        death_unit_A = deaths_A * fund_close
        death_non_unit_A = deaths_A * (db - fund_close)
        surrender_unit_A = paid_out_A * (fund_close - disc_charge_pp)
        maturity_unit_A = maturities_A * fund_close
        roc_pp = (
            v["romc_fraction"] * mc_cum
            + v["ropac_fraction"] * pac_cum
            + v["roadmin_fraction"] * admin_cum
        )
        return_of_charges = maturities_A * roc_pp
        gmmb_pp = v["gmmb_on"] * max(v["gmmb_premium_multiple"] * tpp - fund_close - roc_pp, 0)
        maturity_guarantee_A = maturities_A * gmmb_pp
        death_unit_R = q * rpu_after_fmc_total
        death_non_unit_R = q * (db_R - rpu_after_fmc_total)
        surrender_unit_R = rpu_after_fmc_total * surrenders_R / R_begin if R_begin > 0 else 0.0
        expiry_unit_R = rpu_after_fmc_total * expiries_R / R_begin if R_begin > 0 else 0.0
        maturity_share_R = maturities_R / R_begin if R_begin > 0 else 0.0
        maturity_unit_R = rpu_after_fmc_total * maturity_share_R
        maturity_guarantee_R = v["gmmb_on"] * max(
            v["gmmb_premium_multiple"] * rpu_tpp_open * maturity_share_R - maturity_unit_R, 0
        )
        withdrawals = A_begin * pw_pp
        additions = A_begin * additions_pp
        unit_exits = (
            death_unit_A
            + surrender_unit_A
            + maturity_unit_A
            + dpf_death
            + dpf_release
            + death_unit_R
            + surrender_unit_R
            + expiry_unit_R
            + maturity_unit_R
        )
        non_unit_benefits = (
            death_non_unit_A
            + death_non_unit_R
            + return_of_charges
            + maturity_guarantee_A
            + maturity_guarantee_R
            + additions
            + dpf_guarantee_cost
        )

        # Charges and the unit reserve.
        premiums = premium_pp * A_begin
        pac = A_begin * pac_pp
        admin = A_begin * admin_pp + rpu_admin
        mortality_charge = A_begin * mc_pp + rpu_mc
        guarantee = A_begin * gc_pp + rpu_gc
        fmc_A = A_begin * fund_fmc
        charges_start = pac + admin + mortality_charge + guarantee
        charges_end = fmc_A + rpu_fmc + dpf_fmc + disc_income
        charges = charges_start + charges_end
        unit_reserve_A = A_end * fund_close
        unit_reserve = unit_reserve_A + rpu_close + dpf

        # General fund cashflows.
        inflation = (1 + par["Inflation"]) ** ((t - 1) / 12)
        commissions = clamp_year(b.commission, py, p.channel) * premiums * (t > 0)
        initial = (
            (
                par["initial_fixed_expense"]
                + par["initial_percent_premium_expense"] * premium_pp
                + par["initial_percent_sa_expense"] * p.sum_assured
            )
            * (1 + mad_e)
            * A_begin
            * (pm == 1)
            * (t > 0)
        )
        renewal = (
            par["renewal_fixed_expense"]
            / 12
            * inflation
            * (1 + mad_e)
            * (A_begin + R_begin + D_begin)
            * (py >= 2)
            * live
        )
        fund_expenses = par["fund_expense_rate"] / 12 * (1 + mad_e) * unit_reserve_prev * (t > 0)
        claim_expenses = (
            par["claim_expense"] * inflation * (1 + mad_e) * (deaths_A + deaths_R + deaths_D)
        ) * (t > 0)
        acquisition = commissions + initial
        expense = renewal + fund_expenses
        interest = (charges_start - acquisition - expense) * gf_rate[t] * (t > 0)
        net_cashflows = -(
            charges - acquisition - expense - claim_expenses - non_unit_benefits + interest
        ) * (t > 0)
        unit_profit = (
            A_begin * allocated_pp
            + additions
            + A_begin * fund_growth
            + rpu_growth
            + dpf_credited
            - (admin + mortality_charge + guarantee + charges_end)
            - unit_exits
            - withdrawals
            - (unit_reserve - unit_reserve_prev) * (t > 0)
        ) * (t > 0)
        unit_reserve_prev = unit_reserve

        for name, value in (
            ("A_begin", A_begin),
            ("D_begin", D_begin),
            ("R_begin", R_begin),
            ("A_end", A_end),
            ("D_end", D_end),
            ("R_end", R_end),
            ("lives_end", A_end + D_end + R_end),
            ("deaths_A", deaths_A),
            ("deaths_D", deaths_D),
            ("deaths_R", deaths_R),
            ("surrenders_A", surrenders_A),
            ("cessations_A", cessations_A),
            ("paid_out_A", paid_out_A),
            ("to_dpf", to_dpf),
            ("to_rpu", to_rpu),
            ("lockin_exits_D", lockin_exits_D),
            ("surrenders_R", surrenders_R),
            ("expiries_R", expiries_R),
            ("maturities_A", maturities_A),
            ("maturities_R", maturities_R),
            ("maturities", maturities_A + maturities_R),
            ("premium_income", premiums),
            ("allocated_premiums", A_begin * allocated_pp),
            ("pac_income", pac),
            ("admin_income", admin),
            ("mc_income", mortality_charge),
            ("gc_income", guarantee),
            ("fmc_income_A", fmc_A),
            ("rpu_fmc_total", rpu_fmc),
            ("dpf_fmc", dpf_fmc),
            ("disc_charge_income", disc_income),
            ("charges_start", charges_start),
            ("charges_end", charges_end),
            ("charge_income", charges),
            ("unit_reserve_A", unit_reserve_A),
            ("dpf_close", dpf),
            ("rpu_close_total", rpu_close),
            ("unit_reserve", unit_reserve),
            ("death_unit_A", death_unit_A),
            ("surrender_unit_A", surrender_unit_A),
            ("maturity_unit_A", maturity_unit_A),
            ("dpf_death_paid", dpf_death),
            ("dpf_lockin_paid", dpf_release),
            ("death_unit_R", death_unit_R),
            ("surrender_unit_R", surrender_unit_R),
            ("expiry_unit_R", expiry_unit_R),
            ("maturity_unit_R", maturity_unit_R),
            ("partial_withdrawal_outgo", withdrawals),
            ("unit_benefit_outgo", unit_exits + withdrawals),
            ("death_non_unit_A", death_non_unit_A),
            ("death_non_unit_R", death_non_unit_R),
            ("return_of_charges", return_of_charges),
            ("maturity_guarantee_A", maturity_guarantee_A),
            ("maturity_guarantee_R", maturity_guarantee_R),
            ("addition_outgo", additions),
            ("dpf_guarantee_cost", dpf_guarantee_cost),
            ("non_unit_benefit_outgo", non_unit_benefits),
            ("residual_additions", 0.0),
            ("commissions", commissions),
            ("initial_expense", initial),
            ("renewal_expenses", renewal),
            ("fund_expenses", fund_expenses),
            ("claim_expenses", claim_expenses),
            ("interest_on_cashflows", interest),
            ("net_cashflows", net_cashflows),
            ("sum_at_risk", A_end * sar + rpu_sar * R_survival),
            ("unit_segment_profit", unit_profit),
            ("policy_month", pm),
            ("in_term", pm < term_m),
        ):
            put(name, value)

    # Backward: the discounted cashflow general fund reserve at the end of each month.
    dcf = [0.0] * horizon
    pv_next = 0.0
    for t in range(horizon - 1, -1, -1):
        dcf[t] = pv_next
        pv_next = (pv_next + out["net_cashflows"][t]) / (1 + gf_rate[t])
    out["gf_reserve_dcf"] = dcf
    mc_next = out["mc_income"][1:] + [0.0]
    out["gf_reserve_floor"] = [par["reserve_floor_days"] / 365 * 12 * x for x in mc_next]
    out["gf_reserve_held"] = [
        max(d, 0.0, f) for d, f in zip(dcf, out["gf_reserve_floor"], strict=True)
    ]
    out["revival_provision"] = [
        par["revival_strain_dpf"] * d + par["revival_strain_rpu"] * r
        for d, r in zip(out["dpf_close"], out["rpu_close_total"], strict=True)
    ]
    out["non_unit_reserve"] = [
        h + r for h, r in zip(out["gf_reserve_held"], out["revival_provision"], strict=True)
    ]
    out["total_reserve"] = [
        u + n for u, n in zip(out["unit_reserve"], out["non_unit_reserve"], strict=True)
    ]
    lives = [max(a + m, 1e-6) for a, m in zip(out["lives_end"], out["maturities"], strict=True)]
    out["eligible_lives"] = [
        a + m for a, m in zip(out["lives_end"], out["maturities"], strict=True)
    ]
    for name, source in (
        ("gf_reserve_pp", "gf_reserve_held"),
        ("non_unit_reserve_pp", "non_unit_reserve"),
        ("total_reserve_pp", "total_reserve"),
    ):
        out[name] = [x / n for x, n in zip(out[source], lives, strict=True)]
    out["_gf_rate"] = gf_rate
    out["_rf"] = rf
    out["_roi"] = rate["roi"]
    return out


def capital(
    p: Policy, b: Basis, data: dict[str, list[float]], reserve_pp: list[float]
) -> dict[str, list[float]]:
    """Solvency capital on one basis's lives and unit reserve."""
    par = b.params
    guaranteed = p.variant["gmmb_on"] == 1
    f1 = par[
        "reserve_capital_factor_guarantee" if guaranteed else "reserve_capital_factor_no_guarantee"
    ]
    f2 = par["sar_capital_factor_guarantee" if guaranteed else "sar_capital_factor_no_guarantee"]
    ratio = par["target_capital_ratio"]
    horizon = len(reserve_pp)
    part1, part2, capital_, increase, interest = ([0.0] * horizon for _ in range(5))
    for t in range(horizon):
        reserves = reserve_pp[t] * data["eligible_lives"][t]
        part1[t] = f1 * (data["unit_reserve"][t] + reserves) * ratio
        part2[t] = f2 * data["sum_at_risk"][t] * ratio * data["in_term"][t]
        capital_[t] = max(part1[t] + part2[t], 0.0) if t > 0 else 0.0
        if t > 0:
            increase[t] = capital_[t] - capital_[t - 1]
            interest[t] = capital_[t - 1] * data["_gf_rate"][t]
    return {
        "part1_sm": part1,
        "part2_sm": part2,
        "required_solvency_capital": capital_,
        "increase_in_solvency_capital": increase,
        "interest_on_solvency_capital": interest,
    }


def end_of_month_pv(values: list[float], rates: list[float], start: bool = False) -> list[float]:
    """Variant A (end-of-month cashflows), or variant B when `start`, reported at the end
    of each month."""
    horizon = len(values)
    out = [0.0] * horizon
    pv = 0.0
    for t in range(horizon - 1, -1, -1):
        out[t] = pv
        pv = values[t] + pv / (1 + rates[t]) if start else (pv + values[t]) / (1 + rates[t])
    return out


def project(p: Policy, b: Basis, horizon: int) -> dict[str | None, dict[str, list[float]]]:
    """Every basis, then capital, the best-estimate profit chain and MCEV."""
    par = b.params
    tax, transfer = par["Tax Rate"], par["profit_transfer_rate"]
    data = {basis: project_basis(p, b, basis, horizon) for basis in BASES}
    reserve_pp = data["reserving"]["non_unit_reserve_pp"]
    for basis in BASES:
        data[basis].update(capital(p, b, data[basis], reserve_pp))
    be, mc = data["be"], data["mc"]
    roi, rf = be["_roi"], be["_rf"]
    names = (
        "be_net_cf",
        "be_reserves",
        "increase_in_reserves",
        "interest_on_reserves",
        "profit_before_tax",
        "profit_transfer",
        "tax",
        "net_profit_before_sm",
        "cost_of_capital",
        "net_profit_after_sm",
        "non_unit_segment_profit",
        "total_profit",
        "mc_net_cf",
        "mc_reserves",
        "mc_increase_in_reserves",
        "mcev_interest_on_reserve",
        "mcev_profit_before_tax",
        "mcev_profit_transfer",
        "mcev_tax",
        "mcev_net_profit",
        "interest_on_sm_mc",
        "frictional_cost",
        "crnhr_charge",
    )
    shared = {name: [0.0] * horizon for name in names}
    s = shared
    for t in range(horizon):
        positive = t > 0
        s["be_net_cf"][t] = -be["net_cashflows"][t] * positive
        s["be_reserves"][t] = max(reserve_pp[t] * be["eligible_lives"][t], 0.0) * positive
        previous = s["be_reserves"][t - 1] if t > 0 else 0.0
        s["increase_in_reserves"][t] = s["be_reserves"][t] - previous
        s["interest_on_reserves"][t] = previous * roi[t] * positive
        pbt = s["be_net_cf"][t] - s["increase_in_reserves"][t] + s["interest_on_reserves"][t]
        s["profit_before_tax"][t] = pbt
        s["profit_transfer"][t] = pbt * transfer * positive
        s["tax"][t] = (pbt - s["profit_transfer"][t]) * tax * positive
        s["net_profit_before_sm"][t] = pbt - s["profit_transfer"][t] - s["tax"][t]
        interest = be["interest_on_solvency_capital"][t]
        s["cost_of_capital"][t] = (
            be["increase_in_solvency_capital"][t] - interest * (1 - transfer) * (1 - tax)
        ) * positive
        s["net_profit_after_sm"][t] = s["net_profit_before_sm"][t] - s["cost_of_capital"][t]
        s["non_unit_segment_profit"][t] = pbt
        s["total_profit"][t] = be["unit_segment_profit"][t] + pbt
        s["mc_net_cf"][t] = -mc["net_cashflows"][t] * positive
        s["mc_reserves"][t] = max(reserve_pp[t] * mc["eligible_lives"][t], 0.0) * positive
        previous = s["mc_reserves"][t - 1] if t > 0 else 0.0
        s["mc_increase_in_reserves"][t] = s["mc_reserves"][t] - previous
        s["mcev_interest_on_reserve"][t] = previous * rf[t] * positive
        mpbt = (
            s["mc_net_cf"][t] - s["mc_increase_in_reserves"][t] + s["mcev_interest_on_reserve"][t]
        )
        s["mcev_profit_before_tax"][t] = mpbt
        s["mcev_profit_transfer"][t] = mpbt * transfer
        s["mcev_tax"][t] = (mpbt - s["mcev_profit_transfer"][t]) * tax
        s["mcev_net_profit"][t] = mpbt - s["mcev_profit_transfer"][t] - s["mcev_tax"][t]
        s["interest_on_sm_mc"][t] = mc["interest_on_solvency_capital"][t]
        s["frictional_cost"][t] = s["interest_on_sm_mc"][t] * (tax + (1 - tax) * transfer)
        s["crnhr_charge"][t] = par["cost_of_capital_rate"] / 12 * mc["required_solvency_capital"][t]
    s["pvfp"] = end_of_month_pv(s["mcev_net_profit"], rf)
    s["pv_premium"] = end_of_month_pv(mc["premium_income"], rf, start=True)
    s["fcc"] = end_of_month_pv(s["frictional_cost"], rf)
    s["crnhr"] = end_of_month_pv(s["crnhr_charge"], rf)
    s["vif"] = [a - f - c for a, f, c in zip(s["pvfp"], s["fcc"], s["crnhr"], strict=True)]
    s["gf_bel"] = [-x for x in end_of_month_pv(s["mc_net_cf"], rf)]
    s["bel"] = [u + g for u, g in zip(mc["unit_reserve"], s["gf_bel"], strict=True)]
    s["bel_pp"] = [
        x / n if n else math.nan for x, n in zip(s["bel"], mc["eligible_lives"], strict=True)
    ]
    s["annualised_premium"] = [p.annual_premium] * horizon
    return {**data, None: s}
