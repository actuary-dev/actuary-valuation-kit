# Invented demo basis and books

These examples are invented teaching inputs, without experience calibration or
currency-specific meaning. The generator uses the formulas below and reads the
packaged stress presets. The same seed and product give identical books.

Run from the project folder:
uv run python -m avk.demo.generate /tmp/demo-term --product TERM --count 10000 --seed 209

PowerShell, after the environment setup in the [README](../../../README.md):

```powershell
uv run python -m avk.demo.generate "$HOME\avk-work\demo-term" --product TERM --count 10000 --seed 209
```

Counts 10000, 100000 and 1000000 are supported for each of the five product codes.
Only small basis tables and source code belong in version control. Books, raw results,
run manifests and kernel caches belong outside the repository.

## Rates and expenses

Annual mortality q(x) = min(0.7, 0.00012 + 0.00035 exp(0.075(x-35))).
Female factor 0.82; third mortality field factor 0.91. Ages 0 through 120.
Reinsurance mortality uses this same invented formula. Term smoker loadings are
1.0 and 1.3; Credit Life loadings are 1.0/1.3 (male) and 0.82/1.066 (female).
The Credit Life flat-rate option is 0.0018 BE and 0.0021 reserving.

Annual morbidity at age x is min(0.4, b exp(s(x-35))) times a sex factor
(male 1, female 0.9): accidental death b=0.00028,s=0.008;
critical illness b=0.0011,s=0.045; disability b=0.00065,s=0.035.
No waiting or recovery experience is implied.

Lapse is 6.5% in year 1, 4.5% in years 2-3, 2.5% thereafter; channel 1
adds 0.5 percentage points. Commission is 10% in year 1 and 2.5% thereafter;
channel 1 adds 0.5 points. Schedules explicitly cover 32 years.

Initial expense is 85 currency units plus 4% of premium plus 0.015% of cover;
the fixed amount is 34 for riders. Knots are 0 and 500000. Annual maintenance is
24 (9.6 for riders) plus 1.5% of premium; claim expense is 0.75%.
IFRS schedules use these invented renewal values. Inflation is 2.5%.

Annual curves are flat: investment 4%, reserving 3.2%, reference 3.8%,
IFRS current 3.7%, locked-in 3.5%, IFRS reference 3.8%.
Calendar cohort curves use (1.035 ** (1/12))-1 from 2023 through 2057.
All product parameter values are explicit in PARAMETERS in generate.py and
product_parameters.csv; none are filled by readers. Prudent mortality/morbidity/
expense margins are 12%/15%/10%, lapse margin -10%; tax 20%.
Profit transfer is 1.5% of pre-tax profit to an invented contingency reserve.
Capital factors are 3.5% of reserves and 0.2% of sum at risk, target ratio 150%,
with 50% reinsurance credit floors. Retention is 60000 and proportion 75%.
IFRS initial/renewal/commission multipliers are 1; additions and stress inflation
are zero. The IFRS expense stress multiplier is 1.1 (zero would remove the
stressed costs rather than specify a neutral stress). IFRS RA ratio is 8%; held RA ratio is -5%.

Term and riders set both lapses_after_payment_term and
renewal_premium_expense_after_payment_term false. Credit Life sets both true:
loans may close early despite single premium; the premium-expense switch has no
effect for Credit Life.

## Book construction and dates

Eight independent NumPy random streams are derived from SeedSequence([seed,
product_index]); each property is prefix-stable across the three book sizes.
Entry ages are integers 24-56; Term/rider terms 10-30 years, loans 5-20 years; cover is 80000, 140000 or 240000;
sex is equiprobable; 20% smokers; channels 0/1 are equiprobable.
Issue dates are equiprobable: 2023-03-01, 2024-09-01, 2025-02-01,
2025-10-01 and 2026-02-01, including new business at each reporting date.
Regular-premium payment terms cycle through full-term, 5, 10 and 20 years,
capped at the contract term; shorter options visibly exercise paid-up switches.
Annual premium is cover times 0.6% Term, 0.15% accidental death, 0.4% critical
illness or 0.3% disability, multiplied by term/payment-term for limited pay. An independent 20% subset pays 12% of those rates,
providing intentionally onerous examples. IDs are neutral DEMO sequence numbers.

Credit Life has reducing cover, 6% annual loan interest, monthly amortising
payments from the standard annuity equation, no moratorium and single premium
0.3% of original loan times loan term (0.02% times term for the low-premium subset). There are no
reconstructed historical cashflows.

Opening date is 2025-12-31; closing date is 2026-06-30. Projection is 31 years (372 months),
covering the longest contract including future new business. The full seeded
book is used for opening valuation/measurement and cases/capital. Opening
roll-forward excludes future issues; closing excludes contracts already matured.
Existing group keys and IDs carry unchanged. Opening CSM is an explicit
illustrative 60000 per non-onerous group; direct loss 15000 per onerous group;
all held balances zero. These are invented balances, not saved model results.

The stress set converts the packaged presets in avk.presets/solvency_ii_life.yaml
and avk.presets/solvency_ii_riders.yaml to public CSV format without recalibration.
See avk.presets/README.md for article citations (Regulation (EU) 2015/35 as enacted).
Mortality +15%; lapse +/-50% (down capped at 20 points), mass lapse 40%;
expense +10% and inflation +1 point; catastrophe +0.15 mortality points in
months 1-12. Rider morbidity is +35% in months 1-12 and +25% thereafter.
The labelled life-module correlation submatrix is copied exactly from each
preset: mortality/lapse and morbidity/lapse are zero; other off-diagonals are
0.25 or 0.5. Cost of capital is 6%, on reference_forward. Optional operational
risk, loading and diversification floor are off. The separate Valuation capital
charge parameter remains an invented 5.5%. Article citations are retained
in stress-source.yaml alongside generated tables. This historical protection
subset is not a claim of full or current regulatory compliance.

## Output conventions

Positive IFRS BEL means a liability; the valuation MCEV BEL has the opposite
cashflow sign. Capital, RA, CSM and direct loss are nonnegative. Reinsurance RA
may be negative. Blank aggregate per-policy ratios after all eligible lives
expire, and blank percentage changes against a zero base, are intentional.
Reserve amounts and cashflows run off to zero. The public regression captures
aggregates and reporting tables at 10k/100k; see docs/developer/saved-demo.md.
The 372-month horizon includes policies that start after the valuation date.

The public demo uses physical Batch_Size 8192. Deterministic logical reduction
blocks remain 1024 policies; a 100k byte check covers batches 1024/8192 and
threads 1/4. Batch size is execution layout, not an actuarial assumption.

## Reference laptop timing

On idle mains power, the seed-209 100k Term book (372 months, batch 8192,
16 threads) recorded a 3.715-second best warm elapsed time, 9.366-second cold
compile and 0.525-second warm fixed overhead. The normal guard subsequently
passed at 3.630 seconds warm. The warm limit is 4.644 seconds (125% of the
recorded baseline); compile and fixed-overhead limits remain 30 and 1 seconds.
These are measurements on the reference WSL laptop, not a hardware-independent
performance promise. See tests/perf/demo_baseline_wsl_laptop.json.
