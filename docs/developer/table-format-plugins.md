# Table-format readers

An installed Python package can provide a table reader through the `avk.formats`
entry-point group. A run selects it with the input location's `Format` setting.
The hook changes input parsing; it does not change product formulas or supply assumptions.

In the reader package's `pyproject.toml`:

```toml
[project.entry-points."avk.formats"]
example_mortality = "example_formats:mortality"
```

In a run file:

```yaml
Inputs:
  Tables: tables.csv
  Replace:
    mortality:
      Path: my_mortality.csv
      Format: example_mortality
```

Install the reader package into the same Python environment as Actuary Valuation Kit. Restart the
process after installing or removing a package: discovery is cached per process.
Only a selected entry point is imported. Unselected packages with broken imports do
not prevent unrelated runs. Names are case-sensitive. A selected name provided by
more than one entry point, or shared with a built-in reader, is rejected rather than
chosen by installation order. In-process `register` readers use the same namespace.

The entry point must resolve to a callable:

```python
def mortality(frame: pl.DataFrame, spec: FormatSpec) -> Table: ...
```

`FormatSpec` is imported from `avk.inputs.formats`; `Table` and `Axis` are
imported from `avk.model.data`. The specification supplies:

| Field | Meaning |
|---|---|
| `name` | Logical table name, used in error messages |
| `source` | Source metadata, including logical name and content hash |
| `axes` | Required lookup rules declared by the product |
| `columns` | Required value fields, in the product's declared order |
| `product` | Product requesting the table |
| `projection_months` | Required projection length |
| `units` | Probability, fraction, amount, annual effective rate or mixed |

The reader validates keys, completeness, shape and source values before returning
`Table(spec.name, axes, values, spec.source)`. Values are a finite float64 NumPy
array; axes describe its dimensions and must preserve the product's declared lookup
rules. No missing value becomes zero unless the format explicitly documents it.
Probability units mean fractions in [0, 1], not percentages. Annual effective
interest rates must exceed -1. Preserve all source values during reordering.

Readers can use `numeric`, `unique`, `numeric_keys`, `integer_axis`, `key_axis` and
`table` from `avk.inputs.formats`. These helpers validate or build payloads;
readers must still enforce their format's keys, coverage and dimension rules.

Raise `InputError` for invalid source data, naming the logical table and offending
key or row. Value, type, key and Polars parsing errors receive the table name at the
reader boundary. A missing module, non-callable entry point or non-`Table` result
is reported as an `InputError`. Exceptions representing reader programming bugs can
still propagate. Assumption classes apply their normal validation after reading.

A format extension should be verified with a complete `avk check` and
`avk run`. An equivalent layout should produce identical output CSV files.
The product-level example in `tests/regression/test_format_plugins.py` discovers
actual temporary package metadata, runs Term with an alternative mortality layout,
and checks every output CSV byte for byte. It also exercises invalid inputs and
ambiguous registrations, without installing packages into the user's environment.
