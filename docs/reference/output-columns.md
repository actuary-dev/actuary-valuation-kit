# Output columns

Generated from product output schemas and the approved public reporting schemas.
Do not edit. Amount columns are in the input currency; rates are fractions.
See [output conventions](../output-conventions.md) before summing or taking ratios.
A source identifies the formula column; basis selects its evaluation assumptions.
Keys identify rows. Aggregates sum amounts; book ratios are documented below.
Seriatim is one selected-step row per policy; policy-month exports use the keys.

## ACCIDENTAL_DEATH_RIDER

| Output | Source | Basis | Role / step |
|---|---|---|---|
| `Policy_Number` | `<policy number>` | - | key |
| `Policy_Month` | `policy_month` | - | key |
| `Calendar_Month` | `<calendar month>` | - | key |
| `Projection_Step` | `<projection step>` | - | key |
| `Modal_Factor` | `modal_factor` | - | key |
| `decrements_adb_reserving` | `rider_event` | reserving | aggregate / policy-month |
| `decrements_deaths_reserving` | `deaths` | reserving | aggregate / policy-month |
| `decrements_lapses_reserving` | `lapses` | reserving | aggregate / policy-month |
| `decrements_lives_so_begin_reserving` | `lives_begin` | reserving | aggregate / policy-month |
| `decrements_lives_so_end_reserving` | `lives_end` | reserving | aggregate / policy-month |
| `decrements_maturities_reserving` | `maturities` | reserving | aggregate / policy-month |
| `cashflows_adb_benefit_reserving` | `adb_benefit` | reserving | aggregate / policy-month |
| `cashflows_claim_expenses_reserving` | `claim_expenses` | reserving | aggregate / policy-month |
| `cashflows_commissions_reserving` | `commissions` | reserving | aggregate / policy-month |
| `cashflows_discounted_cf_reserving_reserving` | `discounted_net_cf` | reserving | aggregate / policy-month |
| `cashflows_discounted_cf_with_reins_reserving` | `discounted_cf_with_reins` | reserving | aggregate / policy-month |
| `cashflows_gross_reserve_pp_reserving` | `gross_reserve_pp` | reserving | aggregate / policy-month |
| `cashflows_initial_expense_reserving` | `initial_expense` | reserving | aggregate / policy-month |
| `cashflows_interest_on_cashflows_reserving` | `interest_on_cashflows` | reserving | aggregate / policy-month |
| `cashflows_net_cashflows_reserving` | `net_cashflows` | reserving | aggregate / policy-month |
| `cashflows_net_cf_with_reinsurance_reserving` | `net_cf_with_reinsurance` | reserving | aggregate / policy-month |
| `cashflows_net_reserve_pp_reserving` | `net_reserve_pp` | reserving | aggregate / policy-month |
| `cashflows_premiums_reserving` | `premiums` | reserving | aggregate / policy-month |
| `cashflows_reins_premiums_reserving` | `reins_premiums` | reserving | aggregate / policy-month |
| `cashflows_reins_recoveries_reserving` | `reins_recoveries` | reserving | aggregate / policy-month |
| `cashflows_reins_sum_assured_reserving` | `reins_sum_assured` | reserving | aggregate / policy-month |
| `cashflows_renewal_expenses_reserving` | `renewal_expenses` | reserving | aggregate / policy-month |
| `cashflows_surrender_benefits_reserving` | `surrender_benefits` | reserving | aggregate / policy-month |
| `cashflows_upr_reserving` | `upr` | reserving | aggregate / policy-month |
| `decrements_adb_BE` | `rider_event` | be | aggregate / policy-month |
| `decrements_deaths_BE` | `deaths` | be | aggregate / policy-month |
| `decrements_lapses_BE` | `lapses` | be | aggregate / policy-month |
| `decrements_lives_so_begin_BE` | `lives_begin` | be | aggregate / policy-month |
| `decrements_lives_so_end_BE` | `lives_end` | be | aggregate / policy-month |
| `decrements_maturities_BE` | `maturities` | be | aggregate / policy-month |
| `cashflows_be_adb_benefit_BE` | `adb_benefit` | be | aggregate / policy-month |
| `cashflows_be_claim_expenses_BE` | `claim_expenses` | be | aggregate / policy-month |
| `cashflows_be_commissions_BE` | `commissions` | be | aggregate / policy-month |
| `cashflows_be_initial_expense_BE` | `initial_expense` | be | aggregate / policy-month |
| `cashflows_be_interest_on_cashflows_BE` | `interest_on_cashflows` | be | aggregate / policy-month |
| `cashflows_be_net_cf_BE` | `be_net_cf` | be | aggregate / policy-month |
| `cashflows_be_premiums_BE` | `premiums` | be | aggregate / policy-month |
| `cashflows_be_reinsurance_premiums_BE` | `reins_premiums` | be | aggregate / policy-month |
| `cashflows_be_reinsurance_recoveries_BE` | `reins_recoveries` | be | aggregate / policy-month |
| `cashflows_be_renewal_expenses_BE` | `renewal_expenses` | be | aggregate / policy-month |
| `cashflows_be_reserves_BE` | `be_reserves` | be | aggregate / policy-month |
| `cashflows_be_surrender_benefits_BE` | `surrender_benefits` | be | aggregate / policy-month |
| `cashflows_cost_of_capital_BE` | `cost_of_capital` | be | aggregate / policy-month |
| `cashflows_gross_sar_BE` | `gross_sar` | be | aggregate / policy-month |
| `cashflows_increase_in_reserves_BE` | `increase_in_reserves` | be | aggregate / policy-month |
| `cashflows_increase_in_solvency_capital_BE` | `increase_in_solvency_capital` | be | aggregate / policy-month |
| `cashflows_interest_on_reserves_BE` | `interest_on_reserves` | be | aggregate / policy-month |
| `cashflows_interest_on_solvency_capital_BE` | `interest_on_solvency_capital` | be | aggregate / policy-month |
| `cashflows_net_cf_with_reinsurance_BE` | `net_cf_with_reinsurance` | be | aggregate / policy-month |
| `cashflows_net_profit_after_sm_BE` | `net_profit_after_sm` | be | aggregate / policy-month |
| `cashflows_net_profit_before_sm_BE` | `net_profit_before_sm` | be | aggregate / policy-month |
| `cashflows_net_sar_BE` | `net_sar` | be | aggregate / policy-month |
| `cashflows_profit_before_tax_BE` | `profit_before_tax` | be | aggregate / policy-month |
| `cashflows_profit_transfer_BE` | `profit_transfer` | be | aggregate / policy-month |
| `cashflows_reins_premiums_BE` | `reins_premiums` | be | aggregate / policy-month |
| `cashflows_reins_recoveries_BE` | `reins_recoveries` | be | aggregate / policy-month |
| `cashflows_reins_sum_assured_BE` | `reins_sum_assured` | be | aggregate / policy-month |
| `cashflows_required_solvency_capital_BE` | `required_solvency_capital` | be | aggregate / policy-month |
| `cashflows_tax_BE` | `tax` | be | aggregate / policy-month |
| `MCEV_bel_BE` | `bel` | be | aggregate / policy-month |
| `MCEV_bel_pp_BE` | `bel_pp` | be | aggregate / policy-month |
| `MCEV_coc_BE` | `coc` | be | aggregate / policy-month |
| `MCEV_fcc_BE` | `fcc` | be | aggregate / policy-month |
| `MCEV_ifrs_bel_BE` | `ifrs_bel` | be | aggregate / policy-month |
| `MCEV_ifrs_bel_pp_BE` | `ifrs_bel_pp` | be | aggregate / policy-month |
| `MCEV_ifrs_expense_capital_BE` | `ifrs_expense_capital` | be | aggregate / policy-month |
| `MCEV_interest_on_cashflows_BE` | `mcev_interest_on_cashflows` | be | aggregate / policy-month |
| `MCEV_interest_on_reserve_BE` | `mcev_interest_on_reserve` | be | aggregate / policy-month |
| `MCEV_interest_on_sm_BE` | `interest_on_sm` | be | aggregate / policy-month |
| `MCEV_net_cf_BE` | `mcev_net_cf` | be | aggregate / policy-month |
| `MCEV_net_profit_BE` | `mcev_net_profit` | be | aggregate / policy-month |
| `MCEV_profit_before_tax_BE` | `mcev_profit_before_tax` | be | aggregate / policy-month |
| `MCEV_profit_transfer_BE` | `mcev_profit_transfer` | be | aggregate / policy-month |
| `MCEV_profit_transfer_interest_on_sm_BE` | `profit_transfer_interest_on_sm` | be | aggregate / policy-month |
| `MCEV_pv_premium_BE` | `pv_premium` | be | aggregate / policy-month |
| `MCEV_pvfp_BE` | `pvfp` | be | aggregate / policy-month |
| `MCEV_tax_BE` | `mcev_tax` | be | aggregate / policy-month |
| `MCEV_tax_interest_on_sm_BE` | `tax_interest_on_sm` | be | aggregate / policy-month |
| `MCEV_pvfp_BE` | `pvfp` | be | seriatim step 0 |
| `MCEV_pv_premium_BE` | `pv_premium` | be | seriatim step 0 |
| `MCEV_bel_BE` | `bel` | be | seriatim step 0 |
| `MCEV_fcc_BE` | `fcc` | be | seriatim step 0 |
| `cashflows_gross_reserve_pp_reserving` | `gross_reserve_pp` | reserving | seriatim step 0 |
| `cashflows_net_reserve_pp_reserving` | `net_reserve_pp` | reserving | seriatim step 0 |
| `Annualised_premium` | `annualised_premium` | - | seriatim step 1 |

Book ratio columns (held numerator / eligible lives; sign shown):

| Output | Numerator | Denominator | Basis | Sign |
|---|---|---|---|---|
| `cashflows_gross_reserve_pp_reserving` | `gross_reserve_amount` | `eligible_reserve_lives` | reserving | 1 |
| `cashflows_net_reserve_pp_reserving` | `net_reserve_amount` | `eligible_reserve_lives` | reserving | 1 |
| `MCEV_bel_pp_BE` | `bel` | `eligible_reserve_lives` | be | -1 |
| `MCEV_ifrs_bel_pp_BE` | `ifrs_bel` | `eligible_reserve_lives` | be | 1 |

## CREDIT_LIFE

| Output | Source | Basis | Role / step |
|---|---|---|---|
| `Policy_Number` | `<policy number>` | - | key |
| `Policy_Month` | `policy_month` | - | key |
| `Calendar_Month` | `<calendar month>` | - | key |
| `Projection_Step` | `<projection step>` | - | key |
| `Modal_Factor` | `modal_factor` | - | key |
| `decrements_deaths_reserving` | `deaths` | reserving | aggregate / policy-month |
| `decrements_lapses_reserving` | `lapses` | reserving | aggregate / policy-month |
| `decrements_lives_so_begin_reserving` | `lives_begin` | reserving | aggregate / policy-month |
| `decrements_lives_so_end_reserving` | `lives_end` | reserving | aggregate / policy-month |
| `decrements_maturities_reserving` | `maturities` | reserving | aggregate / policy-month |
| `cashflows_claim_expenses_reserving` | `claim_expenses` | reserving | aggregate / policy-month |
| `cashflows_commissions_reserving` | `commissions` | reserving | aggregate / policy-month |
| `cashflows_death_benefits_reserving` | `death_benefits` | reserving | aggregate / policy-month |
| `cashflows_discounted_cf_reserving_reserving` | `discounted_net_cf` | reserving | aggregate / policy-month |
| `cashflows_discounted_cf_with_reins_reserving` | `discounted_cf_with_reins` | reserving | aggregate / policy-month |
| `cashflows_gross_reserve_pp_reserving` | `gross_reserve_pp` | reserving | aggregate / policy-month |
| `cashflows_initial_expense_reserving` | `initial_expense` | reserving | aggregate / policy-month |
| `cashflows_interest_on_cashflows_reserving` | `interest_on_cashflows` | reserving | aggregate / policy-month |
| `cashflows_net_cashflows_reserving` | `net_cashflows` | reserving | aggregate / policy-month |
| `cashflows_net_cf_with_reinsurance_reserving` | `net_cf_with_reinsurance` | reserving | aggregate / policy-month |
| `cashflows_net_reserve_pp_reserving` | `net_reserve_pp` | reserving | aggregate / policy-month |
| `cashflows_premiums_reserving` | `premiums` | reserving | aggregate / policy-month |
| `cashflows_reins_premiums_reserving` | `reins_premiums` | reserving | aggregate / policy-month |
| `cashflows_reins_recoveries_reserving` | `reins_recoveries` | reserving | aggregate / policy-month |
| `cashflows_reins_sum_assured_reserving` | `reins_sum_assured` | reserving | aggregate / policy-month |
| `cashflows_renewal_expenses_reserving` | `renewal_expenses` | reserving | aggregate / policy-month |
| `cashflows_surrender_benefits_reserving` | `surrender_benefits` | reserving | aggregate / policy-month |
| `cashflows_sv_reserving` | `sv` | reserving | aggregate / policy-month |
| `decrements_deaths_BE` | `deaths` | be | aggregate / policy-month |
| `decrements_lapses_BE` | `lapses` | be | aggregate / policy-month |
| `decrements_lives_so_begin_BE` | `lives_begin` | be | aggregate / policy-month |
| `decrements_lives_so_end_BE` | `lives_end` | be | aggregate / policy-month |
| `decrements_maturities_BE` | `maturities` | be | aggregate / policy-month |
| `cashflows_be_claim_expenses_BE` | `claim_expenses` | be | aggregate / policy-month |
| `cashflows_be_commissions_BE` | `commissions` | be | aggregate / policy-month |
| `cashflows_be_death_benefits_BE` | `death_benefits` | be | aggregate / policy-month |
| `cashflows_be_initial_expense_BE` | `initial_expense` | be | aggregate / policy-month |
| `cashflows_be_interest_on_cashflows_BE` | `interest_on_cashflows` | be | aggregate / policy-month |
| `cashflows_be_net_cf_BE` | `be_net_cf` | be | aggregate / policy-month |
| `cashflows_be_premiums_BE` | `premiums` | be | aggregate / policy-month |
| `cashflows_be_reinsurance_premiums_BE` | `reins_premiums` | be | aggregate / policy-month |
| `cashflows_be_reinsurance_recoveries_BE` | `reins_recoveries` | be | aggregate / policy-month |
| `cashflows_be_renewal_expenses_BE` | `renewal_expenses` | be | aggregate / policy-month |
| `cashflows_be_reserves_BE` | `be_reserves` | be | aggregate / policy-month |
| `cashflows_be_surrender_benefits_BE` | `surrender_benefits` | be | aggregate / policy-month |
| `cashflows_cost_of_capital_BE` | `cost_of_capital` | be | aggregate / policy-month |
| `cashflows_gross_sar_BE` | `gross_sar` | be | aggregate / policy-month |
| `cashflows_increase_in_reserves_BE` | `increase_in_reserves` | be | aggregate / policy-month |
| `cashflows_increase_in_solvency_capital_BE` | `increase_in_solvency_capital` | be | aggregate / policy-month |
| `cashflows_interest_on_reserves_BE` | `interest_on_reserves` | be | aggregate / policy-month |
| `cashflows_interest_on_solvency_capital_BE` | `interest_on_solvency_capital` | be | aggregate / policy-month |
| `cashflows_net_profit_after_sm_BE` | `net_profit_after_sm` | be | aggregate / policy-month |
| `cashflows_net_profit_before_sm_BE` | `net_profit_before_sm` | be | aggregate / policy-month |
| `cashflows_net_sar_BE` | `net_sar` | be | aggregate / policy-month |
| `cashflows_part1_sm_BE` | `part1_sm` | be | aggregate / policy-month |
| `cashflows_part2_sm_BE` | `part2_sm` | be | aggregate / policy-month |
| `cashflows_profit_before_tax_BE` | `profit_before_tax` | be | aggregate / policy-month |
| `cashflows_profit_transfer_BE` | `profit_transfer` | be | aggregate / policy-month |
| `cashflows_reins_premiums_BE` | `reins_premiums` | be | aggregate / policy-month |
| `cashflows_reins_recoveries_BE` | `reins_recoveries` | be | aggregate / policy-month |
| `cashflows_reins_sum_assured_BE` | `reins_sum_assured` | be | aggregate / policy-month |
| `cashflows_required_solvency_capital_BE` | `required_solvency_capital` | be | aggregate / policy-month |
| `cashflows_tax_BE` | `tax` | be | aggregate / policy-month |
| `MCEV_bel_BE` | `bel` | be | aggregate / policy-month |
| `MCEV_bel_pp_BE` | `bel_pp` | be | aggregate / policy-month |
| `MCEV_coc_BE` | `coc` | be | aggregate / policy-month |
| `MCEV_fcc_BE` | `fcc` | be | aggregate / policy-month |
| `MCEV_ifrs_bel_BE` | `ifrs_bel` | be | aggregate / policy-month |
| `MCEV_ifrs_bel_pp_BE` | `ifrs_bel_pp` | be | aggregate / policy-month |
| `MCEV_ifrs_expense_capital_BE` | `ifrs_expense_capital` | be | aggregate / policy-month |
| `MCEV_interest_on_cashflows_BE` | `mcev_interest_on_cashflows` | be | aggregate / policy-month |
| `MCEV_interest_on_reserve_BE` | `mcev_interest_on_reserve` | be | aggregate / policy-month |
| `MCEV_interest_on_sm_BE` | `interest_on_sm` | be | aggregate / policy-month |
| `MCEV_net_cf_BE` | `mcev_net_cf` | be | aggregate / policy-month |
| `MCEV_net_profit_BE` | `mcev_net_profit` | be | aggregate / policy-month |
| `MCEV_profit_before_tax_BE` | `mcev_profit_before_tax` | be | aggregate / policy-month |
| `MCEV_profit_transfer_BE` | `mcev_profit_transfer` | be | aggregate / policy-month |
| `MCEV_profit_transfer_interest_on_sm_BE` | `profit_transfer_interest_on_sm` | be | aggregate / policy-month |
| `MCEV_pv_premium_BE` | `pv_premium` | be | aggregate / policy-month |
| `MCEV_pvfp_BE` | `pvfp` | be | aggregate / policy-month |
| `MCEV_tax_BE` | `mcev_tax` | be | aggregate / policy-month |
| `MCEV_tax_interest_on_sm_BE` | `tax_interest_on_sm` | be | aggregate / policy-month |
| `MCEV_pvfp_BE` | `pvfp` | be | seriatim step 0 |
| `MCEV_pv_premium_BE` | `pv_premium` | be | seriatim step 0 |
| `MCEV_bel_BE` | `bel` | be | seriatim step 0 |
| `MCEV_fcc_BE` | `fcc` | be | seriatim step 0 |
| `cashflows_gross_reserve_pp_reserving` | `gross_reserve_pp` | reserving | seriatim step 0 |
| `cashflows_net_reserve_pp_reserving` | `net_reserve_pp` | reserving | seriatim step 0 |
| `Annualised_premium` | `premiums` | be | seriatim step 1 |

Book ratio columns (held numerator / eligible lives; sign shown):

| Output | Numerator | Denominator | Basis | Sign |
|---|---|---|---|---|
| `cashflows_gross_reserve_pp_reserving` | `gross_reserve_amount` | `eligible_reserve_lives` | reserving | 1 |
| `cashflows_net_reserve_pp_reserving` | `net_reserve_amount` | `eligible_reserve_lives` | reserving | 1 |
| `MCEV_bel_pp_BE` | `bel` | `eligible_reserve_lives` | be | -1 |
| `MCEV_ifrs_bel_pp_BE` | `ifrs_bel` | `eligible_reserve_lives` | be | 1 |

## CRITICAL_ILLNESS_RIDER

| Output | Source | Basis | Role / step |
|---|---|---|---|
| `Policy_Number` | `<policy number>` | - | key |
| `Policy_Month` | `policy_month` | - | key |
| `Calendar_Month` | `<calendar month>` | - | key |
| `Projection_Step` | `<projection step>` | - | key |
| `Modal_Factor` | `modal_factor` | - | key |
| `decrements_critical_illness_reserving` | `rider_event` | reserving | aggregate / policy-month |
| `decrements_cumulative_critical_illness_reserving` | `cumulative_claims` | reserving | aggregate / policy-month |
| `decrements_deaths_out_of_critical_illness_reserving` | `stock_deaths` | reserving | aggregate / policy-month |
| `decrements_deaths_reserving` | `deaths` | reserving | aggregate / policy-month |
| `decrements_lapses_reserving` | `lapses` | reserving | aggregate / policy-month |
| `decrements_lives_so_begin_reserving` | `lives_begin` | reserving | aggregate / policy-month |
| `decrements_lives_so_end_reserving` | `lives_end` | reserving | aggregate / policy-month |
| `decrements_maturities_reserving` | `maturities` | reserving | aggregate / policy-month |
| `decrements_net_cumulative_critical_illness_reserving` | `claim_stock` | reserving | aggregate / policy-month |
| `cashflows_ci_benefit_reserving` | `event_benefit` | reserving | aggregate / policy-month |
| `cashflows_claim_expenses_reserving` | `claim_expenses` | reserving | aggregate / policy-month |
| `cashflows_commissions_reserving` | `commissions` | reserving | aggregate / policy-month |
| `cashflows_discounted_cf_reserving_reserving` | `discounted_net_cf` | reserving | aggregate / policy-month |
| `cashflows_discounted_cf_with_reins_reserving` | `discounted_cf_with_reins` | reserving | aggregate / policy-month |
| `cashflows_gross_reserve_pp_reserving` | `gross_reserve_pp` | reserving | aggregate / policy-month |
| `cashflows_initial_expense_reserving` | `initial_expense` | reserving | aggregate / policy-month |
| `cashflows_interest_on_cashflows_reserving` | `interest_on_cashflows` | reserving | aggregate / policy-month |
| `cashflows_net_cashflows_reserving` | `net_cashflows` | reserving | aggregate / policy-month |
| `cashflows_net_cf_with_reinsurance_reserving` | `net_cf_with_reinsurance` | reserving | aggregate / policy-month |
| `cashflows_net_reserve_pp_reserving` | `net_reserve_pp` | reserving | aggregate / policy-month |
| `cashflows_premiums_reserving` | `premiums` | reserving | aggregate / policy-month |
| `cashflows_reins_premiums_reserving` | `reins_premiums` | reserving | aggregate / policy-month |
| `cashflows_reins_recoveries_reserving` | `reins_recoveries` | reserving | aggregate / policy-month |
| `cashflows_reins_sum_assured_reserving` | `reins_sum_assured` | reserving | aggregate / policy-month |
| `cashflows_renewal_expenses_reserving` | `renewal_expenses` | reserving | aggregate / policy-month |
| `cashflows_surrender_benefits_reserving` | `surrender_benefits` | reserving | aggregate / policy-month |
| `cashflows_upr_reserving` | `upr` | reserving | aggregate / policy-month |
| `cashflows_wop_benefit_reserving` | `wop_benefit` | reserving | aggregate / policy-month |
| `decrements_critical_illness_BE` | `rider_event` | be | aggregate / policy-month |
| `decrements_cumulative_critical_illness_BE` | `cumulative_claims` | be | aggregate / policy-month |
| `decrements_deaths_BE` | `deaths` | be | aggregate / policy-month |
| `decrements_deaths_out_of_critical_illness_BE` | `stock_deaths` | be | aggregate / policy-month |
| `decrements_lapses_BE` | `lapses` | be | aggregate / policy-month |
| `decrements_lives_so_begin_BE` | `lives_begin` | be | aggregate / policy-month |
| `decrements_lives_so_end_BE` | `lives_end` | be | aggregate / policy-month |
| `decrements_maturities_BE` | `maturities` | be | aggregate / policy-month |
| `decrements_net_cumulative_critical_illness_BE` | `claim_stock` | be | aggregate / policy-month |
| `cashflows_be_ci_benefit_BE` | `event_benefit` | be | aggregate / policy-month |
| `cashflows_be_claim_expenses_BE` | `claim_expenses` | be | aggregate / policy-month |
| `cashflows_be_commissions_BE` | `commissions` | be | aggregate / policy-month |
| `cashflows_be_initial_expense_BE` | `initial_expense` | be | aggregate / policy-month |
| `cashflows_be_interest_on_cashflows_BE` | `interest_on_cashflows` | be | aggregate / policy-month |
| `cashflows_be_net_cf_BE` | `be_net_cf` | be | aggregate / policy-month |
| `cashflows_be_premiums_BE` | `premiums` | be | aggregate / policy-month |
| `cashflows_be_reinsurance_premiums_BE` | `reins_premiums` | be | aggregate / policy-month |
| `cashflows_be_reinsurance_recoveries_BE` | `reins_recoveries` | be | aggregate / policy-month |
| `cashflows_be_renewal_expenses_BE` | `renewal_expenses` | be | aggregate / policy-month |
| `cashflows_be_reserves_BE` | `be_reserves` | be | aggregate / policy-month |
| `cashflows_be_surrender_benefits_BE` | `surrender_benefits` | be | aggregate / policy-month |
| `cashflows_be_wop_benefit_BE` | `wop_benefit` | be | aggregate / policy-month |
| `cashflows_cost_of_capital_BE` | `cost_of_capital` | be | aggregate / policy-month |
| `cashflows_gross_sar_BE` | `gross_sar` | be | aggregate / policy-month |
| `cashflows_increase_in_reserves_BE` | `increase_in_reserves` | be | aggregate / policy-month |
| `cashflows_increase_in_solvency_capital_BE` | `increase_in_solvency_capital` | be | aggregate / policy-month |
| `cashflows_interest_on_reserves_BE` | `interest_on_reserves` | be | aggregate / policy-month |
| `cashflows_interest_on_solvency_capital_BE` | `interest_on_solvency_capital` | be | aggregate / policy-month |
| `cashflows_net_cf_with_reinsurance_BE` | `net_cf_with_reinsurance` | be | aggregate / policy-month |
| `cashflows_net_profit_after_sm_BE` | `net_profit_after_sm` | be | aggregate / policy-month |
| `cashflows_net_profit_before_sm_BE` | `net_profit_before_sm` | be | aggregate / policy-month |
| `cashflows_net_sar_BE` | `net_sar` | be | aggregate / policy-month |
| `cashflows_profit_before_tax_BE` | `profit_before_tax` | be | aggregate / policy-month |
| `cashflows_profit_transfer_BE` | `profit_transfer` | be | aggregate / policy-month |
| `cashflows_reins_premiums_BE` | `reins_premiums` | be | aggregate / policy-month |
| `cashflows_reins_recoveries_BE` | `reins_recoveries` | be | aggregate / policy-month |
| `cashflows_reins_sum_assured_BE` | `reins_sum_assured` | be | aggregate / policy-month |
| `cashflows_required_solvency_capital_BE` | `required_solvency_capital` | be | aggregate / policy-month |
| `cashflows_tax_BE` | `tax` | be | aggregate / policy-month |
| `MCEV_bel_BE` | `bel` | be | aggregate / policy-month |
| `MCEV_bel_pp_BE` | `bel_pp` | be | aggregate / policy-month |
| `MCEV_coc_BE` | `coc` | be | aggregate / policy-month |
| `MCEV_fcc_BE` | `fcc` | be | aggregate / policy-month |
| `MCEV_ifrs_bel_BE` | `ifrs_bel` | be | aggregate / policy-month |
| `MCEV_ifrs_bel_pp_BE` | `ifrs_bel_pp` | be | aggregate / policy-month |
| `MCEV_ifrs_expense_capital_BE` | `ifrs_expense_capital` | be | aggregate / policy-month |
| `MCEV_interest_on_cashflows_BE` | `mcev_interest_on_cashflows` | be | aggregate / policy-month |
| `MCEV_interest_on_reserve_BE` | `mcev_interest_on_reserve` | be | aggregate / policy-month |
| `MCEV_interest_on_sm_BE` | `interest_on_sm` | be | aggregate / policy-month |
| `MCEV_net_cf_BE` | `mcev_net_cf` | be | aggregate / policy-month |
| `MCEV_net_profit_BE` | `mcev_net_profit` | be | aggregate / policy-month |
| `MCEV_profit_before_tax_BE` | `mcev_profit_before_tax` | be | aggregate / policy-month |
| `MCEV_profit_transfer_BE` | `mcev_profit_transfer` | be | aggregate / policy-month |
| `MCEV_profit_transfer_interest_on_sm_BE` | `profit_transfer_interest_on_sm` | be | aggregate / policy-month |
| `MCEV_pv_premium_BE` | `pv_premium` | be | aggregate / policy-month |
| `MCEV_pvfp_BE` | `pvfp` | be | aggregate / policy-month |
| `MCEV_tax_BE` | `mcev_tax` | be | aggregate / policy-month |
| `MCEV_tax_interest_on_sm_BE` | `tax_interest_on_sm` | be | aggregate / policy-month |
| `MCEV_pvfp_BE` | `pvfp` | be | seriatim step 0 |
| `MCEV_pv_premium_BE` | `pv_premium` | be | seriatim step 0 |
| `MCEV_bel_BE` | `bel` | be | seriatim step 0 |
| `MCEV_fcc_BE` | `fcc` | be | seriatim step 0 |
| `cashflows_gross_reserve_pp_reserving` | `gross_reserve_pp` | reserving | seriatim step 0 |
| `cashflows_net_reserve_pp_reserving` | `net_reserve_pp` | reserving | seriatim step 0 |
| `Annualised_premium` | `annualised_premium` | - | seriatim step 1 |

Book ratio columns (held numerator / eligible lives; sign shown):

| Output | Numerator | Denominator | Basis | Sign |
|---|---|---|---|---|
| `cashflows_gross_reserve_pp_reserving` | `gross_reserve_amount` | `eligible_reserve_lives` | reserving | 1 |
| `cashflows_net_reserve_pp_reserving` | `net_reserve_amount` | `eligible_reserve_lives` | reserving | 1 |
| `MCEV_bel_pp_BE` | `bel` | `eligible_reserve_lives` | be | -1 |
| `MCEV_ifrs_bel_pp_BE` | `ifrs_bel` | `eligible_reserve_lives` | be | 1 |

## DISABILITY_RIDER

| Output | Source | Basis | Role / step |
|---|---|---|---|
| `Policy_Number` | `<policy number>` | - | key |
| `Policy_Month` | `policy_month` | - | key |
| `Calendar_Month` | `<calendar month>` | - | key |
| `Projection_Step` | `<projection step>` | - | key |
| `Modal_Factor` | `modal_factor` | - | key |
| `decrements_cumulative_disability_reserving` | `cumulative_claims` | reserving | aggregate / policy-month |
| `decrements_deaths_out_of_disability_reserving` | `stock_deaths` | reserving | aggregate / policy-month |
| `decrements_deaths_reserving` | `deaths` | reserving | aggregate / policy-month |
| `decrements_disability_reserving` | `rider_event` | reserving | aggregate / policy-month |
| `decrements_lapses_reserving` | `lapses` | reserving | aggregate / policy-month |
| `decrements_lives_so_begin_reserving` | `lives_begin` | reserving | aggregate / policy-month |
| `decrements_lives_so_end_reserving` | `lives_end` | reserving | aggregate / policy-month |
| `decrements_maturities_reserving` | `maturities` | reserving | aggregate / policy-month |
| `decrements_net_cumulative_disability_reserving` | `claim_stock` | reserving | aggregate / policy-month |
| `cashflows_claim_expenses_reserving` | `claim_expenses` | reserving | aggregate / policy-month |
| `cashflows_commissions_reserving` | `commissions` | reserving | aggregate / policy-month |
| `cashflows_discounted_cf_reserving_reserving` | `discounted_net_cf` | reserving | aggregate / policy-month |
| `cashflows_discounted_cf_with_reins_reserving` | `discounted_cf_with_reins` | reserving | aggregate / policy-month |
| `cashflows_gross_reserve_pp_reserving` | `gross_reserve_pp` | reserving | aggregate / policy-month |
| `cashflows_initial_expense_reserving` | `initial_expense` | reserving | aggregate / policy-month |
| `cashflows_interest_on_cashflows_reserving` | `interest_on_cashflows` | reserving | aggregate / policy-month |
| `cashflows_net_cashflows_reserving` | `net_cashflows` | reserving | aggregate / policy-month |
| `cashflows_net_cf_with_reinsurance_reserving` | `net_cf_with_reinsurance` | reserving | aggregate / policy-month |
| `cashflows_net_reserve_pp_reserving` | `net_reserve_pp` | reserving | aggregate / policy-month |
| `cashflows_premiums_reserving` | `premiums` | reserving | aggregate / policy-month |
| `cashflows_reins_premiums_reserving` | `reins_premiums` | reserving | aggregate / policy-month |
| `cashflows_reins_recoveries_reserving` | `reins_recoveries` | reserving | aggregate / policy-month |
| `cashflows_reins_sum_assured_reserving` | `reins_sum_assured` | reserving | aggregate / policy-month |
| `cashflows_renewal_expenses_reserving` | `renewal_expenses` | reserving | aggregate / policy-month |
| `cashflows_surrender_benefits_reserving` | `surrender_benefits` | reserving | aggregate / policy-month |
| `cashflows_tpd_benefit_reserving` | `event_benefit` | reserving | aggregate / policy-month |
| `cashflows_upr_reserving` | `upr` | reserving | aggregate / policy-month |
| `cashflows_wop_benefit_reserving` | `wop_benefit` | reserving | aggregate / policy-month |
| `decrements_cumulative_disability_BE` | `cumulative_claims` | be | aggregate / policy-month |
| `decrements_deaths_BE` | `deaths` | be | aggregate / policy-month |
| `decrements_deaths_out_of_disability_BE` | `stock_deaths` | be | aggregate / policy-month |
| `decrements_disability_BE` | `rider_event` | be | aggregate / policy-month |
| `decrements_lapses_BE` | `lapses` | be | aggregate / policy-month |
| `decrements_lives_so_begin_BE` | `lives_begin` | be | aggregate / policy-month |
| `decrements_lives_so_end_BE` | `lives_end` | be | aggregate / policy-month |
| `decrements_maturities_BE` | `maturities` | be | aggregate / policy-month |
| `decrements_net_cumulative_disability_BE` | `claim_stock` | be | aggregate / policy-month |
| `cashflows_be_claim_expenses_BE` | `claim_expenses` | be | aggregate / policy-month |
| `cashflows_be_commissions_BE` | `commissions` | be | aggregate / policy-month |
| `cashflows_be_initial_expense_BE` | `initial_expense` | be | aggregate / policy-month |
| `cashflows_be_interest_on_cashflows_BE` | `interest_on_cashflows` | be | aggregate / policy-month |
| `cashflows_be_net_cf_BE` | `be_net_cf` | be | aggregate / policy-month |
| `cashflows_be_premiums_BE` | `premiums` | be | aggregate / policy-month |
| `cashflows_be_reinsurance_premiums_BE` | `reins_premiums` | be | aggregate / policy-month |
| `cashflows_be_reinsurance_recoveries_BE` | `reins_recoveries` | be | aggregate / policy-month |
| `cashflows_be_renewal_expenses_BE` | `renewal_expenses` | be | aggregate / policy-month |
| `cashflows_be_reserves_BE` | `be_reserves` | be | aggregate / policy-month |
| `cashflows_be_surrender_benefits_BE` | `surrender_benefits` | be | aggregate / policy-month |
| `cashflows_be_tpd_benefit_BE` | `event_benefit` | be | aggregate / policy-month |
| `cashflows_be_wop_benefit_BE` | `wop_benefit` | be | aggregate / policy-month |
| `cashflows_cost_of_capital_BE` | `cost_of_capital` | be | aggregate / policy-month |
| `cashflows_gross_sar_BE` | `gross_sar` | be | aggregate / policy-month |
| `cashflows_increase_in_reserves_BE` | `increase_in_reserves` | be | aggregate / policy-month |
| `cashflows_increase_in_solvency_capital_BE` | `increase_in_solvency_capital` | be | aggregate / policy-month |
| `cashflows_interest_on_reserves_BE` | `interest_on_reserves` | be | aggregate / policy-month |
| `cashflows_interest_on_solvency_capital_BE` | `interest_on_solvency_capital` | be | aggregate / policy-month |
| `cashflows_net_cf_with_reinsurance_BE` | `net_cf_with_reinsurance` | be | aggregate / policy-month |
| `cashflows_net_profit_after_sm_BE` | `net_profit_after_sm` | be | aggregate / policy-month |
| `cashflows_net_profit_before_sm_BE` | `net_profit_before_sm` | be | aggregate / policy-month |
| `cashflows_net_sar_BE` | `net_sar` | be | aggregate / policy-month |
| `cashflows_profit_before_tax_BE` | `profit_before_tax` | be | aggregate / policy-month |
| `cashflows_profit_transfer_BE` | `profit_transfer` | be | aggregate / policy-month |
| `cashflows_reins_premiums_BE` | `reins_premiums` | be | aggregate / policy-month |
| `cashflows_reins_recoveries_BE` | `reins_recoveries` | be | aggregate / policy-month |
| `cashflows_reins_sum_assured_BE` | `reins_sum_assured` | be | aggregate / policy-month |
| `cashflows_required_solvency_capital_BE` | `required_solvency_capital` | be | aggregate / policy-month |
| `cashflows_tax_BE` | `tax` | be | aggregate / policy-month |
| `MCEV_bel_BE` | `bel` | be | aggregate / policy-month |
| `MCEV_bel_pp_BE` | `bel_pp` | be | aggregate / policy-month |
| `MCEV_coc_BE` | `coc` | be | aggregate / policy-month |
| `MCEV_fcc_BE` | `fcc` | be | aggregate / policy-month |
| `MCEV_ifrs_bel_BE` | `ifrs_bel` | be | aggregate / policy-month |
| `MCEV_ifrs_bel_pp_BE` | `ifrs_bel_pp` | be | aggregate / policy-month |
| `MCEV_ifrs_expense_capital_BE` | `ifrs_expense_capital` | be | aggregate / policy-month |
| `MCEV_interest_on_cashflows_BE` | `mcev_interest_on_cashflows` | be | aggregate / policy-month |
| `MCEV_interest_on_reserve_BE` | `mcev_interest_on_reserve` | be | aggregate / policy-month |
| `MCEV_interest_on_sm_BE` | `interest_on_sm` | be | aggregate / policy-month |
| `MCEV_net_cf_BE` | `mcev_net_cf` | be | aggregate / policy-month |
| `MCEV_net_profit_BE` | `mcev_net_profit` | be | aggregate / policy-month |
| `MCEV_profit_before_tax_BE` | `mcev_profit_before_tax` | be | aggregate / policy-month |
| `MCEV_profit_transfer_BE` | `mcev_profit_transfer` | be | aggregate / policy-month |
| `MCEV_profit_transfer_interest_on_sm_BE` | `profit_transfer_interest_on_sm` | be | aggregate / policy-month |
| `MCEV_pv_premium_BE` | `pv_premium` | be | aggregate / policy-month |
| `MCEV_pvfp_BE` | `pvfp` | be | aggregate / policy-month |
| `MCEV_tax_BE` | `mcev_tax` | be | aggregate / policy-month |
| `MCEV_tax_interest_on_sm_BE` | `tax_interest_on_sm` | be | aggregate / policy-month |
| `MCEV_pvfp_BE` | `pvfp` | be | seriatim step 0 |
| `MCEV_pv_premium_BE` | `pv_premium` | be | seriatim step 0 |
| `MCEV_bel_BE` | `bel` | be | seriatim step 0 |
| `MCEV_fcc_BE` | `fcc` | be | seriatim step 0 |
| `cashflows_gross_reserve_pp_reserving` | `gross_reserve_pp` | reserving | seriatim step 0 |
| `cashflows_net_reserve_pp_reserving` | `net_reserve_pp` | reserving | seriatim step 0 |
| `Annualised_premium` | `annualised_premium` | - | seriatim step 1 |

Book ratio columns (held numerator / eligible lives; sign shown):

| Output | Numerator | Denominator | Basis | Sign |
|---|---|---|---|---|
| `cashflows_gross_reserve_pp_reserving` | `gross_reserve_amount` | `eligible_reserve_lives` | reserving | 1 |
| `cashflows_net_reserve_pp_reserving` | `net_reserve_amount` | `eligible_reserve_lives` | reserving | 1 |
| `MCEV_bel_pp_BE` | `bel` | `eligible_reserve_lives` | be | -1 |
| `MCEV_ifrs_bel_pp_BE` | `ifrs_bel` | `eligible_reserve_lives` | be | 1 |

## TERM

| Output | Source | Basis | Role / step |
|---|---|---|---|
| `Policy_Number` | `<policy number>` | - | key |
| `Policy_Month` | `policy_month` | - | key |
| `Calendar_Month` | `<calendar month>` | - | key |
| `Projection_Step` | `<projection step>` | - | key |
| `Modal_Factor` | `modal_factor` | - | key |
| `decrements_deaths_reserving` | `deaths` | reserving | aggregate / policy-month |
| `decrements_lapses_reserving` | `lapses` | reserving | aggregate / policy-month |
| `decrements_lives_so_begin_reserving` | `lives_begin` | reserving | aggregate / policy-month |
| `decrements_lives_so_end_reserving` | `lives_end` | reserving | aggregate / policy-month |
| `decrements_maturities_reserving` | `maturities` | reserving | aggregate / policy-month |
| `cashflows_claim_expenses_reserving` | `claim_expenses` | reserving | aggregate / policy-month |
| `cashflows_commissions_reserving` | `commissions` | reserving | aggregate / policy-month |
| `cashflows_death_benefits_reserving` | `death_benefits` | reserving | aggregate / policy-month |
| `cashflows_discounted_cf_with_reins_reserving` | `discounted_cf_with_reins` | reserving | aggregate / policy-month |
| `cashflows_discounted_net_cf_reserving` | `discounted_net_cf` | reserving | aggregate / policy-month |
| `cashflows_gross_reserve_pp_reserving` | `gross_reserve_pp` | reserving | aggregate / policy-month |
| `cashflows_initial_expense_reserving` | `initial_expense` | reserving | aggregate / policy-month |
| `cashflows_interest_on_cashflows_reserving` | `interest_on_cashflows` | reserving | aggregate / policy-month |
| `cashflows_net_cashflows_reserving` | `net_cashflows` | reserving | aggregate / policy-month |
| `cashflows_net_cf_with_reinsurance_reserving` | `net_cf_with_reinsurance` | reserving | aggregate / policy-month |
| `cashflows_net_reserve_pp_reserving` | `net_reserve_pp` | reserving | aggregate / policy-month |
| `cashflows_premiums_reserving` | `premiums` | reserving | aggregate / policy-month |
| `cashflows_reins_premiums_reserving` | `reins_premiums` | reserving | aggregate / policy-month |
| `cashflows_reins_recoveries_reserving` | `reins_recoveries` | reserving | aggregate / policy-month |
| `cashflows_reins_sum_assured_reserving` | `reins_sum_assured` | reserving | aggregate / policy-month |
| `cashflows_renewal_expenses_reserving` | `renewal_expenses` | reserving | aggregate / policy-month |
| `cashflows_surrender_benefits_reserving` | `surrender_benefits` | reserving | aggregate / policy-month |
| `decrements_deaths_BE` | `deaths` | be | aggregate / policy-month |
| `decrements_lapses_BE` | `lapses` | be | aggregate / policy-month |
| `decrements_lives_so_begin_BE` | `lives_begin` | be | aggregate / policy-month |
| `decrements_lives_so_end_BE` | `lives_end` | be | aggregate / policy-month |
| `decrements_maturities_BE` | `maturities` | be | aggregate / policy-month |
| `cashflows_be_claim_expenses_BE` | `claim_expenses` | be | aggregate / policy-month |
| `cashflows_be_commissions_BE` | `commissions` | be | aggregate / policy-month |
| `cashflows_be_death_benefits_BE` | `death_benefits` | be | aggregate / policy-month |
| `cashflows_be_initial_expense_BE` | `initial_expense` | be | aggregate / policy-month |
| `cashflows_be_interest_on_cashflows_BE` | `interest_on_cashflows` | be | aggregate / policy-month |
| `cashflows_be_net_cf_BE` | `be_net_cf` | be | aggregate / policy-month |
| `cashflows_be_premiums_BE` | `premiums` | be | aggregate / policy-month |
| `cashflows_be_reinsurance_premiums_BE` | `reins_premiums` | be | aggregate / policy-month |
| `cashflows_be_reinsurance_recoveries_BE` | `reins_recoveries` | be | aggregate / policy-month |
| `cashflows_be_renewal_expenses_BE` | `renewal_expenses` | be | aggregate / policy-month |
| `cashflows_be_reserves_BE` | `be_reserves` | be | aggregate / policy-month |
| `cashflows_be_surrender_benefits_BE` | `surrender_benefits` | be | aggregate / policy-month |
| `cashflows_cost_of_capital_BE` | `cost_of_capital` | be | aggregate / policy-month |
| `cashflows_gross_sar_BE` | `gross_sar` | be | aggregate / policy-month |
| `cashflows_increase_in_reserves_BE` | `increase_in_reserves` | be | aggregate / policy-month |
| `cashflows_increase_in_solvency_capital_BE` | `increase_in_solvency_capital` | be | aggregate / policy-month |
| `cashflows_interest_on_reserves_BE` | `interest_on_reserves` | be | aggregate / policy-month |
| `cashflows_interest_on_solvency_capital_BE` | `interest_on_solvency_capital` | be | aggregate / policy-month |
| `cashflows_net_cf_with_reinsurance_BE` | `net_cf_with_reinsurance` | be | aggregate / policy-month |
| `cashflows_net_profit_after_sm_BE` | `net_profit_after_sm` | be | aggregate / policy-month |
| `cashflows_net_profit_before_sm_BE` | `net_profit_before_sm` | be | aggregate / policy-month |
| `cashflows_net_sar_BE` | `net_sar` | be | aggregate / policy-month |
| `cashflows_part1_sm_BE` | `part1_sm` | be | aggregate / policy-month |
| `cashflows_part2_sm_BE` | `part2_sm` | be | aggregate / policy-month |
| `cashflows_profit_before_tax_BE` | `profit_before_tax` | be | aggregate / policy-month |
| `cashflows_profit_transfer_BE` | `profit_transfer` | be | aggregate / policy-month |
| `cashflows_reins_premiums_BE` | `reins_premiums` | be | aggregate / policy-month |
| `cashflows_reins_recoveries_BE` | `reins_recoveries` | be | aggregate / policy-month |
| `cashflows_reins_sum_assured_BE` | `reins_sum_assured` | be | aggregate / policy-month |
| `cashflows_required_solvency_capital_BE` | `required_solvency_capital` | be | aggregate / policy-month |
| `cashflows_tax_BE` | `tax` | be | aggregate / policy-month |
| `MCEV_bel_BE` | `bel` | be | aggregate / policy-month |
| `MCEV_bel_pp_BE` | `bel_pp` | be | aggregate / policy-month |
| `MCEV_coc_BE` | `coc` | be | aggregate / policy-month |
| `MCEV_fcc_BE` | `fcc` | be | aggregate / policy-month |
| `MCEV_ifrs_bel_BE` | `ifrs_bel` | be | aggregate / policy-month |
| `MCEV_ifrs_bel_pp_BE` | `ifrs_bel_pp` | be | aggregate / policy-month |
| `MCEV_ifrs_expense_capital_BE` | `ifrs_expense_capital` | be | aggregate / policy-month |
| `MCEV_interest_on_cashflows_BE` | `mcev_interest_on_cashflows` | be | aggregate / policy-month |
| `MCEV_interest_on_reserve_BE` | `mcev_interest_on_reserve` | be | aggregate / policy-month |
| `MCEV_interest_on_sm_BE` | `interest_on_sm` | be | aggregate / policy-month |
| `MCEV_net_cf_BE` | `mcev_net_cf` | be | aggregate / policy-month |
| `MCEV_net_profit_BE` | `mcev_net_profit` | be | aggregate / policy-month |
| `MCEV_profit_before_tax_BE` | `mcev_profit_before_tax` | be | aggregate / policy-month |
| `MCEV_profit_transfer_BE` | `mcev_profit_transfer` | be | aggregate / policy-month |
| `MCEV_profit_transfer_interest_on_sm_BE` | `profit_transfer_interest_on_sm` | be | aggregate / policy-month |
| `MCEV_pv_premium_BE` | `pv_premium` | be | aggregate / policy-month |
| `MCEV_pvfp_BE` | `pvfp` | be | aggregate / policy-month |
| `MCEV_tax_BE` | `mcev_tax` | be | aggregate / policy-month |
| `MCEV_tax_interest_on_sm_BE` | `tax_interest_on_sm` | be | aggregate / policy-month |
| `MCEV_pvfp_BE` | `pvfp` | be | seriatim step 0 |
| `MCEV_pv_premium_BE` | `pv_premium` | be | seriatim step 0 |
| `MCEV_bel_BE` | `bel` | be | seriatim step 0 |
| `MCEV_fcc_BE` | `fcc` | be | seriatim step 0 |
| `cashflows_gross_reserve_pp_reserving` | `gross_reserve_pp` | reserving | seriatim step 0 |
| `cashflows_net_reserve_pp_reserving` | `net_reserve_pp` | reserving | seriatim step 0 |
| `Annualised_premium` | `annualised_premium` | - | seriatim step 1 |

Book ratio columns (held numerator / eligible lives; sign shown):

| Output | Numerator | Denominator | Basis | Sign |
|---|---|---|---|---|
| `cashflows_gross_reserve_pp_reserving` | `gross_reserve_amount` | `eligible_reserve_lives` | reserving | 1 |
| `cashflows_net_reserve_pp_reserving` | `net_reserve_amount` | `eligible_reserve_lives` | reserving | 1 |
| `MCEV_bel_pp_BE` | `bel` | `eligible_reserve_lives` | be | -1 |
| `MCEV_ifrs_bel_pp_BE` | `ifrs_bel` | `eligible_reserve_lives` | be | 1 |

## UNIT_LINKED

| Output | Source | Basis | Role / step |
|---|---|---|---|
| `Policy_Number` | `<policy number>` | - | key |
| `Policy_Month` | `policy_month` | - | key |
| `Calendar_Month` | `<calendar month>` | - | key |
| `Projection_Step` | `<projection step>` | - | key |
| `funds_opening_unit_fund` | `opening_unit_fund` | - | aggregate / policy-month |
| `funds_opening_dpf_fund` | `opening_dpf_fund` | - | aggregate / policy-month |
| `lives_active_reserving` | `A_end` | reserving | aggregate / policy-month |
| `lives_dpf_reserving` | `D_end` | reserving | aggregate / policy-month |
| `lives_paid_up_reserving` | `R_end` | reserving | aggregate / policy-month |
| `lives_total_reserving` | `lives_end` | reserving | aggregate / policy-month |
| `deaths_active_reserving` | `deaths_A` | reserving | aggregate / policy-month |
| `deaths_dpf_reserving` | `deaths_D` | reserving | aggregate / policy-month |
| `deaths_paid_up_reserving` | `deaths_R` | reserving | aggregate / policy-month |
| `surrenders_active_reserving` | `surrenders_A` | reserving | aggregate / policy-month |
| `cessations_active_reserving` | `cessations_A` | reserving | aggregate / policy-month |
| `transfers_to_dpf_reserving` | `to_dpf` | reserving | aggregate / policy-month |
| `transfers_to_paid_up_reserving` | `to_rpu` | reserving | aggregate / policy-month |
| `exits_active_paid_reserving` | `paid_out_A` | reserving | aggregate / policy-month |
| `exits_dpf_lock_in_reserving` | `lockin_exits_D` | reserving | aggregate / policy-month |
| `surrenders_paid_up_reserving` | `surrenders_R` | reserving | aggregate / policy-month |
| `expiries_paid_up_reserving` | `expiries_R` | reserving | aggregate / policy-month |
| `maturities_active_reserving` | `maturities_A` | reserving | aggregate / policy-month |
| `maturities_paid_up_reserving` | `maturities_R` | reserving | aggregate / policy-month |
| `premiums_reserving` | `premium_income` | reserving | aggregate / policy-month |
| `premiums_allocated_reserving` | `allocated_premiums` | reserving | aggregate / policy-month |
| `charges_allocation_reserving` | `pac_income` | reserving | aggregate / policy-month |
| `charges_administration_reserving` | `admin_income` | reserving | aggregate / policy-month |
| `charges_mortality_reserving` | `mc_income` | reserving | aggregate / policy-month |
| `charges_guarantee_reserving` | `gc_income` | reserving | aggregate / policy-month |
| `charges_fmc_active_reserving` | `fmc_income_A` | reserving | aggregate / policy-month |
| `charges_fmc_paid_up_reserving` | `rpu_fmc_total` | reserving | aggregate / policy-month |
| `charges_fmc_dpf_reserving` | `dpf_fmc` | reserving | aggregate / policy-month |
| `charges_discontinuance_reserving` | `disc_charge_income` | reserving | aggregate / policy-month |
| `charges_total_reserving` | `charge_income` | reserving | aggregate / policy-month |
| `funds_active_reserving` | `unit_reserve_A` | reserving | aggregate / policy-month |
| `funds_dpf_reserving` | `dpf_close` | reserving | aggregate / policy-month |
| `funds_paid_up_reserving` | `rpu_close_total` | reserving | aggregate / policy-month |
| `funds_total_reserving` | `unit_reserve` | reserving | aggregate / policy-month |
| `benefits_unit_active_death_reserving` | `death_unit_A` | reserving | aggregate / policy-month |
| `benefits_unit_active_discontinuance_reserving` | `surrender_unit_A` | reserving | aggregate / policy-month |
| `benefits_unit_active_maturity_reserving` | `maturity_unit_A` | reserving | aggregate / policy-month |
| `benefits_unit_dpf_death_reserving` | `dpf_death_paid` | reserving | aggregate / policy-month |
| `benefits_unit_dpf_release_reserving` | `dpf_lockin_paid` | reserving | aggregate / policy-month |
| `benefits_unit_paid_up_death_reserving` | `death_unit_R` | reserving | aggregate / policy-month |
| `benefits_unit_paid_up_surrender_reserving` | `surrender_unit_R` | reserving | aggregate / policy-month |
| `benefits_unit_paid_up_expiry_reserving` | `expiry_unit_R` | reserving | aggregate / policy-month |
| `benefits_unit_paid_up_maturity_reserving` | `maturity_unit_R` | reserving | aggregate / policy-month |
| `benefits_unit_withdrawals_reserving` | `partial_withdrawal_outgo` | reserving | aggregate / policy-month |
| `benefits_unit_total_reserving` | `unit_benefit_outgo` | reserving | aggregate / policy-month |
| `benefits_non_unit_active_death_reserving` | `death_non_unit_A` | reserving | aggregate / policy-month |
| `benefits_non_unit_paid_up_death_reserving` | `death_non_unit_R` | reserving | aggregate / policy-month |
| `benefits_non_unit_return_of_charges_reserving` | `return_of_charges` | reserving | aggregate / policy-month |
| `benefits_non_unit_active_maturity_top_up_reserving` | `maturity_guarantee_A` | reserving | aggregate / policy-month |
| `benefits_non_unit_paid_up_maturity_top_up_reserving` | `maturity_guarantee_R` | reserving | aggregate / policy-month |
| `benefits_non_unit_additions_reserving` | `addition_outgo` | reserving | aggregate / policy-month |
| `benefits_non_unit_dpf_guarantee_reserving` | `dpf_guarantee_cost` | reserving | aggregate / policy-month |
| `benefits_non_unit_total_reserving` | `non_unit_benefit_outgo` | reserving | aggregate / policy-month |
| `lives_active_BE` | `A_end` | be | aggregate / policy-month |
| `lives_dpf_BE` | `D_end` | be | aggregate / policy-month |
| `lives_paid_up_BE` | `R_end` | be | aggregate / policy-month |
| `lives_total_BE` | `lives_end` | be | aggregate / policy-month |
| `deaths_active_BE` | `deaths_A` | be | aggregate / policy-month |
| `deaths_dpf_BE` | `deaths_D` | be | aggregate / policy-month |
| `deaths_paid_up_BE` | `deaths_R` | be | aggregate / policy-month |
| `surrenders_active_BE` | `surrenders_A` | be | aggregate / policy-month |
| `cessations_active_BE` | `cessations_A` | be | aggregate / policy-month |
| `transfers_to_dpf_BE` | `to_dpf` | be | aggregate / policy-month |
| `transfers_to_paid_up_BE` | `to_rpu` | be | aggregate / policy-month |
| `exits_active_paid_BE` | `paid_out_A` | be | aggregate / policy-month |
| `exits_dpf_lock_in_BE` | `lockin_exits_D` | be | aggregate / policy-month |
| `surrenders_paid_up_BE` | `surrenders_R` | be | aggregate / policy-month |
| `expiries_paid_up_BE` | `expiries_R` | be | aggregate / policy-month |
| `maturities_active_BE` | `maturities_A` | be | aggregate / policy-month |
| `maturities_paid_up_BE` | `maturities_R` | be | aggregate / policy-month |
| `premiums_BE` | `premium_income` | be | aggregate / policy-month |
| `premiums_allocated_BE` | `allocated_premiums` | be | aggregate / policy-month |
| `charges_allocation_BE` | `pac_income` | be | aggregate / policy-month |
| `charges_administration_BE` | `admin_income` | be | aggregate / policy-month |
| `charges_mortality_BE` | `mc_income` | be | aggregate / policy-month |
| `charges_guarantee_BE` | `gc_income` | be | aggregate / policy-month |
| `charges_fmc_active_BE` | `fmc_income_A` | be | aggregate / policy-month |
| `charges_fmc_paid_up_BE` | `rpu_fmc_total` | be | aggregate / policy-month |
| `charges_fmc_dpf_BE` | `dpf_fmc` | be | aggregate / policy-month |
| `charges_discontinuance_BE` | `disc_charge_income` | be | aggregate / policy-month |
| `charges_total_BE` | `charge_income` | be | aggregate / policy-month |
| `funds_active_BE` | `unit_reserve_A` | be | aggregate / policy-month |
| `funds_dpf_BE` | `dpf_close` | be | aggregate / policy-month |
| `funds_paid_up_BE` | `rpu_close_total` | be | aggregate / policy-month |
| `funds_total_BE` | `unit_reserve` | be | aggregate / policy-month |
| `benefits_unit_active_death_BE` | `death_unit_A` | be | aggregate / policy-month |
| `benefits_unit_active_discontinuance_BE` | `surrender_unit_A` | be | aggregate / policy-month |
| `benefits_unit_active_maturity_BE` | `maturity_unit_A` | be | aggregate / policy-month |
| `benefits_unit_dpf_death_BE` | `dpf_death_paid` | be | aggregate / policy-month |
| `benefits_unit_dpf_release_BE` | `dpf_lockin_paid` | be | aggregate / policy-month |
| `benefits_unit_paid_up_death_BE` | `death_unit_R` | be | aggregate / policy-month |
| `benefits_unit_paid_up_surrender_BE` | `surrender_unit_R` | be | aggregate / policy-month |
| `benefits_unit_paid_up_expiry_BE` | `expiry_unit_R` | be | aggregate / policy-month |
| `benefits_unit_paid_up_maturity_BE` | `maturity_unit_R` | be | aggregate / policy-month |
| `benefits_unit_withdrawals_BE` | `partial_withdrawal_outgo` | be | aggregate / policy-month |
| `benefits_unit_total_BE` | `unit_benefit_outgo` | be | aggregate / policy-month |
| `benefits_non_unit_active_death_BE` | `death_non_unit_A` | be | aggregate / policy-month |
| `benefits_non_unit_paid_up_death_BE` | `death_non_unit_R` | be | aggregate / policy-month |
| `benefits_non_unit_return_of_charges_BE` | `return_of_charges` | be | aggregate / policy-month |
| `benefits_non_unit_active_maturity_top_up_BE` | `maturity_guarantee_A` | be | aggregate / policy-month |
| `benefits_non_unit_paid_up_maturity_top_up_BE` | `maturity_guarantee_R` | be | aggregate / policy-month |
| `benefits_non_unit_additions_BE` | `addition_outgo` | be | aggregate / policy-month |
| `benefits_non_unit_dpf_guarantee_BE` | `dpf_guarantee_cost` | be | aggregate / policy-month |
| `benefits_non_unit_total_BE` | `non_unit_benefit_outgo` | be | aggregate / policy-month |
| `lives_active_MC` | `A_end` | mc | aggregate / policy-month |
| `lives_dpf_MC` | `D_end` | mc | aggregate / policy-month |
| `lives_paid_up_MC` | `R_end` | mc | aggregate / policy-month |
| `lives_total_MC` | `lives_end` | mc | aggregate / policy-month |
| `deaths_active_MC` | `deaths_A` | mc | aggregate / policy-month |
| `deaths_dpf_MC` | `deaths_D` | mc | aggregate / policy-month |
| `deaths_paid_up_MC` | `deaths_R` | mc | aggregate / policy-month |
| `surrenders_active_MC` | `surrenders_A` | mc | aggregate / policy-month |
| `cessations_active_MC` | `cessations_A` | mc | aggregate / policy-month |
| `transfers_to_dpf_MC` | `to_dpf` | mc | aggregate / policy-month |
| `transfers_to_paid_up_MC` | `to_rpu` | mc | aggregate / policy-month |
| `exits_active_paid_MC` | `paid_out_A` | mc | aggregate / policy-month |
| `exits_dpf_lock_in_MC` | `lockin_exits_D` | mc | aggregate / policy-month |
| `surrenders_paid_up_MC` | `surrenders_R` | mc | aggregate / policy-month |
| `expiries_paid_up_MC` | `expiries_R` | mc | aggregate / policy-month |
| `maturities_active_MC` | `maturities_A` | mc | aggregate / policy-month |
| `maturities_paid_up_MC` | `maturities_R` | mc | aggregate / policy-month |
| `premiums_MC` | `premium_income` | mc | aggregate / policy-month |
| `premiums_allocated_MC` | `allocated_premiums` | mc | aggregate / policy-month |
| `charges_allocation_MC` | `pac_income` | mc | aggregate / policy-month |
| `charges_administration_MC` | `admin_income` | mc | aggregate / policy-month |
| `charges_mortality_MC` | `mc_income` | mc | aggregate / policy-month |
| `charges_guarantee_MC` | `gc_income` | mc | aggregate / policy-month |
| `charges_fmc_active_MC` | `fmc_income_A` | mc | aggregate / policy-month |
| `charges_fmc_paid_up_MC` | `rpu_fmc_total` | mc | aggregate / policy-month |
| `charges_fmc_dpf_MC` | `dpf_fmc` | mc | aggregate / policy-month |
| `charges_discontinuance_MC` | `disc_charge_income` | mc | aggregate / policy-month |
| `charges_total_MC` | `charge_income` | mc | aggregate / policy-month |
| `funds_active_MC` | `unit_reserve_A` | mc | aggregate / policy-month |
| `funds_dpf_MC` | `dpf_close` | mc | aggregate / policy-month |
| `funds_paid_up_MC` | `rpu_close_total` | mc | aggregate / policy-month |
| `funds_total_MC` | `unit_reserve` | mc | aggregate / policy-month |
| `benefits_unit_active_death_MC` | `death_unit_A` | mc | aggregate / policy-month |
| `benefits_unit_active_discontinuance_MC` | `surrender_unit_A` | mc | aggregate / policy-month |
| `benefits_unit_active_maturity_MC` | `maturity_unit_A` | mc | aggregate / policy-month |
| `benefits_unit_dpf_death_MC` | `dpf_death_paid` | mc | aggregate / policy-month |
| `benefits_unit_dpf_release_MC` | `dpf_lockin_paid` | mc | aggregate / policy-month |
| `benefits_unit_paid_up_death_MC` | `death_unit_R` | mc | aggregate / policy-month |
| `benefits_unit_paid_up_surrender_MC` | `surrender_unit_R` | mc | aggregate / policy-month |
| `benefits_unit_paid_up_expiry_MC` | `expiry_unit_R` | mc | aggregate / policy-month |
| `benefits_unit_paid_up_maturity_MC` | `maturity_unit_R` | mc | aggregate / policy-month |
| `benefits_unit_withdrawals_MC` | `partial_withdrawal_outgo` | mc | aggregate / policy-month |
| `benefits_unit_total_MC` | `unit_benefit_outgo` | mc | aggregate / policy-month |
| `benefits_non_unit_active_death_MC` | `death_non_unit_A` | mc | aggregate / policy-month |
| `benefits_non_unit_paid_up_death_MC` | `death_non_unit_R` | mc | aggregate / policy-month |
| `benefits_non_unit_return_of_charges_MC` | `return_of_charges` | mc | aggregate / policy-month |
| `benefits_non_unit_active_maturity_top_up_MC` | `maturity_guarantee_A` | mc | aggregate / policy-month |
| `benefits_non_unit_paid_up_maturity_top_up_MC` | `maturity_guarantee_R` | mc | aggregate / policy-month |
| `benefits_non_unit_additions_MC` | `addition_outgo` | mc | aggregate / policy-month |
| `benefits_non_unit_dpf_guarantee_MC` | `dpf_guarantee_cost` | mc | aggregate / policy-month |
| `benefits_non_unit_total_MC` | `non_unit_benefit_outgo` | mc | aggregate / policy-month |
| `funds_opening_unit_fund` | `opening_unit_fund` | - | seriatim step 0 |
| `funds_opening_dpf_fund` | `opening_dpf_fund` | - | seriatim step 0 |

Book ratio columns (held numerator / eligible lives; sign shown):

| Output | Numerator | Denominator | Basis | Sign |
|---|---|---|---|---|

## Term cases reporting tables

### TERM_Base_aggregate_output.parquet

`Projection_Step`, `decrements_deaths_reserving`, `decrements_lapses_reserving`, `decrements_lives_so_begin_reserving`, `decrements_lives_so_end_reserving`, `decrements_maturities_reserving`, `cashflows_claim_expenses_reserving`, `cashflows_commissions_reserving`, `cashflows_death_benefits_reserving`, `cashflows_discounted_cf_with_reins_reserving`, `cashflows_discounted_net_cf_reserving`, `cashflows_gross_reserve_pp_reserving`, `cashflows_initial_expense_reserving`, `cashflows_interest_on_cashflows_reserving`, `cashflows_net_cashflows_reserving`, `cashflows_net_cf_with_reinsurance_reserving`, `cashflows_net_reserve_pp_reserving`, `cashflows_premiums_reserving`, `cashflows_reins_premiums_reserving`, `cashflows_reins_recoveries_reserving`, `cashflows_reins_sum_assured_reserving`, `cashflows_renewal_expenses_reserving`, `cashflows_surrender_benefits_reserving`, `decrements_deaths_BE`, `decrements_lapses_BE`, `decrements_lives_so_begin_BE`, `decrements_lives_so_end_BE`, `decrements_maturities_BE`, `cashflows_be_claim_expenses_BE`, `cashflows_be_commissions_BE`, `cashflows_be_death_benefits_BE`, `cashflows_be_initial_expense_BE`, `cashflows_be_interest_on_cashflows_BE`, `cashflows_be_net_cf_BE`, `cashflows_be_premiums_BE`, `cashflows_be_reinsurance_premiums_BE`, `cashflows_be_reinsurance_recoveries_BE`, `cashflows_be_renewal_expenses_BE`, `cashflows_be_reserves_BE`, `cashflows_be_surrender_benefits_BE`, `cashflows_cost_of_capital_BE`, `cashflows_gross_sar_BE`, `cashflows_increase_in_reserves_BE`, `cashflows_increase_in_solvency_capital_BE`, `cashflows_interest_on_reserves_BE`, `cashflows_interest_on_solvency_capital_BE`, `cashflows_net_cf_with_reinsurance_BE`, `cashflows_net_profit_after_sm_BE`, `cashflows_net_profit_before_sm_BE`, `cashflows_net_sar_BE`, `cashflows_part1_sm_BE`, `cashflows_part2_sm_BE`, `cashflows_profit_before_tax_BE`, `cashflows_profit_transfer_BE`, `cashflows_reins_premiums_BE`, `cashflows_reins_recoveries_BE`, `cashflows_reins_sum_assured_BE`, `cashflows_required_solvency_capital_BE`, `cashflows_tax_BE`, `MCEV_bel_BE`, `MCEV_bel_pp_BE`, `MCEV_coc_BE`, `MCEV_fcc_BE`, `MCEV_ifrs_bel_BE`, `MCEV_ifrs_bel_pp_BE`, `MCEV_ifrs_expense_capital_BE`, `MCEV_interest_on_cashflows_BE`, `MCEV_interest_on_reserve_BE`, `MCEV_interest_on_sm_BE`, `MCEV_net_cf_BE`, `MCEV_net_profit_BE`, `MCEV_profit_before_tax_BE`, `MCEV_profit_transfer_BE`, `MCEV_profit_transfer_interest_on_sm_BE`, `MCEV_pv_premium_BE`, `MCEV_pvfp_BE`, `MCEV_tax_BE`, `MCEV_tax_interest_on_sm_BE`

### cases_impact.parquet

`Product`, `Case`, `cashflows_gross_reserve_pp_reserving`, `cashflows_gross_reserve_pp_reserving_change`, `cashflows_gross_reserve_pp_reserving_change_pct`, `cashflows_net_reserve_pp_reserving`, `cashflows_net_reserve_pp_reserving_change`, `cashflows_net_reserve_pp_reserving_change_pct`, `cashflows_be_reserves_BE`, `cashflows_be_reserves_BE_change`, `cashflows_be_reserves_BE_change_pct`, `MCEV_bel_BE`, `MCEV_bel_BE_change`, `MCEV_bel_BE_change_pct`, `MCEV_pvfp_BE`, `MCEV_pvfp_BE_change`, `MCEV_pvfp_BE_change_pct`, `MCEV_pv_premium_BE`, `MCEV_pv_premium_BE_change`, `MCEV_pv_premium_BE_change_pct`, `MCEV_fcc_BE`, `MCEV_fcc_BE_change`, `MCEV_fcc_BE_change_pct`, `MCEV_ifrs_bel_BE`, `MCEV_ifrs_bel_BE_change`, `MCEV_ifrs_bel_BE_change_pct`, `cashflows_required_solvency_capital_BE`, `cashflows_required_solvency_capital_BE_change`, `cashflows_required_solvency_capital_BE_change_pct`

### TERM_mortality increase_aggregate_output.parquet

`Projection_Step`, `decrements_deaths_reserving`, `decrements_lapses_reserving`, `decrements_lives_so_begin_reserving`, `decrements_lives_so_end_reserving`, `decrements_maturities_reserving`, `cashflows_claim_expenses_reserving`, `cashflows_commissions_reserving`, `cashflows_death_benefits_reserving`, `cashflows_discounted_cf_with_reins_reserving`, `cashflows_discounted_net_cf_reserving`, `cashflows_gross_reserve_pp_reserving`, `cashflows_initial_expense_reserving`, `cashflows_interest_on_cashflows_reserving`, `cashflows_net_cashflows_reserving`, `cashflows_net_cf_with_reinsurance_reserving`, `cashflows_net_reserve_pp_reserving`, `cashflows_premiums_reserving`, `cashflows_reins_premiums_reserving`, `cashflows_reins_recoveries_reserving`, `cashflows_reins_sum_assured_reserving`, `cashflows_renewal_expenses_reserving`, `cashflows_surrender_benefits_reserving`, `decrements_deaths_BE`, `decrements_lapses_BE`, `decrements_lives_so_begin_BE`, `decrements_lives_so_end_BE`, `decrements_maturities_BE`, `cashflows_be_claim_expenses_BE`, `cashflows_be_commissions_BE`, `cashflows_be_death_benefits_BE`, `cashflows_be_initial_expense_BE`, `cashflows_be_interest_on_cashflows_BE`, `cashflows_be_net_cf_BE`, `cashflows_be_premiums_BE`, `cashflows_be_reinsurance_premiums_BE`, `cashflows_be_reinsurance_recoveries_BE`, `cashflows_be_renewal_expenses_BE`, `cashflows_be_reserves_BE`, `cashflows_be_surrender_benefits_BE`, `cashflows_cost_of_capital_BE`, `cashflows_gross_sar_BE`, `cashflows_increase_in_reserves_BE`, `cashflows_increase_in_solvency_capital_BE`, `cashflows_interest_on_reserves_BE`, `cashflows_interest_on_solvency_capital_BE`, `cashflows_net_cf_with_reinsurance_BE`, `cashflows_net_profit_after_sm_BE`, `cashflows_net_profit_before_sm_BE`, `cashflows_net_sar_BE`, `cashflows_part1_sm_BE`, `cashflows_part2_sm_BE`, `cashflows_profit_before_tax_BE`, `cashflows_profit_transfer_BE`, `cashflows_reins_premiums_BE`, `cashflows_reins_recoveries_BE`, `cashflows_reins_sum_assured_BE`, `cashflows_required_solvency_capital_BE`, `cashflows_tax_BE`, `MCEV_bel_BE`, `MCEV_bel_pp_BE`, `MCEV_coc_BE`, `MCEV_fcc_BE`, `MCEV_ifrs_bel_BE`, `MCEV_ifrs_bel_pp_BE`, `MCEV_ifrs_expense_capital_BE`, `MCEV_interest_on_cashflows_BE`, `MCEV_interest_on_reserve_BE`, `MCEV_interest_on_sm_BE`, `MCEV_net_cf_BE`, `MCEV_net_profit_BE`, `MCEV_profit_before_tax_BE`, `MCEV_profit_transfer_BE`, `MCEV_profit_transfer_interest_on_sm_BE`, `MCEV_pv_premium_BE`, `MCEV_pvfp_BE`, `MCEV_tax_BE`, `MCEV_tax_interest_on_sm_BE`

## Term capital reporting tables

### TERM_StressCapital_aggregate_output.parquet

`Projection_Step`, `capital_mortality`, `capital_lapse up`, `capital_lapse down`, `capital_mass lapse`, `capital_expense`, `capital_life catastrophe`, `capital_lapse`, `diversified_capital`, `combined_capital`, `operational_risk`, `total_capital`, `cost_of_capital`, `pv_cost_of_capital`

### cases_impact.parquet

`Product`, `Case`, `combined_capital`, `operational_risk`, `total_capital`, `cost_of_capital`, `pv_cost_of_capital`, `combined_capital_change`, `operational_risk_change`, `total_capital_change`, `cost_of_capital_change`, `pv_cost_of_capital_change`, `combined_capital_change_pct`, `operational_risk_change_pct`, `total_capital_change_pct`, `cost_of_capital_change_pct`, `pv_cost_of_capital_change_pct`

## Term measurement reporting tables

### TERM_Base_aggregate_output.parquet

`IFRS17_acquisition`, `IFRS17_bel_current`, `IFRS17_bel_locked`, `IFRS17_claim_expense`, `IFRS17_claims`, `IFRS17_coverage_units`, `IFRS17_fulfilment_cashflow`, `IFRS17_maintenance`, `IFRS17_premiums`, `IFRS17_pv_acquisition`, `IFRS17_pv_claims`, `IFRS17_pv_coverage_units`, `IFRS17_pv_maintenance`, `IFRS17_pv_premiums`, `IFRS17_pv_recoveries`, `IFRS17_ra_current`, `IFRS17_ra_locked`, `IFRS17_ri_bel_current`, `IFRS17_ri_bel_locked`, `IFRS17_ri_cashflow`, `IFRS17_ri_premiums`, `IFRS17_ri_ra_current`, `IFRS17_ri_ra_locked`, `IFRS17_ri_recoveries`

### TERM_IFRS17_group_output.parquet

`portfolio`, `cohort`, `profitability`, `premiums`, `claims`, `acquisition`, `maintenance`, `claim_expense`, `coverage_units`, `ri_premiums`, `ri_recoveries`, `fulfilment_cashflow`, `ri_cashflow`, `bel_current`, `ra_current`, `ri_bel_current`, `ri_ra_current`, `bel_locked`, `ra_locked`, `ri_bel_locked`, `ri_ra_locked`, `pv_claims`, `pv_premiums`, `pv_acquisition`, `pv_maintenance`, `pv_recoveries`, `pv_coverage_units`, `coverage_units_total`, `recognition_bel`, `recognition_ra`, `recognition_fcf`, `csm_at_recognition`, `loss_component`, `csm_interest`, `ri_csm_at_recognition`, `loss_recovery_component`, `ri_csm_interest`, `policies`

### cases_impact.parquet

`Product`, `Case`, `bel_current`, `ra_current`, `csm_at_recognition`, `loss_component`, `ri_bel_current`, `ri_ra_current`, `ri_csm_at_recognition`, `loss_recovery_component`, `bel_current_change`, `ra_current_change`, `csm_at_recognition_change`, `loss_component_change`, `ri_bel_current_change`, `ri_ra_current_change`, `ri_csm_at_recognition_change`, `loss_recovery_component_change`, `bel_current_change_pct`, `ra_current_change_pct`, `csm_at_recognition_change_pct`, `loss_component_change_pct`, `ri_bel_current_change_pct`, `ri_ra_current_change_pct`, `ri_csm_at_recognition_change_pct`, `loss_recovery_component_change_pct`

## Term rollforward reporting tables

### IFRS17_rollforward.parquet

`Product`, `portfolio`, `cohort`, `profitability`, `csm_opening`, `loss_component_opening`, `ri_csm_opening`, `loss_recovery_component_opening`, `csm_new_business`, `loss_component_new_business`, `ri_csm_new_business`, `loss_recovery_component_new_business`, `csm_interest`, `loss_component_interest`, `ri_csm_interest`, `loss_recovery_component_interest`, `csm_experience`, `loss_component_experience`, `ri_csm_experience`, `loss_recovery_component_experience`, `csm_assumptions`, `loss_component_assumptions`, `ri_csm_assumptions`, `loss_recovery_component_assumptions`, `csm_release`, `loss_component_release`, `ri_csm_release`, `loss_recovery_component_release`, `csm_closing`, `loss_component_closing`, `ri_csm_closing`, `loss_recovery_component_closing`, `bel_current`, `ra_current`, `ri_bel_current`, `ri_ra_current`, `provided_coverage_units`, `future_coverage_units`, `release_fraction`, `released_outflows`, `future_outflows`, `loss_release_fraction`

Other products use the same IFRS17 and bridge measure labels; capital risk labels
come from the selected stress set and can include morbidity for riders.
The generated dynamic list above describes the public Term demo, not arbitrary
plug-in outputs. The selected factory and run record identify the actual contract.
