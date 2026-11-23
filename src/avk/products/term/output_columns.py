"""Public output labels and their product-column bindings."""

EXITS = (
    ("lives_so_begin", "lives_begin"),
    ("deaths", "deaths"),
    ("lapses", "lapses"),
    ("maturities", "maturities"),
    ("lives_so_end", "lives_end"),
)

CASHFLOWS = (
    "premiums",
    "commissions",
    "initial_expense",
    "renewal_expenses",
    "claim_expenses",
    "death_benefits",
    "interest_on_cashflows",
    "surrender_benefits",
    "net_cashflows",
    "discounted_net_cf",
    "gross_reserve_pp",
    "reins_sum_assured",
    "reins_premiums",
    "reins_recoveries",
    "net_cf_with_reinsurance",
    "discounted_cf_with_reins",
    "net_reserve_pp",
)

BE_LAYER = (
    ("be_premiums", "premiums"),
    ("be_commissions", "commissions"),
    ("be_initial_expense", "initial_expense"),
    ("be_renewal_expenses", "renewal_expenses"),
    ("be_claim_expenses", "claim_expenses"),
    ("be_death_benefits", "death_benefits"),
    ("be_surrender_benefits", "surrender_benefits"),
    ("be_reinsurance_premiums", "reins_premiums"),
    ("be_reinsurance_recoveries", "reins_recoveries"),
    ("be_interest_on_cashflows", "interest_on_cashflows"),
    *(
        (name, name)
        for name in (
            "be_net_cf",
            "be_reserves",
            "increase_in_reserves",
            "interest_on_reserves",
            "part1_sm",
            "part2_sm",
            "gross_sar",
            "net_sar",
            "required_solvency_capital",
            "increase_in_solvency_capital",
            "interest_on_solvency_capital",
            "profit_before_tax",
            "profit_transfer",
            "tax",
            "net_profit_before_sm",
            "cost_of_capital",
            "net_profit_after_sm",
        )
    ),
)

PRESENT_VALUES = (
    ("interest_on_cashflows", "mcev_interest_on_cashflows"),
    ("interest_on_reserve", "mcev_interest_on_reserve"),
    ("net_cf", "mcev_net_cf"),
    ("profit_before_tax", "mcev_profit_before_tax"),
    ("profit_transfer", "mcev_profit_transfer"),
    ("tax", "mcev_tax"),
    ("net_profit", "mcev_net_profit"),
    *(
        (name, name)
        for name in (
            "pvfp",
            "pv_premium",
            "interest_on_sm",
            "tax_interest_on_sm",
            "profit_transfer_interest_on_sm",
            "coc",
            "fcc",
            "bel",
            "bel_pp",
            "ifrs_bel",
            "ifrs_bel_pp",
            "ifrs_expense_capital",
        )
    ),
)
