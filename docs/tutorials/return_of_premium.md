# Add return of premium
Complete [the Term tutorial](term.md) first. This feature reuses the same product
and adds a formula component in the tutorial package, without editing the engine.
It refunds the contractual annual premiums to a policy surviving to maturity.
There is no surrender refund, interest on refunded premiums or premium waiver;
all premiums are assumed paid. This example is for annual premiums only.

1. Open [formulas.py](package/src/tutorial_products/formulas.py).
   `ReturnOfPremium` declares the existing columns it needs.
   `returned_premiums` multiplies annual premium, payment years and maturing lives.
   A formula is a docstring followed by a single return expression.
2. `ReturnTerm` joins the new component with `MyTerm`. Its `@override` explicitly
   replaces `benefit_outgo` on the class derived from both components. This includes
   the refund in the existing cashflow/reserve chain; class order alone cannot
   silently choose a replacement.
3. In [factory.py](package/src/tutorial_products/factory.py), `ReturnFactory`
   selects the new composition and adds `returned_premiums_BE` to the output.
   All inherited preparation and validation still apply.
4. Run from the project root:

```sh
uv run python docs/tutorials/return_of_premium.py /tmp/avk-rop-tutorial
```

PowerShell:

```powershell
uv run python docs/tutorials/return_of_premium.py "$HOME/avk-work/tutorial-rop"
```

This example explicitly switches mortality off, unlike the Term tutorial,
so the refund arithmetic stays visible. It retains zero reinsurance mortality
and lapses. The same one-policy book therefore has zero deaths and lapses. Policy month 24 is step 23:
duration at step 0 is 1. The one surviving policy receives **100 x 2 x 1 = 200.00**.
Total refunded premiums are **200.00**, future collected premiums **100.00**,
death benefits **0.00**, step 1 closing lives **1.00**.
The runner checks the maturity row and total refund independently.
It also compares a complete plain-Term run: gross reserving net outgo increases
by exactly **200.00** at step 23, with every other step unchanged. The comparison
uses the central numerical tolerance policy.
Expected last line: `PASS: maturity at step 23; returned premiums = 100 x 2 x 1 = 200.00`.
Expenses and interest still affect reserves; the refund is an outgo in both bases.
This exercise covers Valuation; it does not define a new IFRS accounting contract.
