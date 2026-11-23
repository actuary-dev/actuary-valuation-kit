# Build your own term product
Start in the project root after the [Linux](../LINUX.md) or
[Windows](../WINDOWS.md) installation. This tutorial uses one invented policy;
you need only know Python imports, classes and multiplication.
All paths below are relative to that directory.

## 1. Read the product
Open [formulas.py](package/src/tutorial_products/formulas.py).
First, `LevelTermBenefit` is our own formula component: sum assured times expected
deaths after the valuation instant. With cover 1,000, the first future month's
expected benefit is **1.00554254**. Its `REQUIRES` names the deaths column supplied by the shared
lives component.
Then `MyTerm` joins our component to the tested `Term` composition, gives it a
new code, and explicitly overrides the death-benefit port to read our column.
That composition joins monthly mortality/lapse rates, surviving lives, premiums,
expenses, reinsurance, reserves and present values. It evaluates two bases:
`reserving` applies prudent margins; `be` uses best estimates.
Reusing components keeps their timing and validation rules.

## 2. Connect the input tables and factory
Open [factory.py](package/src/tutorial_products/factory.py).
`MyTermFactory` selects that composition. The inherited factory supplies the
policy adapter, validator, required assumptions and ordered output schema.
Its parameter column remains `TERM` and its policy table remains `policies_term`:
we intentionally reuse the public Term input contract.

Open [pyproject.toml](package/pyproject.toml). The `avk.products` entry point
makes the factory discoverable. A distinct product code avoids collisions.
A normal extension package is installed with `uv pip install docs/tutorials/package`.
For this exercise the runner installs it into a disposable folder and adds that
folder to Python's search path, leaving your environment unchanged.

## 3. Run it

The generated run file declares its table list in `Inputs.Tables`.

Linux/macOS shell:

```sh
uv run python docs/tutorials/term.py /tmp/avk-term-tutorial
```

PowerShell:

```powershell
uv run python docs/tutorials/term.py "$HOME/avk-work/tutorial-term"
```

[term.py](term.py) and [worked.py](worked.py) are the complete executable steps.
They generate a public basis, then write one policy: start 1 December 2025,
valuation 31 December 2025, two-year term, two-year payment term, annual premium
100, sum assured 1,000, entry age 35, male non-smoker. Annual mortality is
**0.012** at every age and for every sex. Reinsurance mortality and lapses
remain zero to keep the arithmetic visible. Other expenses and interest remain
the invented demo assumptions; this is not a pricing basis.

## 4. Read the numbers and regression
The first premium belongs to the period before valuation. Step 0 has no premium.
Only the premium at policy month 13 remains, at projection step 12.
On the best-estimate basis, the engine converts annual mortality by taking the
twelfth root of annual survival, then subtracting it from one:
`q = 1 - (1 - 0.012) ** (1 / 12) = 0.001005542539128`.
This preserves annual survival; it does not simply divide annual mortality by 12.

Start with one life. First future month (step 1) expected deaths are
**1 x q = 0.001005542539128**, expected death benefit is
**1,000 x q = 1.00554254**, and closing lives are **0.998994457461**.
Duration at valuation is one month, so 23 covered months remain, including the
maturity month. Total future death benefit is
**1,000 x [1 - (1 - q)^23] = 22.87345770**.
The premium is paid on opening lives at step 12, after 11 mortality decrements:
**100 x (1 - q)^11 = 98.89944760**.

The runner constructs these expectations independently from the stated rate,
cover and duration, and checks first-month deaths, benefit and closing lives,
plus total premiums and benefits, using the central tolerance policy.
Reserving mortality additionally carries the demo prudent margin.
It calls `check`, `compile` and `run`, then compares every aggregate column
against a complete built-in Term run using the central tolerance policy.
Guard 2 also removes the sum assured from a disposable copy of the formula and
requires the complete comparison to fail, proving it detects a benefit error.
Expected final line: `PASS: own Term factory matches every built-in aggregate column`.

Both JSON run files, inputs and output folders remain in your chosen folder.
Read `my-term.json` to see the selected code and assumptions.
The aggregate CSV is in `my-term`; `run_record.json` records its provenance.
To run the automatic product guard:

```sh
uv run pytest -q tests/regression/test_tutorials.py -k tutorial_product
```

Continue to [return of premium](return_of_premium.md).
