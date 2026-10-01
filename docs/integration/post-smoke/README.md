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
2. **Pending dependency decision:** integrate NeKo/MaBoSS preservation in dedicated
   backend source branches, or choose maintained project-local overlays. Dedicated
   source branches are recommended so both clients share the same implementation.
3. **Pending:** address reusable capture/finalization and setup gaps with focused
   contracts/tests; update installation and completion documentation. Keep broader
   telemetry and context-size redesign separately scoped.
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
