# Changelog

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
