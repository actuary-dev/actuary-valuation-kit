# UL P4a: scenario tooling — implementation plan

> **For agentic workers:** implement this plan task by task, test first, inline (no
> sub-agents). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A seeded multi-asset stochastic scenario generator, generator settings in the
scenario registry, a command that writes scenario sets in the existing supplied Parquet
format, and a deterministic scenario library (flat illustration rates, shifts, one-off
shocks, custom paths). Product-agnostic: tested with TERM and synthetic variables now,
used by UNIT_LINKED later.

**Architecture:** Generators live in `avk.esg` and produce `avk.model.data.ScenarioSet`.
`MultiAssetLognormalESG` starts from the same deterministic monthly paths as
`DeterministicCurveESG` (same curve, column and timing rules) and adds correlated
lognormal noise to the variables marked stochastic. A run file selects it with
`Inputs: Scenarios: {Source: generator, Generator: MultiAssetLognormalESG, Settings: {...}}`.
`avk scenarios generate` and `avk scenarios library` write Parquet files that
`SuppliedScenarios` reads back unchanged.

**Tech stack:** Python 3.13, numpy, polars, pytest, uv.

**Spec:** `docs/superpowers/specs/2026-11-26-unit-linked-product-design.md` sections 5.4
and 5.13.

## Global constraints

- Run every project check in `CLAUDE.md` (from the worktree root) before declaring done.
- Existing saved results stay byte-identical; the deterministic generator's output is unchanged bit for bit.
- Import-linter: `avk.esg` must not import products, outputs, runs, api, cli, ui, testing. CLI glue lives in `avk.cli` / `avk.runs`.
- float64 throughout; no fastmath; numpy `Generator(PCG64)` via `SeedSequence`.
- No hidden defaults: every setting is required unless this plan names a default.
- Commit locally after each green task on branch `ul/p4a-scenarios`; never push; keep `docs/superpowers/plans/ul-p4a-log.md` current (done, decisions, next step).

## Review focus

1. Scenario i must be identical whether 10 or 10,000 scenarios are generated (prefix stability). Test in Task 2.
2. A correlation matrix that is not positive semidefinite, or misses a stochastic variable → clear error before generation. Test in Task 1.
3. Antithetic pairs with an odd scenario count → error. Test in Task 2.
4. A Parquet file written by `avk scenarios generate` and read by `SuppliedScenarios` gives arrays equal bit for bit. Test in Task 4.
5. Under `risk_neutral`, the average discounted asset index stays at 1 within Monte Carlo error. Test in Task 2.

---

## Interfaces

```python
# src/avk/esg/multi_asset.py
@dataclass(frozen=True)
class AssetModel:
    variable: str          # a declared scenario variable name, e.g. "ret_eq_large"
    volatility: float      # annual, >= 0
@dataclass(frozen=True)
class MultiAssetSettings:
    scenarios: int                     # >= 1
    seed: int                          # >= 0
    measure: Literal["real_world", "risk_neutral"]
    assets: tuple[AssetModel, ...]     # the stochastic variables; others stay deterministic
    correlation: npt.NDArray[np.float64]  # (n, n) in assets order
    risk_free: str | None              # variable whose monthly rate is the drift under risk_neutral
    antithetic: bool
class MultiAssetLognormalESG(EconomicScenarioGenerator):
    SETTINGS = frozenset({"Scenarios", "Seed", "Measure", "Assets", "Correlations", "Risk_Free", "Antithetic"})
    def __init__(self, variables: Sequence[ScenarioVariable], settings: Mapping[str, Any], *, base: Path | None) -> None: ...
    def generate(self, curves: Mapping[str, InterestCurveAssumption], horizon: int) -> ScenarioSet: ...

# src/avk/esg/library.py  (pure functions on ScenarioSet)
def flat(base: ScenarioSet, variables: Sequence[str], annual: float) -> ScenarioSet
def shift(base: ScenarioSet, variables: Sequence[str], annual_change: float) -> ScenarioSet
def shock(base: ScenarioSet, variables: Sequence[str], month: int, factor: float) -> ScenarioSet
def custom(base: ScenarioSet, path: Path) -> ScenarioSet   # CSV Month,<variable>... monthly effective
def write_parquet(scenarios: ScenarioSet, path: Path) -> Path   # the SuppliedScenarios layout
```

Settings, as written in a run file:

- `Scenarios` (int), `Seed` (int), `Measure` (`real_world` | `risk_neutral`).
- `Assets`: path (relative to the run file) to a CSV `variable,volatility`.
- `Correlations`: path to a CSV in the existing `avk_correlations_v1` layout
  (`risk,other,value`), with `risk`/`other` naming asset variables; read through the
  existing reader so its square, symmetric, unit-diagonal, PSD rules apply.
- `Risk_Free`: required when `Measure` is `risk_neutral`, forbidden otherwise.
- `Antithetic`: optional, default false (the one named default).

Model, per stochastic variable `v` and month `t >= 1` (month 0 and any month the
deterministic placement sets to zero stay as the deterministic path):

```
mu_m(t)  = deterministic monthly rate of v           (real_world)
         = deterministic monthly rate of Risk_Free   (risk_neutral)
sigma_m  = volatility / sqrt(12)
r_v(t)   = exp(log(1 + mu_m(t)) - sigma_m**2 / 2 + sigma_m * Z_v(t)) - 1
Z(t)     = L @ e(t),  L = cholesky(correlation) (use an eigen-decomposition fallback for PSD-singular)
```

so `E[1 + r_v(t)] = 1 + mu_m(t)` exactly. Each scenario `s` draws from its own child
`SeedSequence(seed).spawn(...)[s]` (antithetic: pair `2j, 2j+1` share draws `e, -e`),
which gives prefix stability. `ScenarioSet.ids` are `"1".."S"`, weights `1/S`, `seeds`
the per-scenario entropy integers, `measure` the setting, provenance records the
generator, version, settings, and the sha256 of each settings file.

---

### Task 1: Settings and validation

**Files:** create `src/avk/esg/multi_asset.py` (settings part); test `tests/esg/test_multi_asset_settings.py`.

- [ ] Write tests: valid settings parse; unknown setting key, missing `Scenarios`/`Seed`/`Measure`, `Scenarios < 1`, negative seed, unknown `Measure`, an asset variable not declared by the product, a duplicate asset, negative volatility, a correlation file missing an asset or not PSD, `Risk_Free` missing under risk_neutral or present under real_world, `Risk_Free` naming an undeclared variable — each raises `InputError` with a message naming the setting.
- [ ] Run `uv run pytest tests/esg -q`: fails. Implement `MultiAssetSettings.parse(settings, variables, base)`. Run: passes. Commit `feat(esg): multi-asset generator settings`.

### Task 2: Generator

**Files:** extend `multi_asset.py`; test `tests/esg/test_multi_asset.py`.

- [ ] Write tests (synthetic curves built in the test; horizon 120):
  - deterministic variables equal `DeterministicCurveESG` output exactly for every scenario;
  - with every volatility 0 the stochastic variables equal the deterministic paths to 1e-15;
  - prefix stability: scenario 7 of a 10-scenario set equals scenario 7 of a 200-scenario set exactly;
  - same seed, same set (bit for bit); different seed, different set;
  - 20,000 scenarios: sample mean of `1 + r` per month within 4 standard errors of `1 + mu_m`; sample correlation of `log(1 + r)` across two assets within 0.02 of the input;
  - risk_neutral: mean over scenarios of `prod(1 + r_v) / prod(1 + r_rf)` at month 120 within 4 standard errors of 1;
  - antithetic: draws pair exactly; odd `Scenarios` with antithetic raises;
  - output: `ScenarioSet` shape `(S, horizon)`, ids, weights, seeds length `S`, measure.
- [ ] Run: fails. Implement `generate`. Run: passes. Commit `feat(esg): multi-asset lognormal generator`.

### Task 3: Registry with settings

**Files:** modify `src/avk/esg/registry.py` (and the call sites that pass `base`); test `tests/esg/test_registry.py`.

**Interfaces:** each registered generator class declares `SETTINGS: frozenset[str]`; `generator_for` accepts `Settings` for generators whose `SETTINGS` is non-empty, rejects unknown keys, and constructs `cls(variables, settings, base=base)`; `DeterministicCurveESG` keeps `SETTINGS = frozenset()` and its current behaviour (rejecting any Settings).

- [ ] Write tests: `DeterministicCurveESG` with Settings still raises the existing message; `MultiAssetLognormalESG` is selected by name with settings; unknown generator name raises the existing message.
- [ ] Write an end-to-end test: generate a TERM demo (`avk.demo.generate.generate(tmp, "TERM", 50, 209)`), add `Inputs.Scenarios` selecting the generator with 4 scenarios over `roi` as the stochastic variable (Assets CSV with volatility 0.02, a 1x1 correlation file), run the Valuation: the aggregate file has a leading `Scenario` column with 4 values; with volatility 0 every scenario's rows equal the deterministic run's rows (parity).
- [ ] Run: fails. Implement. Run: passes, plus `uv run pytest tests/regression/test_demo_suite.py -q` unchanged. Commit `feat(esg): generator settings in run files`.

### Task 4: Scenario files and the deterministic library

**Files:** create `src/avk/esg/library.py`; modify `src/avk/cli.py` and add `src/avk/runs/scenarios.py` (the run-layer function that loads a run file's product, its declared scenario variables and curves, builds the generator and writes Parquet); test `tests/esg/test_library.py`, `tests/esg/test_scenarios_cli.py`.

**Interfaces:**

```
avk scenarios generate RUN_FILE OUTPUT.parquet
    # uses the run file's Inputs.Scenarios generator (default: deterministic)
avk scenarios library RUN_FILE LIBRARY.json OUTPUT_FOLDER
    # LIBRARY.json: [{"Name": "illustration_8", "Operations": [{"Op": "flat", "Variables": [...], "Annual": 0.08}]}, ...]
    # ops: flat, shift (Annual_Change), shock (Month, Factor), custom (Path); applied in order
    # writes OUTPUT_FOLDER/<Name>.parquet, one file per entry, each one scenario (Seed 0)
```

`flat` sets the variable to `(1 + annual)^(1/12) - 1` from month 1; `shift` converts each
month to annual `(1 + r)^12 - 1`, adds `annual_change`, converts back (error if the result
is <= -1); `shock` sets `r(month) = (1 + r(month)) * factor - 1` (factor 0.7 is a 30% fall);
`custom` replaces listed variables with a CSV `Month,<variable>...` covering months 0 to
horizon - 1. Months the deterministic placement holds at zero stay zero for `flat` and
`shift`.

- [ ] Write tests: each operation's exact values on a synthetic set; operations compose in order; invalid op, unknown variable, month out of range, custom file with missing months → `InputError`; `write_parquet` then `SuppliedScenarios(...).generate(...)` returns identical arrays, ids and seeds (review-focus 4); the CLI `generate` on the TERM demo writes a file that a Valuation with `Scenarios: {Source: parquet, Path: ..., Settings: {Measure: real_world}}` runs; the CLI `library` writes one file per entry.
- [ ] Run: fails. Implement. Run: passes. Commit `feat(scenarios): scenario files and deterministic library`.

### Task 5: Documentation and checks

**Files:** create `docs/scenarios.md` (generator model and formulas, settings, file layout, library operations, a worked TERM example, notes for unit-linked asset variables `ret_*` from the design); link it from `docs/how-tos.md` or `README.md`; `CHANGELOG.md`; regenerate `docs/reference` if the run-file reference covers Scenarios.

- [ ] Write docs. Run `uv run python scripts/generate_reference.py --check` and `uv run pytest tests/regression/test_documentation.py -q`.
- [ ] Run every project check in `CLAUDE.md`; record the summary in `ul-p4a-log.md`. Commit `docs(scenarios): stochastic and deterministic scenario tooling`.

## Done when

All tasks committed on `ul/p4a-scenarios`, every project check passes, saved results are
unchanged, and `ul-p4a-log.md` records decisions and open points.
