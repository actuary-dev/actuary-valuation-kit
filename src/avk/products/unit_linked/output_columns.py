"""Public valuation labels and the product columns they read.

Aggregate entries are `decrements_<name>_<layer>` on every basis, `cashflows_<name>_<layer>`
on the reserving and best-estimate bases (the best-estimate layer adds the profit chain, the
segment split and capital) and `MCEV_<name>_MC` on the market-consistent basis.
"""

LAYERS = {"reserving": "reserving", "be": "BE", "mc": "MC"}

HIGHEST_NAV = ("benefits_non_unit_highest_nav", "highest_nav_cost")

DECREMENTS = (
    ("lives_active_begin", "A_begin"),
    ("lives_dpf_begin", "D_begin"),
    ("lives_paid_up_begin", "R_begin"),
    ("lives_active_end", "A_end"),
    ("lives_dpf_end", "D_end"),
    ("lives_paid_up_end", "R_end"),
    ("lives_total_end", "lives_end"),
    ("deaths_active", "deaths_A"),
    ("deaths_dpf", "deaths_D"),
    ("deaths_paid_up", "deaths_R"),
    ("surrenders_active", "surrenders_A"),
    ("cessations_active", "cessations_A"),
    ("exits_active_paid", "paid_out_A"),
    ("transfers_to_dpf", "to_dpf"),
    ("transfers_to_paid_up", "to_rpu"),
    ("exits_dpf_lock_in", "lockin_exits_D"),
    ("surrenders_paid_up", "surrenders_R"),
    ("expiries_paid_up", "expiries_R"),
    ("maturities_active", "maturities_A"),
    ("maturities_paid_up", "maturities_R"),
    ("maturities", "maturities"),
)

CASHFLOWS = (
    ("premiums", "premium_income"),
    ("premiums_allocated", "allocated_premiums"),
    ("charges_allocation", "pac_income"),
    ("charges_administration", "admin_income"),
    ("charges_mortality", "mc_income"),
    ("charges_guarantee", "gc_income"),
    ("charges_fmc_active", "fmc_income_A"),
    ("charges_fmc_paid_up", "rpu_fmc_total"),
    ("charges_fmc_dpf", "dpf_fmc"),
    ("charges_discontinuance", "disc_charge_income"),
    ("charges_start_of_month", "charges_start"),
    ("charges_end_of_month", "charges_end"),
    ("charges_total", "charge_income"),
    ("funds_active", "unit_reserve_A"),
    ("funds_dpf", "dpf_close"),
    ("funds_paid_up", "rpu_close_total"),
    ("unit_reserve", "unit_reserve"),
    ("benefits_unit_active_death", "death_unit_A"),
    ("benefits_unit_active_discontinuance", "surrender_unit_A"),
    ("benefits_unit_active_maturity", "maturity_unit_A"),
    ("benefits_unit_dpf_death", "dpf_death_paid"),
    ("benefits_unit_dpf_release", "dpf_lockin_paid"),
    ("benefits_unit_paid_up_death", "death_unit_R"),
    ("benefits_unit_paid_up_surrender", "surrender_unit_R"),
    ("benefits_unit_paid_up_expiry", "expiry_unit_R"),
    ("benefits_unit_paid_up_maturity", "maturity_unit_R"),
    ("benefits_unit_withdrawals", "partial_withdrawal_outgo"),
    ("benefits_unit_total", "unit_benefit_outgo"),
    ("benefits_non_unit_active_death", "death_non_unit_A"),
    ("benefits_non_unit_paid_up_death", "death_non_unit_R"),
    ("benefits_non_unit_return_of_charges", "return_of_charges"),
    ("benefits_non_unit_active_maturity_top_up", "maturity_guarantee_A"),
    ("benefits_non_unit_paid_up_maturity_top_up", "maturity_guarantee_R"),
    ("benefits_non_unit_additions", "addition_outgo"),
    ("benefits_non_unit_dpf_guarantee", "dpf_guarantee_cost"),
    ("benefits_non_unit_total", "non_unit_benefit_outgo"),
    ("residual_additions", "residual_additions"),
    ("commissions", "commissions"),
    ("initial_expense", "initial_expense"),
    ("renewal_expenses", "renewal_expenses"),
    ("fund_expenses", "fund_expenses"),
    ("claim_expenses", "claim_expenses"),
    ("interest_on_cashflows", "interest_on_cashflows"),
    ("net_cashflows", "net_cashflows"),
    ("gf_reserve_dcf", "gf_reserve_dcf"),
    ("gf_reserve_floor", "gf_reserve_floor"),
    ("gf_reserve_held", "gf_reserve_held"),
    ("revival_provision", "revival_provision"),
    ("non_unit_reserve", "non_unit_reserve"),
    ("total_reserve", "total_reserve"),
    ("gf_reserve_pp", "gf_reserve_pp"),
    ("non_unit_reserve_pp", "non_unit_reserve_pp"),
    ("total_reserve_pp", "total_reserve_pp"),
    ("sum_at_risk", "sum_at_risk"),
)

BE_ONLY = tuple(
    (name, name)
    for name in (
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
        "unit_segment_profit",
        "non_unit_segment_profit",
        "total_profit",
        "part1_sm",
        "part2_sm",
        "required_solvency_capital",
        "increase_in_solvency_capital",
        "interest_on_solvency_capital",
    )
)

MCEV = (
    ("net_cf", "mc_net_cf"),
    ("reserves", "mc_reserves"),
    ("increase_in_reserves", "mc_increase_in_reserves"),
    ("interest_on_reserve", "mcev_interest_on_reserve"),
    ("profit_before_tax", "mcev_profit_before_tax"),
    ("profit_transfer", "mcev_profit_transfer"),
    ("tax", "mcev_tax"),
    ("net_profit", "mcev_net_profit"),
    ("required_solvency_capital", "required_solvency_capital"),
    ("interest_on_sm", "interest_on_sm_mc"),
    ("frictional_cost", "frictional_cost"),
    ("crnhr_charge", "crnhr_charge"),
    *(
        (name, name)
        for name in ("pvfp", "pv_premium", "fcc", "crnhr", "vif", "gf_bel", "bel", "bel_pp")
    ),
)

# Step-0 values per policy: (output, column, basis).
SERIATIM = (
    ("cashflows_unit_reserve_reserving", "unit_reserve", "reserving"),
    ("cashflows_gf_reserve_held_reserving", "gf_reserve_held", "reserving"),
    ("cashflows_total_reserve_reserving", "total_reserve", "reserving"),
    ("MCEV_bel_MC", "bel", "mc"),
    ("MCEV_pvfp_MC", "pvfp", "mc"),
    ("MCEV_vif_MC", "vif", "mc"),
    ("cashflows_sum_at_risk_BE", "sum_at_risk", "be"),
    ("Annualised_premium", "annualised_premium", None),
)

# Per-policy outputs aggregated as held amount / eligible lives on their basis.
RATIOS = {
    "gf_reserve_pp": ("gf_reserve_held", 1.0),
    "non_unit_reserve_pp": ("non_unit_reserve", 1.0),
    "total_reserve_pp": ("total_reserve", 1.0),
    "bel_pp": ("bel", 1.0),
}
