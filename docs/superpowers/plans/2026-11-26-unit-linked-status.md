# Unit-linked implementation: status tracker

The single source of truth for the UNIT_LINKED build. Update it after every phase
event (start, checkpoint, review, merge, stop). Design:
[unit-linked design](../specs/2026-11-26-unit-linked-product-design.md).

## How to resume (read first after any interruption)

1. `git fetch && git checkout feature/unit-linked && git pull` in the main checkout
   (`C:\Users\tusha\OneDrive\Documents\Actuary_Valuation_Kit`).
2. Read the phase table below. For a phase marked *running* or *stopped*, open its
   worktree, read `docs/superpowers/plans/ul-<phase>-log.md` and `git log` on its
   branch, then restart the worker with its prompt from
   [phase prompts](2026-11-26-unit-linked-phase-prompts.md) plus:
   "Resume: read your log and the last commit on your branch, then continue."
3. Never merge a phase branch without the review steps in the prompts file.

Reference material (outside the repository): `C:\avkwt\_ref\`.
Codex CLI: `<install folder>\app\resources\codex.exe`, model `gpt-6.2-sol`. The app
updates itself into a new versioned folder and WindowsApps cannot be listed, so
`run_codex.sh` finds the folder with `(Get-AppxPackage -Name OpenAI.Codex).InstallLocation`.

Environment facts learned:

- Under OneDrive, `uv sync` needs `UV_LINK_MODE=copy` (hardlinks fail with os error 396).
- Codex runs sandboxed (`workspace-write`); unsandboxed mode is refused by the permission
  classifier and must not be used. The Windows sandbox cannot run the user's Python,
  write the user's Temp folder, or write any `.git` directory. So each Codex phase uses a
  full clone under `C:\avkwt\<phase>` with Python (`.uvpython`), uv cache (`.uvcache`),
  kernel cache (`.avk-cache`) and temp (`.tmp`) inside it (excluded in
  `.git/info/exclude`); `run_codex.sh` sets the environment. Codex leaves changes
  uncommitted; the orchestrator reviews and commits in the clone, then fetches the
  branch into the main checkout (`git fetch C:/avkwt/<phase> <branch>:<branch>`).
- Create a Codex clone: `git clone -b feature/unit-linked <main checkout> C:/avkwt/<phase>`,
  `git checkout -b ul/<phase>-<slug>`, add the four folders to `.git/info/exclude`, then
  `uv sync --locked --extra ui --extra sql --dev` with the same environment variables as
  `run_codex.sh`.
- Claude sessions get app-managed worktrees under `.claude\worktrees\` and commit
  themselves.
- Memory: two Codex workers with overlapping long pytest runs starved the machine
  (1.3 GB free of 23.6 GB; one P5 run held 7.9 GB and ran about seven hours). Every
  worker prompt must say: run one test suite at a time, wait for it, and stop any
  background run you no longer need.
- The app refuses to start a nested session on a turn begun by a background-task event
  (for example a Codex completion). Such a turn can only propose a card, and the card
  drops `source_branch`, so the brief must check its base branch. Codex runs have no such
  limit.

## Phase table

| Phase | Status | Branch | Worktree | Worker / id | Last checkpoint | Notes |
|---|---|---|---|---|---|---|
| P0 design and tracking | merged | feature/unit-linked | main checkout | orchestrator | 021370e | design approved 2026-11-26 |
| P1 inputs and contracts | merged | claude/ul-p1-inputs-d90104 | `.claude\worktrees\ul-p1-inputs-d90104` (inside the main checkout) | Claude session `local_155c82e5-61a0-469c-8bf6-94630c380042` (ul-p1-inputs), Opus 5.5 medium | f6e11af (merge 181a503) | orchestrator fix ed0b855 (spool file handle) |
| P4a scenario tooling | merged | ul/p4a-scenarios | `C:\avkwt\p4a` (full clone) | Codex gpt-6.2-sol | b5fb061 (merge 49b4238) | orchestrator re-ran checks: 220 passed, 14 contracts |
| P2a unit engine | merged | ul/p2a-unit-engine | `C:\avkwt\p2a` (full clone) | Codex gpt-6.2-sol, effort high, prompts `C:\avkwt\prompts\p2a.md`, then `p2a-fix.md` | 7e9e045 (merge 881f4f0) | log `docs/superpowers/plans/ul-p2a-log.md` |
| P2b general fund and results | merged | claude/nostalgic-shannon-5d7738 | app worktree | Claude session `local_32b69ad7-2b4c-43cc-b350-eb0c78dfe618`, Opus 5.5 medium | acb486a (merge 2f9cbe4; fixes affdaf6) | methodology review 2026-11-28 |
| P3 compliance (RIY, illustration) | merged; general-fund wiring of residual additions waits for P2b | claude/ul-p3-compliance-c1cbcb | app worktree | Claude session `local_9a05dfb5-71ef-4db0-9ce3-440ffd29d952`, Sonnet 5.5 high | cafa52a (merge 1c3e888) | plan `2026-11-27-ul-p3-compliance.md`; log `ul-p3-log.md` |
| P4b stochastic results, part 1 | merged | ul/p4b-stochastic | `C:\avkwt\p4b` (full clone) | Codex gpt-6.2-sol | dd12ceb | TVOG wiring in the integration pass |
| P5 IFRS 17 VFA and stress capital | running | ul/p5-ifrs17 | `C:\avkwt\p5` (full clone) | Codex gpt-6.2-sol, prompt `C:\avkwt\prompts\p5.md` | — | plan `2026-11-27-ul-p5-ifrs17-stress.md` |
| P6a top-ups, fund strategies, highest NAV | merged | ul/p6a-unit-features | `C:\avkwt\p6a` (full clone) | Codex gpt-6.2-sol | 9fcd327 (merge 950f637) | switch charges integrated |
| Integration pass | running | ul/integration | `C:\avkwt\integ` (full clone) | Codex gpt-6.2-sol, prompt `C:\avkwt\prompts\integ.md` | — | residual additions, highest-NAV capital, TVOG wiring, illustration limits |
| P6b premium funding, settlement, pension | plan merged (3f0f164); build after P2b, P5 and P6a | — | — | — | — | plan `2026-11-27-ul-p6b-features.md` (9 tasks); GST and reinsurance excluded (design call 10) |

Status values: not started, running, stopped (usage limit or error), in review,
merged, blocked.

## Event log

- 2026-11-26 P0: recon done (specs, workbook, engine). Integration branch
  `feature/unit-linked` created from `main` at 775a859. Design drafted.
  Maintainer added: policy table one row per policy; fund holdings table one row
  per policy-fund; shared key fields consistent; history fields for retrospective
  calculations and IFRS 17 cohorting (design section 5.2).
- 2026-11-26 P0 merged (design approved). P4a started in Codex (clone `C:\avkwt\p4a`,
  effort high). P1 started as Claude session ul-p1-inputs (Opus 5.5 medium).
- 2026-11-26 P4a merged into feature/unit-linked (49b4238) after review; Codex report:
  all checks incl. slow suite passed; orchestrator re-ran lint/format/mypy/imports/reference/default pytest (220 passed).
- 2026-11-27 Maintainer: continue in this session; merge each reviewed phase and start the
  next without waiting for approval.
- 2026-11-27 P1 merged (181a503) after review: CHANGELOG conflict resolved (both
  entries); `check.py` auto-merged with P4a. Orchestrator re-ran ruff, format, mypy (128),
  lint-imports (14 kept), reference check and the UL, ESG and demo-suite tests (230
  passed). A scan found no text copied from the private specs. Fix ed0b855: a failed
  streamed check left the spool file open on Windows (pyarrow keeps a path-opened IPC
  file open after its block); the test now fails without the fix.
- 2026-11-27 P2b plan written (d3c8ed1). P2a started in Codex (clone `C:\avkwt\p2a`).
- 2026-11-27 P2a first pass done (Codex report: 411 default tests, 6 slow, 191 UL, all
  checks pass; 10k demo projection 2.43 s). Orchestrator committed it in the clone
  (abd6688). No copied spec text. Review decisions, sent back as `p2a-fix.md`:
  (1) a policy whose term ends in the valuation month settles at step 1 from its step-0
  balances, with no other activity (the first pass dropped INR 160.8m of unit reserve
  for 34 demo policies); (2) the DPF is released at the earlier of lock-in end and term
  end; (3) no addition when there are no allocation weights and no funds, with the
  general-fund cost also nil.
- 2026-11-27 P2a fix pass done (7e9e045; Codex: 416 default tests, 196 UL with JIT off,
  10k reconciliation and maturity clearance on all bases, 171 saved files unchanged).
  Merged into feature/unit-linked (881f4f0). Orchestrator re-ran ruff, format, mypy (135),
  lint-imports (14 kept), reference and fund-slot generator checks, and the UL and demo
  tests (245 passed). No copied spec text.
- 2026-11-27 P2b proposed as a session card (task_0be661ae). The app starts nested sessions
  only on a turn the maintainer began; on a turn started by a background-task event it
  allows only a card the maintainer clicks.
- 2026-11-27 Maintainer: start as many workers as possible. P2b started. Started in
  parallel: P3 (Claude, Sonnet 5.5 high), the P5 and P6b plan session (Claude, Opus 5.5
  medium), P4b part 1 and P6a (Codex, clones made by `C:\avkwt\setup_clone.sh`). Parallel
  workers are told to avoid P2b's files (general-fund modules, `testing/demo.py`,
  `tests/saved`, the valuation schema) and not to change existing results. Expect merge
  conflicts in `pyproject.toml`, docs and CHANGELOG. Merge order: P2b, then P6a, P4b, P3.
- 2026-11-28 P5 and P6b plans reviewed and merged (3f0f164); no copied spec text. Each
  plan ends with maintainer questions. The orchestrator takes these defaults unless the
  maintainer says otherwise:
  - P5: new UL capital, measurement and roll-forward saved modes, flagged for awareness;
    certainty-equivalent VFA now, with a TVOG adjustment possible after P4b; Legal Entity
    not in the group key; the factor-based CRNHR kept; no partial-withdrawal lapse shock;
    the teaching calibration accepted.
  - P6b: decided when P6b starts.
- 2026-11-28 P3 merged (1c3e888) after review. The session reported every CLAUDE.md check
  passing, 463 default tests (47 new), and `tests/saved` untouched; it did not run the slow
  suite. The orchestrator re-ran the static and generator checks and the UL tests, and
  reworded two doc sentences that were close to the product specification. Design note:
  `illustration.py` is a separate numpy roll of one life's units, tied to the engine by a
  reconciliation test, so later unit-engine features (P6a, P6b) must update it or state
  that it excludes them. Open: residual additions are reported but not yet in the general
  fund and the units; this follows the P2b merge.
- 2026-11-28 P6a reviewed and committed in its clone (9fcd327). Codex report: 446 default
  tests and 7 slow, 30 new tests with and without JIT, all checks pass, and the 10k demo is
  byte-identical. No copied spec text. Concerns: the cold compile rose from 75 s to 350 s
  (measured while other test suites ran; re-time after merge), and the warm projection went
  from 2.4 s to 4.1 s. Existing UL assumption packs need the new explicit off columns.
  Integration items after P2b merges:
  1. Switch charges enter `charge_income` but are in neither P2b's `charges_start` /
     `charges_end` split nor its `unit_charges_deducted`.
  2. P3's `illustration.py` excludes top-ups and strategies; document or extend it.
- 2026-11-28 P4b part 1 reviewed and committed in its clone (dd12ceb). Codex report: 460
  default tests and 7 slow, all checks pass, 171 saved files byte-identical, and the 10k UL
  outputs byte-identical with dynamic lapse off. No copied spec text. Integration item 3:
  wire `MCEV_pvfp_MC`, `MCEV_bel_MC`, `MCEV_vif_MC` and the path-discounted guarantee costs
  into the TVOG comparison.
- 2026-11-28 P2b done (session report: 495 default tests, 1 strict xfail for check 9, 9
  slow, all checks pass; 10k valuation 68 s wall, 100k 379 s). Merged LOCALLY into
  feature/unit-linked as 2f9cbe4 (CHANGELOG conflict kept both sides). NOT PUSHED: the
  combined P2b + P3 checks have not been run yet. The orchestrator stopped here at a usage
  limit. Resume steps:
  1. Run ruff, format, mypy, lint-imports, the reference and fund-slot generator checks,
     and `pytest tests/unit_linked tests/regression/test_demo_suite.py`, then push.
  2. Reword two phrases close to the spec: `docs/products/unit-linked.md` ("insurer's profit
     arises entirely in the non-unit segment", and "sum at risk is never negative and is nil
     above the floors") and the `mcev.py` docstring ("not the capital lock-up itself").
  3. Merge `ul/p6a-unit-features` (9fcd327). A trial merge was aborted. It conflicts in
     the generator (keep both total tuples: P2b's `fund_growth_total` and `rpu_growth_total`
     and P6a's `topup_close_total` and `withdrawable_total`), in `output_columns.py` (P2b's
     version plus P6a's `HIGHEST_NAV` constant), and in `factory.py` (union of imports; P6a's
     `valuation_output_schema` must iterate P2b's `LAYERS` dict instead of
     `BASIS_SUFFIXES`), plus the docs. Then regenerate `fund_slots.py`, and check that the
     UL saved results stay byte-identical.
  4. Merge `ul/p4b-stochastic` (dd12ceb).
  5. Integration pass, in Codex: switch charges into P2b's charge split and unit segment;
     residual additions into the general fund and units; TVOG wiring to the MCEV columns;
     the P3 illustration's exclusions documented.
  6. P5 in Codex from plan `2026-11-27-ul-p5-ifrs17-stress.md`, then P6b.
  Maintainer items from P2b: check 9 (reserving `fund_return_margin`, 29 of 1,000 demo
  policies breach at -0.5%); the demo capital factors are unverified.
- 2026-11-28 Maintainer asked for a methodology review, a ruling on check 9, adjusted
  goldens and validated capital factors. Steps 1 and 2 are done: the combined P2b + P3
  checks passed with 371 tests, and the two phrases are reworded. Findings and fixes:
  1. Check 9 used the wrong comparator. The model specification compares the reserving
     reserve with the best-estimate liability (BE unit reserve plus the BE general fund
     DCF, on the same real-world economics). The test compared with the mc BEL (risk-free
     growth). Against the BE liability, 1 of 1,000 policies is short, by INR 2.85 on INR
     6.42m (4e-7 relative): a return-of-allocation-charge policy seven months from
     maturity, where the upward lapse margin is favourable because a lapse forfeits the
     refund. That is within the money tolerance. The mc comparison (29 policies, INR 58,608
     in total) is reported, not asserted. It follows from the specification's reserving
     basis, which takes credit for real-world growth less 0.5%. Ruling: no
     `fund_return_margin` change; the strict xfail is removed.
  2. Demo capital factors were wrong. Two independent sources (an IAIS 2009 India solvency
     presentation and a 2018 broker report) give IRDAI linked life as 0.8% of reserves and
     0.2% of sum at risk without guarantee, and 1.8% and 0.2% with guarantee; pension and
     annuity take 0% on sum at risk; the target is 150%. The demo had 0.6%/0% and 2.0%/0.2%.
     Fixed in `src/avk/demo/unit_linked.py` and `examples/demo/basis/product_parameters.csv`.
  3. The UL cost of capital charged tax on the interest on capital before the profit
     transfer (copied from the shared `ProfitSignature`). Fixed to the specification:
     interest x (1 - transfer) x (1 - tax). The shared version in the other five products
     keeps the same imprecision and is left alone so their saved results do not move.
     Flagged for the maintainer.
  UL goldens regenerated: 14 of 210 columns changed, all capital, cost of capital, FCC,
  CRNHR or VIF. At step 0, BE part 1 went from 271.0m to 309.5m, part 2 from 3.5m to 27.9m,
  MC CRNHR from 51.4m to 61.2m, FCC from 12.5m to 14.8m, and VIF from 1,010.4m to 998.3m.
  The other 170 saved files and the manifest are unchanged.
  Noted, not changed:
  - Capital is nil at the valuation instant (the shared AVK convention), so the first
    month's frictional cost on valuation-date capital is omitted.
  - Under stochastic paths the reserving basis follows each path's returns.
  - Highest-NAV funds (P6a) should count as guaranteed for the capital factors
    (integration pass).
  - A pension variant (P6b) needs 0% on sum at risk.
  - Speed: 10k valuation 68 s, 100k 379 s.
- 2026-11-28 P6a merged (950f637). Conflicts were resolved against P2b's schema; switch
  charges now join `charges_start` and the unit segment's deductions (new test). P4b
  merged on top (api.py conflict). After both merges: 500 tests pass (runs, ESG, UL, demo
  suite) and every static and generator check passes. The UL saved table is unchanged by
  P6a and P4b. Next: an integration pass in Codex (`C:\avkwt\prompts\integ.md`: residual
  additions in the projection, highest-NAV capital classification, TVOG wiring,
  illustration limits, status docs), and P5 in Codex (`C:\avkwt\prompts\p5.md`), in
  parallel.
- 2026-11-29 A side session, at the maintainer's request, stopped three stale P5 Codex
  test runs in `C:\avkwt\p5` to free memory. Any P5 result from `.tmp/p5-task1-reg`,
  `.tmp/p5-slow` or `.tmp/p5-all` is invalid. Before merging P5, the orchestrator re-runs
  its demo-suite, slow and full checks itself. Left running: P5's StressCapital test,
  the integration pass's final `pytest` and `pytest -m slow`, and both Codex processes.
- 2026-11-29 P5 Codex finished partly (WIP committed in the clone as 1a07978, not merged).
  Done: equity shock, StressCapital sources and presets, VFA settings, in-force
  measurement, scalar oracles; 32 focused tests pass. It stopped at the VFA identity
  (IFRS BEL = mc unit reserve + `gf_bel`; largest gap INR 46,218), which exposed two
  engine timing defects:
  1. Additions are credited to the units before growth (as the specification orders it),
     but P2b's general fund paid them at month end, so their first month of growth had no
     funding. Fix: additions, and residual additions, become a start-of-month
     general-fund outgo inside `interest_earning_cashflow`.
  2. Policies whose term ends in the valuation month settle at step 1 from step-0
     balances with no return, but are paid at month end. Fix: the funds (slots, paid-up
     and DPF) earn the basis's return less FMC in the settlement month; still no premium,
     other charges, decrements or additions.
  Both change UL valuation results; the goldens will be regenerated and the moves
  documented. Not run: the full default and slow suites (the stale runs were stopped,
  and the slow TERM roll-forward hit a memory error); the capital kernel's native
  compile took over 20 minutes. Plan: merge the integration pass, apply both fixes on
  feature/unit-linked, then merge that into the P5 branch and resume P5.
