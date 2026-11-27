"""Unit-linked constants: asset classes, fund slots, status codes and table names."""

CODE = "UNIT_LINKED"

# Asset classes of the fund universe; each has one scenario variable of monthly returns.
ASSET_CLASSES = (
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
SCENARIO_ASSETS = tuple(f"ret_{a}" for a in ASSET_CLASSES)  # scenario variable names

# Funds a policy may hold outside the Discontinued Policy Fund (generated fund slots).
MAX_FUND_SLOTS = 5

# Policy Status codes.
STATUS_ACTIVE, STATUS_DPF, STATUS_RPU = 0, 1, 2

POLICY_TABLE, HOLDINGS_TABLE = "policies_ul", "policy_funds_ul"

# Logical assumption tables.
FUNDS_TABLE = "ul_funds"
VARIANTS_TABLE = "ul_variants"
CAPS_TABLE = "ul_regulatory_caps"
SCALES_TABLE = "ul_charge_scales"
DISC_CAPS_TABLE = "ul_disc_charge_caps"
RIY_CAPS_TABLE = "ul_riy_caps"
MORTALITY_CHARGES_TABLE = "mortality_charges_ul"
LAPSE_TABLE = "lapse_rates_ul"
WITHDRAWALS_TABLE = "partial_withdrawals_ul"
COMMISSIONS_TABLE = "commissions_ul"
ASSET_RETURNS_TABLE = "ul_asset_returns"

# Fields of `mortality_charges_ul`, in the order of `Charge_Column` (2 x gender + smoker).
CHARGE_COLUMNS = (
    "male_non_smoker",
    "male_smoker",
    "female_non_smoker",
    "female_smoker",
    "transgender_non_smoker",
    "transgender_smoker",
)
GENDER_CODES = {"M": 0, "F": 1, "T": 2}
SMOKER_CODES = {"NS": 0, "S": 1}
PREMIUM_FREQUENCIES = (0, 1, 2, 4, 12)

# Product parameters (column UNIT_LINKED of `product_parameters`).
PARAMETERS = (
    "Inflation",
    "Tax Rate",
    "profit_transfer_rate",
    "prudent_margin_mortality",
    "prudent_margin_lapse",
    "prudent_margin_partial_withdrawal",
    "prudent_margin_expense",
    "fund_return_margin",
    "experience_mortality_pct",
    "smoker_mortality_loading",
    "surrender_share",
    "initial_fixed_expense",
    "initial_percent_premium_expense",
    "initial_percent_sa_expense",
    "renewal_fixed_expense",
    "claim_expense",
    "fund_expense_rate",
    "reserve_floor_days",
    "revival_strain_dpf",
    "revival_strain_rpu",
    "reserve_capital_factor_no_guarantee",
    "sar_capital_factor_no_guarantee",
    "reserve_capital_factor_guarantee",
    "sar_capital_factor_guarantee",
    "target_capital_ratio",
    "cost_of_capital_rate",
    "mc_fund_return_source",
)
