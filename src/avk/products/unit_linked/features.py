"""Field catalogue of the unit-linked product and regulation tables: one source of truth
for each field's kind, allowed values and range, checked vectorised over table rows."""

from dataclasses import dataclass
from typing import Literal

import numpy as np
import polars as pl

from avk.products.unit_linked.bindings import ASSET_CLASSES, MAX_FUND_SLOTS

Kind = Literal["flag", "code", "int", "rate", "amount", "multiple"]
FLAG = frozenset({0.0, 1.0})


@dataclass(frozen=True)
class FieldRule:
    """One numeric field: `allowed` lists the only values for flags and codes; `minimum`
    and `maximum` bound the others (closed unless `minimum_open` / `maximum_open`)."""

    name: str
    kind: Kind
    allowed: frozenset[float] | None
    minimum: float | None
    maximum: float | None
    maximum_open: bool
    minimum_open: bool = False
    meaning: str = ""


def flag(name: str, meaning: str) -> FieldRule:
    return FieldRule(name, "flag", FLAG, None, None, False, meaning=meaning)


def code(name: str, values: tuple[int, ...], meaning: str) -> FieldRule:
    return FieldRule(
        name, "code", frozenset(float(v) for v in values), None, None, False, False, meaning
    )


def integer(name: str, minimum: float, meaning: str) -> FieldRule:
    return FieldRule(name, "int", None, minimum, None, False, meaning=meaning)


def rate(name: str, meaning: str, maximum: float = 1.0, maximum_open: bool = False) -> FieldRule:
    return FieldRule(name, "rate", None, 0.0, maximum, maximum_open, meaning=meaning)


def amount(name: str, meaning: str) -> FieldRule:
    return FieldRule(name, "amount", None, 0.0, None, False, meaning=meaning)


def multiple(name: str, meaning: str) -> FieldRule:
    return FieldRule(name, "multiple", None, 0.0, None, False, meaning=meaning)


VARIANT_FIELDS = (
    integer("variant_id", 0, "Unique integer key of the variant; keys `ul_charge_scales`"),
    integer("regime_id", 0, "Regulatory regime (`regime_id` of `ul_regulatory_caps`)"),
    flag("single_premium", "1 single premium; 0 regular or limited pay"),
    code(
        "death_benefit_type",
        (1, 2),
        "1 Type I (higher of cover and fund); 2 Type II (cover plus fund)",
    ),
    multiple("min_db_premium_multiple", "Death benefit floor as a multiple of premiums paid"),
    integer(
        "lock_in_months", 0, "Lock-in period in months; discontinuance inside it goes to the DPF"
    ),
    flag("dpf_enabled", "1 discontinuance inside the lock-in moves the fund to the DPF"),
    code(
        "rpu_mode",
        (0, 1, 2),
        "Cessation after lock-in: 0 pays out, 1 paid-up to maturity, 2 paid-up to revival end",
    ),
    integer("revival_period_months", 1, "Revival period of a reduced paid-up policy, in months"),
    flag("pw_allowed", "1 partial withdrawals are projected"),
    integer("pw_start_year", 1, "First policy year in which partial withdrawals occur"),
    flag(
        "pw_reduces_sa",
        "1 withdrawals of the current and previous policy year reduce the sum assured",
    ),
    flag("loyalty_on", "1 loyalty additions are credited"),
    code(
        "loyalty_basis",
        (1, 2),
        "Loyalty basis: 1 average month-end fund of the year, 2 annualised premium",
    ),
    integer(
        "loyalty_start_year", 1, "First policy year at whose end loyalty additions are credited"
    ),
    flag(
        "loyalty_requires_full_premiums", "1 loyalty additions only while all premiums due are paid"
    ),
    rate(
        "guaranteed_addition_rate",
        "Guaranteed addition each policy year, a fraction of the annualised premium",
    ),
    rate("romc_fraction", "Fraction of cumulative mortality charges returned at maturity"),
    rate(
        "ropac_fraction", "Fraction of cumulative premium allocation charges returned at maturity"
    ),
    rate("roadmin_fraction", "Fraction of cumulative administration charges returned at maturity"),
    flag("gmmb_on", "1 guaranteed maturity benefit"),
    multiple("gmmb_premium_multiple", "Guaranteed maturity benefit as a multiple of premiums paid"),
    rate("guarantee_charge", "Annual guarantee charge, a fraction of the fund", maximum_open=True),
    rate("admin_escalation", "Annual escalation of the administration charge", maximum_open=True),
    multiple("mortality_charge_multiplier", "Multiplier applied to the mortality charge table"),
    amount(
        "disc_ap_threshold", "Annualised premium above which the high discontinuance scale applies"
    ),
    flag("auto_rebalance", "1 funds are rebalanced to the premium allocation at each anniversary"),
    flag("riy_additions_on", "1 reduction-in-yield residual additions (read from phase P3)"),
    flag("topup_on", "1 permits top-up premiums and associated cover and units"),
    multiple("topup_sa_multiple", "Additional cover as a multiple of gross top-up premiums"),
    integer("topup_lock_in_months", 0, "Top-up partial withdrawal lock from most recent payment"),
    amount("switch_charge", "Charge per month in which a strategy switches units"),
    integer("highest_nav_start_month", 0, "First policy month of the highest-NAV window; 0 off"),
)

STRATEGY_FIELDS = (
    code("mode", (0, 1, 2, 3, 4), "None, lifecycle age/remaining years, STP share/amount"),
    FieldRule("source_slot", "int", None, 0, MAX_FUND_SLOTS, False),
    rate("share", "Lifecycle equity target share or the STP share of the source"),
    amount("amount", "Fixed STP amount; zero for other modes"),
    *(rate(f"target_{k}", f"Destination weight of slot {k}") for k in range(1, MAX_FUND_SLOTS + 1)),
)

FUND_FIELDS = (
    FieldRule(
        "unit_price", "amount", None, 0.0, None, False, True, "Unit price at the valuation date"
    ),
    rate("fmc", "Annual fund management charge", maximum_open=True),
    FieldRule(
        "alpha",
        "rate",
        None,
        -1.0,
        None,
        False,
        True,
        "Annual return over the asset mix (negative for tracking cost)",
    ),
    *(rate(f"w_{a}", f"Weight of asset class {a} in the fund mix") for a in ASSET_CLASSES),
    flag("selectable", "1 the fund may receive premiums; 0 for the DPF and closed funds"),
    flag("is_dpf", "1 for the Discontinued Policy Fund (exactly one fund)"),
    code(
        "guarantee_type", (0, 1, 2), "0 none; 1 highest NAV; 2 capital protection (mechanics later)"
    ),
    code("risk_class", (1, 2, 3, 4, 5), "Risk class from 1 (low) to 5 (high)"),
)

CAP_FIELDS = (
    integer("regime_id", 0, "Unique integer key of the regime"),
    flag("caps_apply", "1 the caps below are enforced; 0 (UNCAPPED) none is"),
    rate("pac_max", "Maximum premium allocation charge rate in any year"),
    FieldRule(
        "pac_ratio_max_first5",
        "multiple",
        None,
        1.0,
        None,
        False,
        meaning="Maximum ratio of highest to lowest allocation charge in years 1-5",
    ),
    amount("admin_max_monthly", "Maximum monthly administration charge"),
    rate("admin_escalation_max", "Maximum annual escalation of the administration charge"),
    rate("fmc_max", "Maximum annual fund management charge"),
    rate("dpf_fmc_max", "Annual fund management charge of the DPF (and its maximum)"),
    rate("guarantee_charge_max", "Maximum annual guarantee charge"),
    multiple("min_db_premium_multiple", "Minimum death benefit as a multiple of premiums paid"),
    integer("lock_in_months_min", 0, "Minimum lock-in period in months"),
    rate("dpf_min_rate", "Minimum guaranteed annual rate credited by the DPF"),
    multiple(
        "min_sa_multiple_regular_young",
        "Minimum cover multiple of AP, regular premium, below the age threshold",
    ),
    multiple(
        "min_sa_multiple_regular_old",
        "Minimum cover multiple of AP, regular premium, from the age threshold",
    ),
    integer(
        "regular_age_threshold", 0, "Entry age from which the regular-premium old multiple applies"
    ),
    multiple(
        "min_sa_multiple_single_young",
        "Minimum cover multiple of the single premium below the age threshold",
    ),
    multiple(
        "min_sa_multiple_single_old",
        "Minimum cover multiple of the single premium from the age threshold",
    ),
    integer(
        "single_age_threshold", 0, "Entry age from which the single-premium old multiple applies"
    ),
    amount("switch_charge_max", "Maximum charge per switch"),
    amount("pw_charge_max", "Maximum charge per partial withdrawal"),
    amount("misc_charge_max", "Maximum miscellaneous charge per alteration"),
)

DISC_CAP_FIELDS = (
    rate("disc_pct_low", "Discontinuance charge, fraction of AP, AP up to the threshold"),
    amount("disc_cap_low", "Discontinuance charge cap, AP up to the threshold"),
    rate("disc_pct_high", "Discontinuance charge, fraction of AP, AP above the threshold"),
    amount("disc_cap_high", "Discontinuance charge cap, AP above the threshold"),
)

SCALE_FIELDS = (
    rate("premium_allocation_rate", "Premium allocation charge, a fraction of each premium"),
    rate("topup_allocation_rate", "Allocation charge, a fraction of each gross top-up"),
    amount("admin_charge_monthly", "Monthly administration charge before escalation"),
    rate("loyalty_rate", "Loyalty addition rate at the end of the policy year"),
    rate("booster_rate", "Booster addition rate at the end of the policy year"),
    *DISC_CAP_FIELDS,
)

RIY_FIELDS = (rate("riy_max", "Maximum reduction in yield after the completed years"),)


def _number(value: float) -> str:
    return f"{value:g}"


def check_rules(frame: pl.DataFrame, rules: tuple[FieldRule, ...], table: str) -> list[str]:
    """Messages for every field of `frame` (one column per rule) that breaks its rule."""
    messages = []
    for rule in rules:
        if rule.name not in frame.columns:
            messages.append(f"{table}: missing field {rule.name}")
            continue
        values = frame[rule.name].cast(pl.Float64, strict=False).to_numpy()
        prefix = f"{table}: {rule.name}"
        if not np.isfinite(values).all():
            messages.append(f"{prefix} must be finite")
            continue
        if rule.allowed is not None:
            if not np.isin(values, sorted(rule.allowed)).all():
                allowed = ", ".join(_number(v) for v in sorted(rule.allowed))
                messages.append(f"{prefix} must be one of [{allowed}]")
            continue
        if rule.kind == "int" and not np.equal(values, np.floor(values)).all():
            messages.append(f"{prefix} must be an integer")
        if rule.minimum is not None:
            if rule.minimum_open and (values <= rule.minimum).any():
                messages.append(f"{prefix} must exceed {_number(rule.minimum)}")
            elif not rule.minimum_open and (values < rule.minimum).any():
                messages.append(f"{prefix} must be at least {_number(rule.minimum)}")
        if rule.maximum is not None:
            if rule.maximum_open and (values >= rule.maximum).any():
                messages.append(f"{prefix} must be below {_number(rule.maximum)}")
            elif not rule.maximum_open and (values > rule.maximum).any():
                messages.append(f"{prefix} must be at most {_number(rule.maximum)}")
    return messages
