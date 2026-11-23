# Developer reference
This page maps the interfaces available to extension authors.

| Boundary | Contract |
|---|---|
| `avk.api` | `check`, `preflight`, `compile`, `run`, `RunConfig`, errors and `version` |
| `avk.model.lang` | `Component`, `Product`, family ports, bindings, `prev`/`nxt`, `if_`, `at_basis`, `override` |
| `avk.products.registry.ProductFactory` | definition, assumption spec, adapter, validator, output schema, aggregate ratios |
| `avk.inputs` | source locations, policy loading/preparation and format hooks |
| `avk.assumptions` | strict typed assumptions, scenario-variable declarations and parameter loading |
| `avk.outputs.schema.OutputSchema` | ordered entries, keys and seriatim slices |
| `avk.runtime.progress` | callbacks/status contract; optional for library callers |
| `avk.testing.parity` | saved-result comparisons and the single numerical tolerance policy |

`run(config, *, root=None, progress=None, diagnostics=None, output=None)` returns
`RunResult`: run type, files, kernel identities, timings, notes and cache hits.
`check` returns a validated report or raises a checked error.
`compile(codes=(), *, device="cpu", explain=False, listing=False)` accepts registered
codes or a source file for compilation. Running a new code requires an installed
`avk.products` factory entry point. See [the Term tutorial](../tutorials/term.md).

Formula modules import the authoring language and other formulas only. A formula
has a docstring and one return expression. Use `if_` rather than Python conditional
expressions; lagged/future columns use declared recursion. Component requirements
are explicit; two competing owners need an override on a class derived from both.
Factories select compositions; product-option branching does not belong in kernels.
The core imports no configuration/I/O/product layer. Enforce this with
`uv run lint-imports`; kernels use float64 and no fastmath.

A factory's assumption spec must cover exactly the tables/curves and scenario
variables bound by the composition. The policy adapter prepares arrays in batches;
the validator rejects invalid inputs before projection. No hidden parameter default,
per-policy Pydantic instance or per-policy preparation loop is allowed.
See [table-format plug-ins](table-format-plugins.md) and
[the runnable plug-in tutorial](../tutorials/table_format.md).

Schema changes require regenerating the reference and reviewing the diff:

```sh
uv run python scripts/generate_reference.py
uv run python scripts/generate_reference.py --check
uv run pytest -q tests/regression/test_documentation.py
```

The generator reads Pydantic run/input schemas, the public format registry, product
output schemas and public reporting-table headers. Dynamic stress risk names and
custom plug-in outputs depend on the run and cannot be exhaustively enumerated.
All complete-product regression comparisons use `avk.testing.parity`.
Logical reduction blocks preserve batch/thread reproducibility; writers format
results without calculating new actuarial quantities. See the [audit record](../audit-trail.md)
for provenance and failed-run diagnostics.
