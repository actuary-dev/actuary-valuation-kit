"""Unit-linked insurance: composition and model-point contract."""

from avk.model.lang import Component, UnitLinkedProduct, curve, param, scen, table
from avk.products.unit_linked.benefits import UnitSegment
from avk.products.unit_linked.decrements import UnitLinkedDecrements, channel_table, year_table
from avk.products.unit_linked.dpf import DiscontinuedFund
from avk.products.unit_linked.fund_slots import SLOTS, FundSlots
from avk.products.unit_linked.lives import UnitLinkedLives
from avk.products.unit_linked.paid_up import PaidUpCashflows
from avk.products.unit_linked.premiums import ActiveCashflows

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
    "topup_on",
    "topup_sa_multiple",
    "topup_lock_in_months",
    "switch_charge",
    "highest_nav_start_month",
)
REGIME_FIELDS = ("dpf_min_rate", "dpf_fmc_max", "caps_apply")
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
    "Topup_Value",
    "Selectable",
    "Unit_Price",
    "Guarantee_Type",
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
    "Single_Top_Up_Premium",
    "Single_Top_Up_Policy_Month",
    "Regular_Top_Up_Premium",
    "Top_Up_Premiums_Paid_To_Date",
    "Last_Top_Up_Policy_Month",
    "Strategy_Id",
    "Strategy_Mode",
    "Strategy_Source_Slot",
    "Strategy_Amount",
    *(f"Strategy_Target_{k}" for k in range(1, SLOTS + 1)),
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

    def opening_dpf_fund(self, t):
        """The value held in the Discontinued Policy Fund at the valuation instant."""
        return self.policy.DPF_Value * (t == 0)


class UnitLinked(
    PolicyTime,
    OpeningFunds,
    UnitLinkedDecrements,
    UnitLinkedLives,
    ActiveCashflows,
    FundSlots,
    DiscontinuedFund,
    PaidUpCashflows,
    UnitSegment,
    UnitLinkedProduct,
):
    CODE, LABEL, BASES = "UNIT_LINKED", "Unit-linked insurance", ("reserving", "be", "mc")
    FIELDS = FIELDS

    # Tables used in preparation and bindings for later phases.
    funds = table("ul_funds", axes=())
    variants = table("ul_variants", axes=())
    regulatory_caps = table("ul_regulatory_caps", axes=())
    cap_disc_pct_low = year_table("ul_disc_charge_caps/disc_pct_low", "Regime_Id")
    cap_disc_cap_low = year_table("ul_disc_charge_caps/disc_cap_low", "Regime_Id")
    cap_disc_pct_high = year_table("ul_disc_charge_caps/disc_pct_high", "Regime_Id")
    cap_disc_cap_high = year_table("ul_disc_charge_caps/disc_cap_high", "Regime_Id")
    riy_max = year_table("ul_riy_caps", "Regime_Id")
    commission = channel_table("commissions_ul")
    interest_curve = curve("interest_rates")
    asset_returns = curve("ul_asset_returns")
    roi = scen("roi")
    vroi = scen("vroi")
    inflation = param("Inflation")
    tax_rate = param("Tax Rate")
    profit_transfer_rate = param("profit_transfer_rate")
    prudent_margin_expense = param("prudent_margin_expense")
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
