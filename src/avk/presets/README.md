# Solvency II-style protection presets

Use `solvency_ii_life.yaml` for Term/credit life, or `solvency_ii_riders.yaml`
when the run includes riders. Set `Stress_Set` to the chosen file's path in the
run configuration. The supplied windows require at least a two-year projection.
All calibrations are explicit inputs; edit a copy to choose a different basis.

The reference is **Regulation (EU) 2015/35 as enacted (17 January 2015)**,
[official identifier](https://eur-lex.europa.eu/eli/reg_del/2015/35/oj),
[primary regulation text, mirrored PDF](https://www.dlapiperintelligence.com/export/sites/intelligence-old/investmentrules/blog/articles/2018/downloads/CELEX_32015R0035_EN_TXT.pdf).
This is a reproducible historical illustration, not a claim about current requirements.

| Input | Article | Calibration |
|---|---|---|
| Mortality | 137(1) | Multiply by 1.15 |
| Incidence | 139(a), (b) | Multiply by 1.35 months 1–12, then 1.25 |
| Expenses/inflation | 140(a), (b) | Multiply expenses by 1.10; add 0.01 inflation |
| Lapse up/down | 142(2), (3) | Multiply by 1.5/0.5; cap decrease at 0.20 |
| Ordinary-policy mass lapse | 142(6)(b) | 0.40 |
| Mortality catastrophe | 143(1) | Add 0.0015 in months 1–12 |
| Correlations | 136(3) | Labelled submatrix in each YAML; every included cell verified |
| Annual cost rate | 39 | 0.06 as enacted |

The EIOPA rulebook independently reproduces
[incidence](https://www.eiopa.europa.eu/rulebook/solvency-ii-single-rulebook/article-5759_en?prefLang=de),
[lapse](https://www.eiopa.europa.eu/rulebook/solvency-ii-single-rulebook/article-5762_en),
[expense](https://www.eiopa.europa.eu/rulebook/solvency-ii-single-rulebook/article-5760_en?prefLang=mt)
and [catastrophe](https://www.eiopa.europa.eu/rulebook/solvency-ii-single-rulebook/article-5763_en).

The presets omit longevity, revision and
Article 139(c)'s recovery-rate shock (these products expose incidence rather than
a recovery-rate assumption). It does not implement the special pension mass-lapse
70% case in Article 142(6)(a), future-business reinsurance, management actions,
loss-absorbing adjustments, or the full standard-formula SCR. The generic monthly
capital and cost measure retains Actuary Valuation Kit's existing BEL/in-force conventions,
and its chosen `reference_forward` demonstration curve is not a regulatory risk-free curve.
Commissions remain unshocked under the carried product convention.

The preset's `life catastrophe` is a windowed mortality **revaluation**.
The reserved `catastrophe` label still means the clean immediate own-benefit
measure in STRESS.md, including CI/TPD rider cover. The two methods have different
purposes; neither silently replaces the other. Mass lapse retains the clean
surrender-value measure. The lapse alternatives reduce once to their per-policy
maximum before correlation. Optional floor, operational charges and cost loading
are absent and therefore off. Regulatory operational-risk formulas are not supplied.
