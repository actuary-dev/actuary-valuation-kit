# Unit-linked build: worker prompts and review checklist

Each worker gets the common preamble plus its phase prompt. A resumed worker also gets:
"Resume: read `docs/superpowers/plans/ul-<phase>-log.md` and `git log` on your branch,
then continue from the first unchecked step of your plan."

## Common preamble (every worker)

You are implementing one phase of the UNIT_LINKED product in Actuary Valuation Kit (AVK),
a Python actuarial projection engine. Work only in your git worktree and on your branch.

1. Read, in order: `CLAUDE.md` (invariants and project checks), the design
   `docs/superpowers/specs/2026-11-26-unit-linked-product-design.md`, your phase plan,
   then the code your plan names. The maintainer's source specifications are in
   `C:\avkwt\_ref\` (read-only; never copy them or quote them into the repository, which
   is public).
2. Implement your plan task by task, test first. Where the plan leaves a choice, choose,
   and record the choice in `docs/superpowers/plans/ul-<phase>-log.md`.
3. After every green task: update the log (done, decisions, next step) and commit locally
   on your branch with a conventional message. Never push. Never commit to `main` or
   `feature/unit-linked`. Never rewrite published history.
4. Keep existing products' saved results byte-identical; never relax a tolerance; never
   edit `tests/saved` except where your plan says so.
5. Do not use Claude subagents (the Agent tool). Work inline. Run one test suite at a
   time and wait for it; stop any background run you no longer need. Overlapping long
   runs in one checkout have exhausted the machine's memory.
6. Before declaring the phase done, run every check in `CLAUDE.md` and paste the summary
   (pass/fail counts) into the log. If something cannot pass, stop and write why in the
   log instead of weakening the check.
7. Finish with a short report: what is done, test counts, decisions, open points.

## P1 inputs and contracts (Claude session, Opus 5.5, medium effort)

Plan: `docs/superpowers/plans/2026-11-26-ul-p1-inputs.md`. Log: `ul-p1-log.md`.
Goal: UNIT_LINKED input contracts (policy table + fund holdings companion table), new
formats, fund universe and product tables, caps, validation, preparation into fund-slot
fields, skeleton product and factory, demo inputs, documentation.

## P4a scenario tooling (Codex gpt-6.2-sol)

Plan: `docs/superpowers/plans/2026-11-26-ul-p4a-scenarios.md`. Log: `ul-p4a-log.md`.
Goal: multi-asset lognormal generator, generator settings in run files, scenario Parquet
writer and deterministic scenario library, docs. Product-agnostic; test with TERM.
Environment: set `AVK_CACHE_DIR` to `.avk-cache` inside your worktree (already excluded
from git); use `uv run` for every command.

## Later phases (plans written by the orchestrator when the phase starts)

- **P2a unit engine (Codex).** Add `UnitLinkedProduct` family ports to `avk.model.lang`;
  `scripts/generate_ul_fund_slots.py` and generated `fund_slots.py` (+ currency test);
  multi-state lives (active, DPF, RPU) and decrements (design 5.5); premiums; unit roll
  per slot in the order of design 5.6; charges; DPF and RPU aggregate funds (5.9);
  benefits and every feature of 5.7; per-basis fund returns (5.4) including the mc
  switch. Tests per feature with hand-computed one-policy cases. Reads the P1 field
  contract exactly.
- **P2b general fund and results (Claude, Opus 5.5 medium).** General fund cashflows
  (5.10), reserves and floors, profit with unit/non-unit split, solvency, MCEV (5.11),
  output schema (5.12), the independent scalar oracle and the verification checks (6),
  UNIT_LINKED saved results at 10k (maintainer approval), docs, performance record.
- **P3 compliance (Claude, Sonnet 5.5 high).** Reduction-in-yield test against
  `ul_riy_caps`, residual additions when `riy_additions_on`, the pricing-time
  demonstration at 4%/8% gross (library scenarios from P4a), benefit illustration output.
- **P4b stochastic results (Codex).** Scenario summary outputs (weighted mean,
  percentiles, CTE), TVOG for guarantees under risk-neutral sets
  (`mc_fund_return_source = 1`), dynamic lapse switch, worked tutorial.
- **P5 IFRS 17 and stress capital (Claude, Opus 5.5 medium).** VFA measurement for UL
  (entity share = expected charges, CSM with fund-value coverage units, grouping from the
  P1 IFRS fields), StressCapital support (equity, interest, lapse, expense, mortality).
- **P6 feature extensions.** Lifecycle and systematic transfer strategies, top-ups,
  premium funding benefit, highest-NAV guarantee mechanics, settlement option, pension
  variant, GST on charges. Split into separate plans when reached.

## Orchestrator review checklist (before any merge)

1. `git diff feature/unit-linked...<branch> --stat`; read every changed source file.
2. Plan coverage: every task's tests exist and assert what the plan says.
3. CLAUDE.md invariants: model independence, one owner per column, no fastmath,
   explicit inputs, no hidden defaults, import contracts.
4. Run every project check in `CLAUDE.md` in the worktree myself; confirm existing saved
   results byte-identical (`uv run pytest tests/regression/test_demo_suite.py`).
5. Spot-check numbers by hand for at least one policy where the phase computes any.
6. Merge with `git merge --no-ff` into `feature/unit-linked`, push, update the tracker.
