# Post-smoke integration selection

## Scope and sequence

On 2026-10-01 the researcher authorized stepwise integration, followed by a
whole-system code diagnostic (no modelling session), then pushing and updating
main. They will test Claude afterward. This report tracks software integration;
it does not alter scientific state or accept new modelling assumptions.

Work in `codex/modelling-architecture-integration`. Preserve both experiment
branches. Select reusable changes rather than merging their active scientific
records. Every implementation step has a descriptive commit and relevant tests.

1. **Complete:** transfer the three reusable repository fixes below.
2. **Source integration complete:** the researcher selected dedicated backend
   source branches. NeKo and MaBoSS preservation fixes are committed separately;
   setup adoption and a reproduced SDK compatibility blocker remain outstanding.
3. **Complete in source:** pinned backend setup, recursive-copy protection and
   reusable capture checks are implemented and regression-tested. Fresh installation
   verification remains part of release diagnostics. Broader automatic stage
   finalization, telemetry and context-size redesign remain separately scoped.
4. **Pending:** diagnose the complete system through code review and software
   tests, including Codex/Claude setup, routing, permissions, handoffs, dependency
   compatibility, failure recovery and provenance. Fix material findings before
   publication. No scientific models are run in this diagnostic.
5. **Pending:** publish reviewed changes and update main after integration and
   diagnostic completion; the researcher then performs the live Claude test.

## Selected changes

| Item | Source | Disposition |
|---|---|---|
| Explicit specialist web-search boundary | smoke `0eeb1ef` | Integrated as `6a12d49`; only authorized literature fallback enables search, with identical preflight/execution overrides |
| ODE failures before session creation | smoke `e34a550` | Integrated as `b7d00ca`; launcher, setup migration and Codex/Claude guidance explain the existing null-session contract without weakening validation |
| NeKo graph relocation | smoke `449cb34` | Integrated as `93c874e`; preserve basename and reject capture-metadata collisions |
| NeKo SIF reference round trip | smoke `2f6d46e` patch/tests | Next dependency step; preserve exported PMID comments on import |
| Immutable MaBoSS run results | smoke `1da736c` patch/tests | Next dependency step; preserve full trajectories and actual engine inputs/outputs per run, retaining legacy final-snapshot behavior |
| Boolean target ordering | smoke `79f5981` | Retain regression requirement; generalize the check when integrating reusable capture, not the nine-gene script |
| ODE capture ownership recovery | smoke `72a9b51`, `docs/smoke-test/capture_ode_execution.py` | Retain regression requirement; use authoritative same-invocation inventory, never inferred ownership or weaker artifact validation |
| Setup recursion when temporary home is inside source | smoke Phase 5 deployment report | Add a pre-copy path guard during setup hardening; source and destination must not recursively contain the copied tree |
| Numerical result validators and plots | smoke `72a9b51` | Keep experiment criteria with the experiment; helpers currently encode exact scenarios/species/tolerances and are not generic defaults |
| Active model state, approvals, runs, evidence, overlays and private profiles | smoke checkpoints | Preserve on experiment branch; do not import as this repository's active baseline |

The smoke patch commits contain deployment reports, local absolute paths and, in
one case, scientific-state edits. They must not be cherry-picked wholesale.

## Step 1 validation

All three changes applied cleanly and retain their source commit IDs in Git
trailers. The bounded repository runner passed **349 tests**: 271 Codex, 19 Claude,
59 setup, with no skips. See [machine-readable validation](step1-validation.json)
and [complete test log](step1-tests.log). Nested test-runner fixture output is not
counted as an additional top-level suite.

The six scientific source files remain byte-identical to integration baseline
`24fe3e7`. No modelling session, installed profile, dependency installation, remote
push or main-branch update was performed. Passing Claude source tests does not
establish live Claude inventory isolation or scientific execution.

## Completed smoke evidence

The experiment branch is `model/cell-cycle-dispatcher-smoke`, content checkpoint
`72a9b51ed1e6fcf7e7c1cc56666eaf6d0e3147b0`, metadata checkpoint
`279ab9f742d395dd77e04eafcc8e79ad0e0b6ce3`. Resolve these paths at that revision:

- `docs/smoke-test/execution-comparison/report.md`
- `docs/smoke-test/execution-comparison/range-acceptance.json`
- `docs/smoke-test/execution-comparison/operational-record.json`
- `docs/integration/phase5-cell-cycle/README.md` (historical deployment report;
  its in-progress modelling text is superseded by the completed comparison)

Both engines ran two approved synthetic scenarios through isolated specialists.
MaBoSS used ten threads and reported 0–98; the researcher accepted that limitation
while preserving the failed original endpoint check. BioMASS reported 0–100 and
passed the approved numerical checks. These are executability observations, not
biological validation, general release readiness or a complete tool-call audit.

## Backend ownership decision

Read-only inspection found clean local sources at:

- NeKo: `Neko`, main at `f9b8d8c`, version 1.10.0; the parser still assigns
  `SIF file` instead of restoring reference comments.
- MCP servers: `mcp-biomodelling-servers`, branch `mcp-biomass` at `57f1ba5`,
  version 2.3.0; the per-run preservation helper is absent.

The current setup pins MCP package version 2.3.0, which alone does not establish
these added capabilities. Select and record reproducible dependency revisions or
an explicit maintained overlay before claiming ordinary setup reproduces the
smoke environment. No dependency source or shared installation has been changed
as part of Step 1. Source-repository status here is local, not a fetched upstream
release check.

## Step 2 outcome — dedicated backend source branches

Researcher choice: “Use dedicated backend source branches (Recommended)”. Separate
worktrees preserve the existing NeKo main and MCP `mcp-biomass` checkouts.

| Repository | Branch | Content commit | Validation |
|---|---|---|---|
| NeKo | `codex/preserve-sif-references` | `94579ac506aeb87545ca9b709d8c5fc316a9f552` | Nine offline reference round-trip regressions passed; tests retain Python 3.10 compatibility |
| MCP servers | `codex/preserve-maboss-runs` | `1f16e5d128ee78e6bffc0945fc961ee672ca0b38` | Seven new preservation tests pass; updated protocol success/concurrency fixtures pass; changed Python passes Ruff |

The MCP patch adds immutable exact inputs/raw outputs/full tables and a manifest
published last. Legacy final-snapshot behavior is preserved. Its tests cover
multiple runs, failed copy, missing input, path rejection, namespace collision and
partial-publication rollback. No engine or biological model was run.

**Release blocker:** the wider MCP checks report 98 passes and 21 failures. The
same 21 cases fail on the unchanged source baseline (91 passes). All involve
expected actionable error text being replaced by generic tool-error messages with
installed MCP SDK 2.2.0. No new failing case was introduced. Do not characterize
these backend checks as all passing; resolve the error contract during the later
whole-system diagnostic before publication. The setup and final source revision
selection must incorporate any resulting follow-up commit.

See [Step 2 validation](step2-validation.json), [baseline protocol log](step2-mcp-baseline.log),
[patched protocol log](step2-mcp-preservation.log) and [NeKo log](step2-neko-tests.log).
The first broader run aborted in a GUI plotting backend; the completed comparisons
use `MPLBACKEND=Agg`. The modelling environment had no pytest, so backend tests used
its existing development environment. No shared environment was installed into.

These are local source revisions, not releases or installed dependencies. Setup
still pins the old package version and has not adopted the new source commits.
The next step must make that dependency selection reproducible for both clients,
then address capture/setup gaps. Push and main updates remain after diagnostic.

## Step 3 outcome — setup and capture integration

- `15b7b3b`: opt-in `--backend-sources` manifest, exact clean Git identities,
  committed build snapshots, installation-origin and installed-file receipts.
  Codex and Claude select the same environment; checks/reuse verify the receipt
  before writing client configuration. Both real backend checkouts match the
  checked-in integration manifest. Package installation was tested with fake pip,
  not performed against the shared environment. Transitive package resolution
  remains recorded by pip freeze, not globally locked by the two source pins.
- `3f75f3c`: reject Codex source/home/cache overlap before rendering or installation,
  including symlink aliases and direct plugin-installer entry points.
- Capture implementation: preserve existing Boolean exports with typed identity,
  exact BNET target order and atomic publication. Reconcile missing redundant ODE
  ownership only against the same recorded invocation's successful file catalogue;
  hash-check provenance again before publication. Scientific state/approvals and
  the original handoff remain unchanged. No automatic simulation retry or stage
  acceptance was added.

The bounded full runner passed **373 tests** (280 Codex, 19 Claude, 74 setup),
with no skips. Existing concurrency/interruption capture tests still pass. A
read-only application of the new ODE reconciler to the historical smoke invocation
verified all 42 entries; it wrote no new capture and called no modelling tool.
See [validation and limitations](step3-validation.json) and [test log](step3-tests.log).

Next is the requested whole-system **code diagnostic**, not another modelling
session. It must address the reproduced backend SDK error-message failures,
review both client routes and preservation contracts, and verify fresh installation
before claiming release readiness. The source manifest must be advanced if that
review changes backend commits. The ordinary released-package setup pin is not
silently replaced by an unpublished dependency. Remote publication and main
updates remain after the diagnostic; live Claude testing follows publication.
