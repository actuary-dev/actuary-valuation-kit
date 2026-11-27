# Changelog

## Unreleased

- Generate correlated lognormal economic scenarios in valuation runs. Export them
  to supplied-scenario Parquet or build deterministic paths with `avk scenarios`.
- Add the UNIT_LINKED input contract: policy table `policies_ul`, fund holdings
  companion table `policy_funds_ul`, fund universe, variant, charge-scale and
  regulatory-cap tables with formats `avk_ul_keyed_v1` and `avk_ul_year_key_v1`,
  validation before projection, model points in five fund slots, a skeleton
  Valuation product reporting opening funds, and an invented demo book.
- Add UNIT_LINKED compliance tools: `avk ul compliance` tests every variant against the
  reduction-in-yield caps at 4% and 8% gross, `avk ul additions` reports the residual
  additions that restore a breached cap per policy and policy year, and
  `avk ul illustration` writes a benefit illustration by policy year. The Python entry
  points are `avk.api.ul_compliance`, `ul_residual_additions` and `ul_illustration`.
  Residual additions are not yet a cashflow of the projection.
- Value UNIT_LINKED business on reserving, best-estimate and market-consistent
  bases: units in five fund slots with active, discontinued (DPF) and reduced
  paid-up states, charges, additions and guarantees. The general fund carries
  commission, expenses and interest. The general fund reserve has its zero and
  mortality-charge floors and a revival provision. The best-estimate profit
  signature has unit and non-unit segments. Solvency capital and MCEV (PVFP,
  frictional cost, CRNHR, VIF, BEL) complete the valuation. Add the final
  UNIT_LINKED output schema and saved 10,000-policy valuation results.
- `python -m avk.testing.demo --products` captures saved results for chosen products.
- Let a product factory name companion policy tables that the run reads once,
  validates and gives to the model-point adapter; existing products declare none.
- Allow a 1e-10 percentage-point floor in parity checks for percentage-change rate columns.
- Document Windows long paths and check that repository file paths stay within 140 characters.

## 0.1.0

- Value five life insurance product families: term life, accidental death
  rider, critical illness rider, disability rider, and credit life.
- Run base valuations, what-if cases, stress capital, and IFRS 17 General
  Measurement Model (GMM) measurement and roll-forward.
- Validate books with `avk check`, project them with `avk run`, and generate
  invented examples with `avk demo generate`. The Python API is under `avk.api`.
- Read CSV and Parquet policy books and extend the available assumption-table
  formats with Python entry points. Run records, status and logs accompany
  the projection output.
- Use Python 3.13 or 3.14 on [Windows](docs/WINDOWS.md) or [Linux](docs/LINUX.md).
  Review the [known output conventions](docs/output-conventions.md) for timing,
  cashflow signs, reserves and ratios before using the results.
