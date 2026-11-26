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

## Phase table

| Phase | Status | Branch | Worktree | Worker / id | Last checkpoint | Notes |
|---|---|---|---|---|---|---|
| P0 design and tracking | merged | feature/unit-linked | main checkout | orchestrator | 021370e | design approved 2026-11-26 |
| P1 inputs and contracts | running | claude/ul-p1-inputs-d90104 | `.claude\worktrees\ul-p1-inputs-d90104` (inside the main checkout) | Claude session `local_155c82e5-61a0-469c-8bf6-94630c380042` (ul-p1-inputs), Opus 5.5 medium | — | commits locally itself |
| P4a scenario tooling | merged | ul/p4a-scenarios | `C:\avkwt\p4a` (full clone) | Codex gpt-6.2-sol | b5fb061 (merge 49b4238) | orchestrator re-ran checks: 220 passed, 14 contracts |
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
- 2026-11-26 P0 merged (design approved). P4a started in Codex (clone `C:\avkwt\p4a`,
  effort high). P1 started as Claude session ul-p1-inputs (Opus 5.5 medium).
- 2026-11-26 P4a merged into feature/unit-linked (49b4238) after review; Codex report:
  all checks incl. slow suite passed; orchestrator re-ran lint/format/mypy/imports/reference/default pytest (220 passed).
