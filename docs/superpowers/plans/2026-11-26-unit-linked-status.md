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
| P2b general fund and results | running | app worktree branch (step 0 re-bases it on feature/unit-linked ≥ 4d4e86f) | app worktree | Claude session `local_32b69ad7-2b4c-43cc-b350-eb0c78dfe618`, Opus 5.5 medium | — | plan `2026-11-26-ul-p2b-results.md`; log `ul-p2b-log.md` |
| P3 compliance (RIY, illustration) | merged; general-fund wiring of residual additions waits for P2b | claude/ul-p3-compliance-c1cbcb | app worktree | Claude session `local_9a05dfb5-71ef-4db0-9ce3-440ffd29d952`, Sonnet 5.5 high | cafa52a (merge 1c3e888) | plan `2026-11-27-ul-p3-compliance.md`; log `ul-p3-log.md` |
| P4b stochastic results, part 1 | reviewed; merge after P2b and P6a | ul/p4b-stochastic | `C:\avkwt\p4b` (full clone) | Codex gpt-6.2-sol, effort high, prompt `C:\avkwt\prompts\p4b.md` | dd12ceb (clone and main checkout) | summaries, `avk.api.tvog`, dynamic lapse as an optional run-file setting (off when absent), tutorial; TVOG wiring to P2b columns later |
| P5 IFRS 17 VFA and stress capital | plan merged (3f0f164); build blocked by P2b | ul/p5-ifrs17 | — | plan by session `local_79cec2d5-2396-4b34-9c21-8ea34d4a8aca` | — | plan `2026-11-27-ul-p5-ifrs17-stress.md` (10 tasks) |
| P6a top-ups, fund strategies, highest NAV | reviewed; merge after P2b | ul/p6a-unit-features | `C:\avkwt\p6a` (full clone) | Codex gpt-6.2-sol, effort high, prompt `C:\avkwt\prompts\p6a.md` | 9fcd327 (clone and main checkout) | all features off by default; demo byte-identical (SHA-256 in its log) |
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
