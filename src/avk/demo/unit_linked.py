"""Invented unit-linked demo basis: fund universe, variants, regulatory caps and scales.

Every value is invented for teaching (see demo/README.md). The IRDAI_2024 regime holds
the published caps as read by the maintainer; re-verify before relying on them.
"""

from collections.abc import Callable
from typing import Any

from avk.products.unit_linked.bindings import ASSET_CLASSES
from avk.products.unit_linked.features import STRATEGY_FIELDS

YEARS = 40
Put = Callable[[str, list[dict[str, Any]], str], None]

# Code, FMC, unit price, alpha, guarantee type, risk class, asset mix (fractions).
FUNDS: tuple[tuple[str, float, float, float, int, int, dict[str, float]], ...] = (
    ("EQ_LARGE_CAP", 0.0135, 42.18, 0.0050, 0, 4, {"eq_large": 0.92, "money_market": 0.08}),
    ("EQ_INDEX", 0.0050, 31.64, -0.0015, 0, 4, {"eq_large": 0.98, "money_market": 0.02}),
    (
        "EQ_FLEXI_CAP",
        0.0135,
        27.90,
        0.0060,
        0,
        4,
        {"eq_large": 0.55, "eq_mid": 0.25, "eq_small": 0.12, "money_market": 0.08},
    ),
    (
        "EQ_MID_CAP",
        0.0135,
        58.25,
        0.0070,
        0,
        5,
        {"eq_large": 0.15, "eq_mid": 0.75, "money_market": 0.10},
    ),
    (
        "EQ_SMALL_CAP",
        0.0135,
        64.40,
        0.0100,
        0,
        5,
        {"eq_mid": 0.15, "eq_small": 0.75, "money_market": 0.10},
    ),
    (
        "EQ_VALUE",
        0.0135,
        36.72,
        0.0040,
        0,
        4,
        {"eq_large": 0.60, "eq_mid": 0.25, "eq_small": 0.07, "money_market": 0.08},
    ),
    (
        "EQ_ESG",
        0.0125,
        18.35,
        0.0020,
        0,
        4,
        {"eq_large": 0.80, "eq_mid": 0.12, "money_market": 0.08},
    ),
    (
        "EQ_INFRA_THEME",
        0.0135,
        22.06,
        0.0030,
        0,
        5,
        {
            "eq_large": 0.45,
            "eq_mid": 0.30,
            "eq_small": 0.10,
            "real_assets": 0.07,
            "money_market": 0.08,
        },
    ),
    ("EQ_GLOBAL", 0.0135, 15.88, 0.0010, 0, 5, {"eq_global": 0.90, "money_market": 0.10}),
    (
        "HY_AGGRESSIVE",
        0.0125,
        33.47,
        0.0030,
        0,
        4,
        {
            "eq_large": 0.55,
            "eq_mid": 0.15,
            "gov_long": 0.15,
            "corp_bond": 0.10,
            "money_market": 0.05,
        },
    ),
    (
        "HY_BALANCED",
        0.0120,
        29.81,
        0.0020,
        0,
        3,
        {
            "eq_large": 0.30,
            "eq_mid": 0.10,
            "gov_long": 0.30,
            "corp_bond": 0.25,
            "money_market": 0.05,
        },
    ),
    (
        "HY_CONSERVATIVE",
        0.0110,
        24.12,
        0.0010,
        0,
        2,
        {
            "eq_large": 0.15,
            "gov_long": 0.40,
            "gov_short": 0.10,
            "corp_bond": 0.30,
            "money_market": 0.05,
        },
    ),
    (
        "HY_DYNAMIC",
        0.0125,
        20.57,
        0.0020,
        0,
        3,
        {
            "eq_large": 0.40,
            "eq_mid": 0.10,
            "gov_long": 0.25,
            "corp_bond": 0.15,
            "money_market": 0.10,
        },
    ),
    (
        "DT_GILT",
        0.0090,
        26.33,
        0.0000,
        0,
        2,
        {"gov_long": 0.85, "gov_short": 0.10, "money_market": 0.05},
    ),
    (
        "DT_CORP_BOND",
        0.0100,
        30.95,
        0.0010,
        0,
        2,
        {"gov_long": 0.10, "corp_bond": 0.80, "money_market": 0.10},
    ),
    (
        "DT_SHORT_DURATION",
        0.0080,
        19.46,
        0.0000,
        0,
        2,
        {"gov_short": 0.55, "corp_bond": 0.30, "money_market": 0.15},
    ),
    ("MM_LIQUID", 0.0060, 21.70, 0.0000, 0, 1, {"gov_short": 0.10, "money_market": 0.90}),
    ("ALT_GOLD", 0.0100, 12.84, -0.0020, 0, 3, {"gold": 0.95, "money_market": 0.05}),
    ("ALT_REAL_ASSETS", 0.0125, 11.29, 0.0000, 0, 4, {"real_assets": 0.90, "money_market": 0.10}),
    (
        "GT_HIGHEST_NAV",
        0.0135,
        10.00,
        0.0000,
        1,
        3,
        {"eq_large": 0.50, "gov_long": 0.40, "money_market": 0.10},
    ),
    (
        "GT_CAPITAL_PROTECT",
        0.0135,
        10.00,
        0.0000,
        2,
        2,
        {"eq_large": 0.20, "gov_long": 0.50, "gov_short": 0.25, "money_market": 0.05},
    ),
    ("DPF", 0.0050, 14.62, 0.0000, 0, 1, {"gov_short": 0.40, "money_market": 0.60}),
)
DPF_CODE = "DPF"

# The variant fields shared by every demo variant, then each variant's differences.
BASE_VARIANT = {
    "regime_id": 0,
    "single_premium": 0,
    "death_benefit_type": 1,
    "min_db_premium_multiple": 1.05,
    "lock_in_months": 60,
    "dpf_enabled": 1,
    "rpu_mode": 2,
    "revival_period_months": 36,
    "pw_allowed": 1,
    "pw_start_year": 6,
    "pw_reduces_sa": 0,
    "loyalty_on": 0,
    "loyalty_basis": 1,
    "loyalty_start_year": 10,
    "loyalty_requires_full_premiums": 1,
    "guaranteed_addition_rate": 0.0,
    "romc_fraction": 0.0,
    "ropac_fraction": 0.0,
    "roadmin_fraction": 0.0,
    "gmmb_on": 0,
    "gmmb_premium_multiple": 0.0,
    "guarantee_charge": 0.0,
    "admin_escalation": 0.0,
    "mortality_charge_multiplier": 1.0,
    "disc_ap_threshold": 50000.0,
    "auto_rebalance": 0,
    "riy_additions_on": 1,
}
VARIANTS: dict[str, dict[str, float]] = {
    "ULIP_CLASSIC": {"variant_id": 0, "loyalty_on": 1},
    "ULIP_WEALTH_T2": {
        "variant_id": 1,
        "death_benefit_type": 2,
        "loyalty_on": 1,
        "loyalty_start_year": 6,
        "romc_fraction": 1.0,
        "pw_reduces_sa": 1,
    },
    "ULIP_MATURITY_GUARANTEE": {
        "variant_id": 2,
        "gmmb_on": 1,
        "gmmb_premium_multiple": 1.0,
        "guarantee_charge": 0.004,
    },
    "ULIP_SINGLE": {
        "variant_id": 3,
        "single_premium": 1,
        "min_db_premium_multiple": 1.25,
        "rpu_mode": 1,
    },
    "ULIP_LIMITED_PAY_ROC": {
        "variant_id": 4,
        "ropac_fraction": 1.0,
        "roadmin_fraction": 1.0,
        "auto_rebalance": 1,
        "admin_escalation": 0.03,
    },
    "UL_INVESTMENT_BOND": {
        "variant_id": 5,
        "regime_id": 1,
        "single_premium": 1,
        "min_db_premium_multiple": 1.01,
        "lock_in_months": 0,
        "dpf_enabled": 0,
        "rpu_mode": 0,
        "pw_start_year": 2,
        "riy_additions_on": 0,
    },
}

REGIMES: dict[str, dict[str, float]] = {
    "IRDAI_2024": {
        "regime_id": 0,
        "caps_apply": 1,
        "pac_max": 0.125,
        "pac_ratio_max_first5": 3.0,
        "admin_max_monthly": 500.0,
        "admin_escalation_max": 0.05,
        "fmc_max": 0.0135,
        "dpf_fmc_max": 0.005,
        "guarantee_charge_max": 0.005,
        "min_db_premium_multiple": 1.05,
        "lock_in_months_min": 60,
        "dpf_min_rate": 0.04,
        "min_sa_multiple_regular_young": 7.0,
        "min_sa_multiple_regular_old": 5.0,
        "regular_age_threshold": 50,
        "min_sa_multiple_single_young": 1.25,
        "min_sa_multiple_single_old": 1.10,
        "single_age_threshold": 45,
        "switch_charge_max": 500.0,
        "pw_charge_max": 500.0,
        "misc_charge_max": 500.0,
    },
    # No limit applies; the values are explicit so that nothing defaults.
    "UNCAPPED": {
        "regime_id": 1,
        "caps_apply": 0,
        "pac_max": 1.0,
        "pac_ratio_max_first5": 1e12,
        "admin_max_monthly": 1e12,
        "admin_escalation_max": 1.0,
        "fmc_max": 1.0,
        "dpf_fmc_max": 1.0,
        "guarantee_charge_max": 1.0,
        "min_db_premium_multiple": 0.0,
        "lock_in_months_min": 0,
        "dpf_min_rate": 0.0,
        "min_sa_multiple_regular_young": 0.0,
        "min_sa_multiple_regular_old": 0.0,
        "regular_age_threshold": 0,
        "min_sa_multiple_single_young": 0.0,
        "min_sa_multiple_single_old": 0.0,
        "single_age_threshold": 0,
        "switch_charge_max": 1e12,
        "pw_charge_max": 1e12,
        "misc_charge_max": 1e12,
    },
}

# Discontinuance scale by policy year 1-4 (nil after): low and high annualised premium.
DISCONTINUANCE = {
    1: (0.20, 3000.0, 0.06, 6000.0),
    2: (0.15, 2000.0, 0.04, 5000.0),
    3: (0.10, 1500.0, 0.03, 4000.0),
    4: (0.05, 1000.0, 0.02, 2000.0),
}
RIY = {5: 0.04, 6: 0.0375, 7: 0.035, 8: 0.033, 9: 0.0315, 10: 0.03}


def riy_max(year: int) -> float:
    """Maximum reduction in yield after `year` completed years (years 1-4 as year 5)."""
    if year <= 10:
        return RIY[max(year, 5)]
    return 0.0275 if year <= 12 else 0.025 if year <= 14 else 0.0225


def discontinuance(year: int) -> tuple[float, float, float, float]:
    return DISCONTINUANCE.get(year, (0.0, 0.0, 0.0, 0.0))


def scale(variant: str, year: int) -> dict[str, float]:
    """One policy year of a variant's charge scale."""
    pac: float
    if variant == "ULIP_CLASSIC":
        pac = (0.06, 0.04, 0.04, 0.03, 0.03)[year - 1] if year <= 5 else 0.02 * (year <= 10)
        admin = 200.0 if year <= 5 else 150.0 if year <= 10 else 100.0
        loyalty = (
            0.0
            if year < 10
            else 0.0025
            if year == 10
            else 0.003
            if year <= 15
            else 0.004
            if year <= 20
            else 0.005
        )
        booster = 0.0
    elif variant == "ULIP_WEALTH_T2":
        pac = (0.05, 0.04, 0.04, 0.03, 0.03)[year - 1] if year <= 5 else 0.015 * (year <= 10)
        admin = 250.0 if year <= 5 else 200.0
        loyalty = 0.002 * (year >= 6)
        booster = 0.01 * (year % 5 == 0 and year >= 10)
    elif variant == "ULIP_MATURITY_GUARANTEE":
        pac = (
            (0.07, 0.05, 0.05, 0.04, 0.04)[year - 1] if year <= 5 else 0.02 if year <= 10 else 0.01
        )
        admin = 220.0
        loyalty = booster = 0.0
    elif variant == "ULIP_SINGLE":
        pac = 0.03
        admin = 150.0
        loyalty = booster = 0.0
    elif variant == "ULIP_LIMITED_PAY_ROC":
        pac = (0.08, 0.06, 0.06, 0.04, 0.04)[year - 1] if year <= 5 else 0.0
        admin = 300.0 if year <= 10 else 250.0
        loyalty = booster = 0.0
    else:  # UL_INVESTMENT_BOND
        pac = 0.01
        admin = 100.0
        loyalty = booster = 0.0
    low, cap_low, high, cap_high = (
        (0.0, 0.0, 0.0, 0.0) if variant == "UL_INVESTMENT_BOND" else discontinuance(year)
    )
    return {
        "premium_allocation_rate": pac,
        "topup_allocation_rate": 0.0,
        "admin_charge_monthly": admin,
        "loyalty_rate": loyalty,
        "booster_rate": booster,
        "disc_pct_low": low,
        "disc_cap_low": cap_low,
        "disc_pct_high": high,
        "disc_cap_high": cap_high,
    }


def lapse_rate(year: int) -> float:
    if year == 1:
        return 0.08
    if year <= 4:
        return 0.07 - 0.01 * (year - 2)
    if year == 5:
        return 0.12
    if year <= 10:
        return 0.09 - 0.0075 * (year - 6)
    return 0.04


def commission_rate(year: int) -> float:
    return 0.075 if year == 1 else 0.025 if year <= 5 else 0.015


ASSET_RETURNS = {
    "eq_large": 0.111,
    "eq_mid": 0.120,
    "eq_small": 0.128,
    "eq_global": 0.095,
    "gov_long": 0.072,
    "gov_short": 0.068,
    "corp_bond": 0.078,
    "money_market": 0.060,
    "gold": 0.080,
    "real_assets": 0.090,
}

PARAMETERS = {
    "Inflation": 0.05,
    "Tax Rate": 0.1456,
    "profit_transfer_rate": 0.02,
    "prudent_margin_mortality": 0.2,
    "prudent_margin_lapse": 0.2,
    "prudent_margin_partial_withdrawal": 0.25,
    "prudent_margin_expense": 0.10,
    "fund_return_margin": -0.005,
    "experience_mortality_pct": 0.8,
    "smoker_mortality_loading": 1.35,
    "surrender_share": 0.7,
    "initial_fixed_expense": 3000.0,
    "initial_percent_premium_expense": 0.15,
    "initial_percent_sa_expense": 0.001,
    "renewal_fixed_expense": 900.0,
    "claim_expense": 2500.0,
    "fund_expense_rate": 0.0015,
    "reserve_floor_days": 15.0,
    "revival_strain_dpf": 0.02,
    "revival_strain_rpu": 0.01,
    "reserve_capital_factor_no_guarantee": 0.006,
    "sar_capital_factor_no_guarantee": 0.0,
    "reserve_capital_factor_guarantee": 0.02,
    "sar_capital_factor_guarantee": 0.002,
    "target_capital_ratio": 1.5,
    "cost_of_capital_rate": 0.025,
    "mc_fund_return_source": 0.0,
}
TABLES = (
    "ul_funds",
    "ul_variants",
    "ul_regulatory_caps",
    "ul_charge_scales",
    "ul_disc_charge_caps",
    "ul_riy_caps",
    "ul_strategies",
    "mortality_charges_ul",
    "lapse_rates_ul",
    "partial_withdrawals_ul",
    "commissions_ul",
    "ul_asset_returns",
)
SEX_FIELDS = (("male", 1.0), ("female", 0.82), ("transgender", 0.91))


def variants() -> dict[str, dict[str, float]]:
    return {
        name: {
            **BASE_VARIANT,
            **fields,
            "topup_on": 0.0,
            "topup_sa_multiple": 0.0,
            "topup_lock_in_months": 0.0,
            "switch_charge": 0.0,
            "highest_nav_start_month": 0.0,
        }
        for name, fields in VARIANTS.items()
    }


def fund_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for code, fmc, price, alpha, guarantee, risk, mix in FUNDS:
        fields: dict[str, float] = {"unit_price": price, "fmc": fmc, "alpha": alpha}
        fields.update({f"w_{a}": mix.get(a, 0.0) for a in ASSET_CLASSES})
        fields.update(
            {
                "selectable": float(code != DPF_CODE),
                "is_dpf": float(code == DPF_CODE),
                "guarantee_type": float(guarantee),
                "risk_class": float(risk),
            }
        )
        rows.extend({"key": code, "field": f, "value": float(v)} for f, v in fields.items())
    return rows


def ul_basis(put: Put, mortality: list[dict[str, Any]]) -> None:
    """Write the unit-linked tables through `put` (name, rows, short format name)."""
    put("ul_funds", fund_rows(), "ul_keyed")
    put(
        "ul_strategies",
        [
            {"year": year, "key": 0, "field": rule.name, "value": 0.0}
            for year in (1, 2)
            for rule in STRATEGY_FIELDS
        ],
        "ul_year_key",
    )
    put(
        "ul_variants",
        [
            {"key": name, "field": f, "value": float(v)}
            for name, fields in variants().items()
            for f, v in fields.items()
        ],
        "ul_keyed",
    )
    put(
        "ul_regulatory_caps",
        [
            {"key": name, "field": f, "value": float(v)}
            for name, fields in REGIMES.items()
            for f, v in fields.items()
        ],
        "ul_keyed",
    )
    put(
        "ul_charge_scales",
        [
            {"year": y, "key": int(fields["variant_id"]), "field": f, "value": v}
            for y in range(1, YEARS + 1)
            for name, fields in VARIANTS.items()
            for f, v in scale(name, y).items()
        ],
        "ul_year_key",
    )
    fields = ("disc_pct_low", "disc_cap_low", "disc_pct_high", "disc_cap_high")
    put(
        "ul_disc_charge_caps",
        [
            {"year": y, "key": key, "field": f, "value": v}
            for y in range(1, YEARS + 1)
            for key, values in ((0, discontinuance(y)), (1, (1.0, 1e12, 1.0, 1e12)))
            for f, v in zip(fields, values, strict=True)
        ],
        "ul_year_key",
    )
    put(
        "ul_riy_caps",
        [
            {"year": y, "key": key, "field": "riy_max", "value": value}
            for y in range(1, YEARS + 1)
            for key, value in ((0, riy_max(y)), (1, 1.0))
        ],
        "ul_year_key",
    )
    rates = {(row["age"], row["field"]): row["value"] for row in mortality}
    put(
        "mortality_charges_ul",
        [
            {
                "age": age,
                "field": f"{sex}_{smoker}",
                "value": 1.75 * rates[(age, sex)] * 1000.0 * loading,
            }
            for age in sorted({row["age"] for row in mortality})
            for sex, _ in SEX_FIELDS
            for smoker, loading in (("non_smoker", 1.0), ("smoker", 1.35))
        ],
        "mortality",
    )
    put(
        "lapse_rates_ul",
        [
            {"year": y, "channel": c, "value": lapse_rate(y) * (1.2 if c else 1.0)}
            for y in range(1, YEARS + 1)
            for c in (0, 1)
        ],
        "lapse",
    )
    put(
        "partial_withdrawals_ul",
        [
            {"year": y, "channel": c, "value": 0.006 * (y >= 6)}
            for y in range(1, YEARS + 1)
            for c in (0, 1)
        ],
        "lapse",
    )
    put(
        "commissions_ul",
        [
            {"year": y, "channel": c, "value": commission_rate(y) * (0.8 if c else 1.0)}
            for y in range(1, YEARS + 1)
            for c in (0, 1)
        ],
        "commission",
    )
    put(
        "ul_asset_returns",
        [
            {"year": y, "field": a, "value": ASSET_RETURNS[a]}
            for y in range(1, YEARS + 1)
            for a in ASSET_CLASSES
        ],
        "curves",
    )


def parameter_rows() -> list[dict[str, Any]]:
    return [
        {"product": "UNIT_LINKED", "parameter": key, "value": value}
        for key, value in PARAMETERS.items()
    ]
