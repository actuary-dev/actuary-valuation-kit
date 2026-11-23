# Contributing to Actuary Valuation Kit

Use Python 3.13 or 3.14 and uv 0.12.19 or newer. Install from the project root
using the [Linux guide](docs/LINUX.md) or [Windows guide](docs/WINDOWS.md).

For an issue, describe the product, run type, expected result and observed
result. Include the command and a small invented example that reproduces the
issue. Use `avk demo generate` to create inputs. Keep actual policy books and
assumption tables out of issues, changes and attachments.

For a change, write a failing product-level check using `avk check`, `avk run`
or `avk compile`, then make it pass. State which product and run types you
verified. If numbers are affected, show the first stage that differs and
give a worked example. Maintainers review saved-result changes and their
explanation before accepting them. See [output conventions](docs/output-conventions.md)
and the [saved demo guide](docs/developer/saved-demo.md).

Run the [project checks](CLAUDE.md#checks) and include their results when you
submit your change. Regenerate reference pages with
`uv run python scripts/generate_reference.py` when a documented contract changes.
The default suite and installed-wheel check run on Linux and Windows.
