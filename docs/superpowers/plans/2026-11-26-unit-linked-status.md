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
Codex CLI: `C:\Program Files\WindowsApps\OpenAI.Codex_26.1120.5083.0_x64__2p2nqsd0c76g0\app\resources\codex.exe`,
model `gpt-6.2-sol`.

## Phase table

| Phase | Status | Branch | Worktree | Worker / id | Last checkpoint | Notes |
|---|---|---|---|---|---|---|
| P0 design and tracking | in review | feature/unit-linked | main checkout | orchestrator | — | awaiting maintainer approval of the design |
| P1 inputs and contracts | not started | ul/p1-inputs | C:\avkwt\p1 | Claude session, Opus 5.5 medium | — | |
| P4a scenario tooling | not started | ul/p4a-scenarios | C:\avkwt\p4a | Codex gpt-6.2-sol | — | parallel with P1 |
| P2a unit engine | blocked by P1 | ul/p2a-unit-engine | C:\avkwt\p2a | Codex gpt-6.2-sol | — | |
| P2b general fund and results | blocked by P2a | ul/p2b-results | C:\avkwt\p2b | Claude session, Opus 5.5 medium | — | |
| P3 compliance (RIY, illustration) | blocked by P2b | ul/p3-compliance | C:\avkwt\p3 | Claude session, Sonnet 5.5 high | — | |
| P4b stochastic results | blocked by P2b, P4a | ul/p4b-stochastic | C:\avkwt\p4b | Codex gpt-6.2-sol | — | |
| P5 IFRS 17 VFA and stress capital | blocked by P2b | ul/p5-ifrs17 | C:\avkwt\p5 | Claude session, Opus 5.5 medium | — | |
| P6 feature extensions | blocked by P2b | split later | — | — | — | |

Status values: not started, running, stopped (usage limit or error), in review,
merged, blocked.

## Event log

- 2026-11-26 P0: recon done (specs, workbook, engine). Integration branch
  `feature/unit-linked` created from `main` at 775a859. Design drafted.
  Maintainer added: policy table one row per policy; fund holdings table one row
  per policy-fund; shared key fields consistent; history fields for retrospective
  calculations and IFRS 17 cohorting (design section 5.2).
