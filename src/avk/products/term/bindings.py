"""Term binding names and strict parameter requirements."""

# Mortality columns in code order: a sex code is its column's position (validation.py).
SEX = ("Male", "Female", "Transgender")
INITIAL = ("SA", "% of Prem", "Fixed", "% of SA")
RENEWAL = ("Fixed expenses", "Claim expenses", "% of Prem")
# The IFRS 17 renewal schedules (curves of `common/ifrs_bel.py`) and their column of
# `ifrs17_renewal_expenses_term`, in `RENEWAL` order.
IFRS_SCHEDULES = {
    "ifrs17_renewal_fixed": "Fixed expenses",
    "ifrs17_renewal_claim": "Claim expenses",
    "ifrs17_renewal_premium": "% of Prem",
}
IFRS_PARAMETERS = {
    "ifrs17_multiplier_initial_expenses": "ifrs_initial_expense_multiplier",
    "ifrs17_multiplier_renewal_expenses": "IFRS17 Multiplier Renewal Expenses",
    "ifrs17_addition_renewal_expenses": "IFRS17 Addition Renewal Expenses",
    "ifrs17_ra_ratio": "IFRS 17 RA Ratio",
    "ifrs17_ri_ra_ratio": "IFRS 17 RI RA Ratio",
    "ifrs17_stress_inflation": "IFRS 17 stress inflation",
    "ifrs17_stress_expense": "IFRS 17 stress expense",
    "ifrs17_multiplier_initial_commission": "IFRS17 Multiplier Initial Commission",
}
