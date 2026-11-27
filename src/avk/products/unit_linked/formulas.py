"""Unit-linked insurance (UNIT_LINKED): the skeleton composition of phase P1.

The columns place each policy in time and report the opening funds. Every table, curve,
parameter and scenario variable the projection will read is declared on the product
class (as `Term.support`), so `avk check` validates all of them before projection; phase
P2a moves each binding into the component that reads it.
"""

from avk.model.lang import Component, Product, curve, int_axis, keymap, param, scen, table

# Formula modules import only the authoring API, so the model-point contract is spelled
# here; tests tie ASSETS, VARIANT_FEATURES and SLOTS to `bindings` and `features`.
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
VARIANT_FEATURES = (
    "single_premium",
    "death_benefit_type",
    "min_db_premium_multiple",
    "lock_in_months",
    "dpf_enabled",
    "rpu_mode",
    "revival_period_months",
    "pw_allowed",
    "pw_start_year",
    "pw_reduces_sa",
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
REGIME_FIELDS = ("dpf_min_rate", "dpf_fmc_max", "caps_apply")
SLOTS = 5
SLOT_FIELDS = (
    "Present",
    "Fund_Index",
    "Allocation",
    "Value",
    "FMC",
    "Alpha",
    *(f"W_{a}" for a in ASSETS),
    "Premiums_Allocated",
    "Guaranteed_Price",
)
POLICY_FIELDS = (
    "Variant_Id",
    "Regime_Id",
    "Duration_in_Months",
    "Age_at_Entry",
    "Gender_Code",
    "Smoker_Code",
    "Charge_Column",
    "Distribution_Channel",
    "Policy_Term",
    "Premium_Payment_Term",
    "Premium_Frequency",
    "Annualised_Premium",
    "Instalment_Premium",
    "Instalments_Payable",
    "Sum_Assured",
    "EMR",
    "Flat_Extra",
    "Flat_Extra_Term_Months",
    "Policy_Status",
    "Paid_Up_Sum_Assured",
    "Premiums_Paid_To_Date",
    "Instalments_Paid",
    "PAC_To_Date",
    "Admin_To_Date",
    "MC_To_Date",
    "GC_To_Date",
    "Loyalty_To_Date",
    "PW_To_Date",
    "PW_Current_Year",
    "PW_Previous_Year",
    "FV_Sum_Current_Year",
    "Disc_Charge_Paid",
)
FIELDS = (
    *POLICY_FIELDS,
    *(f"V_{name}" for name in VARIANT_FEATURES),
    *(f"R_{name}" for name in REGIME_FIELDS),
    "DPF_Value",
    "DPF_FMC",
    "DPF_Alpha",
    *(f"DPF_W_{a}" for a in ASSETS),
    *(f"Fund_{k}_{name}" for k in range(1, SLOTS + 1) for name in SLOT_FIELDS),
)


def year_table(name: str, key: str) -> object:
    return table(
        name,
        axes=(
            int_axis("policy_year", below="clamp", above="clamp"),
            keymap(key, unknown="error", above="error"),
        ),
    )


def channel_table(name: str) -> object:
    return table(
        name,
        value="rate",
        axes=(
            int_axis("policy_year", below="clamp", above="clamp"),
            keymap("Distribution_Channel", unknown="error", above="error"),
        ),
    )


class PolicyTime(Component):
    """Policy month, policy year and attained age."""

    def policy_month(self, t):
        """Months since the policy started: those already elapsed plus the projection month."""
        return self.policy.Duration_in_Months + t

    def policy_year(self, t):
        """Policy year, from 1."""
        return (self.policy_month(t) - 1) // 12 + 1

    def age(self, t):
        """Age: entry age plus completed policy years."""
        return self.policy.Age_at_Entry + (self.policy_month(t) - 1) // 12


class OpeningFunds(Component):
    """The funds held at the valuation date (projection step 0 only)."""

    def opening_unit_fund(self, t):
        """The value of the policy's fund slots at the valuation instant (units times unit
        price, outside the DPF)."""
        return (
            self.policy.Fund_1_Value
            + self.policy.Fund_2_Value
            + self.policy.Fund_3_Value
            + self.policy.Fund_4_Value
            + self.policy.Fund_5_Value
        ) * (t == 0)

    def opening_dpf_fund(self, t):
        """The value held in the Discontinued Policy Fund at the valuation instant."""
        return self.policy.DPF_Value * (t == 0)


class UnitLinked(PolicyTime, OpeningFunds, Product):
    CODE, LABEL, BASES = "UNIT_LINKED", "Unit-linked insurance", ("reserving", "be", "mc")
    FIELDS = FIELDS

    # Declared for phase P2 formulas; validated by `avk check` meanwhile.
    funds = table("ul_funds", axes=())
    variants = table("ul_variants", axes=())
    regulatory_caps = table("ul_regulatory_caps", axes=())
    premium_allocation_rate = year_table("ul_charge_scales/premium_allocation_rate", "Variant_Id")
    admin_charge_monthly = year_table("ul_charge_scales/admin_charge_monthly", "Variant_Id")
    loyalty_rate = year_table("ul_charge_scales/loyalty_rate", "Variant_Id")
    booster_rate = year_table("ul_charge_scales/booster_rate", "Variant_Id")
    disc_pct_low = year_table("ul_charge_scales/disc_pct_low", "Variant_Id")
    disc_cap_low = year_table("ul_charge_scales/disc_cap_low", "Variant_Id")
    disc_pct_high = year_table("ul_charge_scales/disc_pct_high", "Variant_Id")
    disc_cap_high = year_table("ul_charge_scales/disc_cap_high", "Variant_Id")
    cap_disc_pct_low = year_table("ul_disc_charge_caps/disc_pct_low", "Regime_Id")
    cap_disc_cap_low = year_table("ul_disc_charge_caps/disc_cap_low", "Regime_Id")
    cap_disc_pct_high = year_table("ul_disc_charge_caps/disc_pct_high", "Regime_Id")
    cap_disc_cap_high = year_table("ul_disc_charge_caps/disc_cap_high", "Regime_Id")
    riy_max = year_table("ul_riy_caps", "Regime_Id")
    mortality = table(
        "mortality",
        axes=(
            int_axis("age", below="error", above="clamp"),
            keymap("Gender_Code", unknown="error", above="error"),
        ),
    )
    mortality_charges = table(
        "mortality_charges_ul",
        axes=(
            int_axis("age", below="error", above="clamp"),
            keymap("Charge_Column", unknown="error", above="error"),
        ),
    )
    discontinuance = channel_table("lapse_rates_ul")
    partial_withdrawals = channel_table("partial_withdrawals_ul")
    commission = channel_table("commissions_ul")
    interest_curve = curve("interest_rates")
    asset_returns = curve("ul_asset_returns")
    roi = scen("roi")
    vroi = scen("vroi")
    reference_forward = scen("reference_forward")
    ret_eq_large = scen("ret_eq_large")
    ret_eq_mid = scen("ret_eq_mid")
    ret_eq_small = scen("ret_eq_small")
    ret_eq_global = scen("ret_eq_global")
    ret_gov_long = scen("ret_gov_long")
    ret_gov_short = scen("ret_gov_short")
    ret_corp_bond = scen("ret_corp_bond")
    ret_money_market = scen("ret_money_market")
    ret_gold = scen("ret_gold")
    ret_real_assets = scen("ret_real_assets")
    inflation = param("Inflation")
    tax_rate = param("Tax Rate")
    profit_transfer_rate = param("profit_transfer_rate")
    prudent_margin_mortality = param("prudent_margin_mortality")
    prudent_margin_lapse = param("prudent_margin_lapse")
    prudent_margin_partial_withdrawal = param("prudent_margin_partial_withdrawal")
    prudent_margin_expense = param("prudent_margin_expense")
    fund_return_margin = param("fund_return_margin")
    experience_mortality_pct = param("experience_mortality_pct")
    smoker_mortality_loading = param("smoker_mortality_loading")
    surrender_share = param("surrender_share")
    initial_fixed_expense = param("initial_fixed_expense")
    initial_percent_premium_expense = param("initial_percent_premium_expense")
    initial_percent_sa_expense = param("initial_percent_sa_expense")
    renewal_fixed_expense = param("renewal_fixed_expense")
    claim_expense = param("claim_expense")
    fund_expense_rate = param("fund_expense_rate")
    reserve_floor_days = param("reserve_floor_days")
    revival_strain_dpf = param("revival_strain_dpf")
    revival_strain_rpu = param("revival_strain_rpu")
    reserve_capital_factor_no_guarantee = param("reserve_capital_factor_no_guarantee")
    sar_capital_factor_no_guarantee = param("sar_capital_factor_no_guarantee")
    reserve_capital_factor_guarantee = param("reserve_capital_factor_guarantee")
    sar_capital_factor_guarantee = param("sar_capital_factor_guarantee")
    target_capital_ratio = param("target_capital_ratio")
    cost_of_capital_rate = param("cost_of_capital_rate")
    mc_fund_return_source = param("mc_fund_return_source")
