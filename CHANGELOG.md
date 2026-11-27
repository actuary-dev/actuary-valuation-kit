# Changelog

## Unreleased

- Generate correlated lognormal economic scenarios in valuation runs. Export them
  to supplied-scenario Parquet or build deterministic paths with `avk scenarios`.
- Add the UNIT_LINKED input contract: policy table `policies_ul`, fund holdings
  companion table `policy_funds_ul`, fund universe, variant, charge-scale and
  regulatory-cap tables with formats `avk_ul_keyed_v1` and `avk_ul_year_key_v1`,
  validation before projection, model points in five fund slots, a skeleton
  Valuation product reporting opening funds, and an invented demo book.
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
