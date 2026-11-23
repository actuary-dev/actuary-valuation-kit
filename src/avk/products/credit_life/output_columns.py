"""Public output labels and their product-column bindings."""

from avk.products.term.output_columns import EXITS as EXITS

CASHFLOWS = (
    *(
        (name, name)
        for name in (
            "premiums",
            "commissions",
            "initial_expense",
            "renewal_expenses",
            "claim_expenses",
            "death_benefits",
            "surrender_benefits",
            "interest_on_cashflows",
            "net_cashflows",
            "sv",
        )
    ),
    ("discounted_cf_reserving", "discounted_net_cf"),
    ("gross_reserve_pp", "gross_reserve_pp"),
    *(
        (name, name)
        for name in (
            "reins_sum_assured",
            "reins_premiums",
            "reins_recoveries",
            "net_cf_with_reinsurance",
            "discounted_cf_with_reins",
            "net_reserve_pp",
        )
    ),
)
