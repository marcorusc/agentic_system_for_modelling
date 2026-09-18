# Phase 2 — ODE contracts and artifacts

Date: 2026-09-18. Branch: `codex/modelling-architecture-integration`.
Starting commit: `3f1813d`. Feature source: `1e8f9a43c4fc249e43d94c71316fc798ee7ad01d`.

## Approved decisions and result

The researcher approved automatic provisional bundle preservation inside an already authorized workflow, then selected the richer `ode_modeler` contract for new runs. The [decision record](phase2-decisions.md) preserves those choices.

Phase 2 integrates and strengthens the source branch's artifact and evidence layer:

- Canonical role `ode_modeler`, stage `biomass_ode`, artifact root `runs/ode-modeler/`.
- Explicit `ode.contract_version=2`; the existing common envelope remains version 1. Historical ODE payloads use their original verifier instead of an implicit compatibility alias.
- Provisional bundles receive complete integrity checks and use the existing workflow's recorded authorization. Exact-revision approval remains mandatory for conclusive export. Saving a candidate never advances scientific state.
- Generated revisions, source provenance, NeKo relocation, Python syntax, selected-revision simulation outputs, safe ZIPs and immutable approval snapshots are validated.
- Mechanism, kinetic-law and quantity evidence reports have their own immutable writer mode; existing edge-report behavior remains available.
- Both artifact recorders verify a complete staging directory before one final rename, serialized with a persistent POSIX lock. Failure or interruption cannot expose a partially populated final capture under cooperating recorder invocations.

See the [implemented contract](../ode-contract.md) for fields, approval records and helper commands.

## Independent software review

Read-only review found five gaps after the initial passing suite. All five were addressed before the final runs:

| Finding | Correction and regression |
|---|---|
| A draft could supply nonexistent hashed artifacts while omitting its revision path | Any ODE project artifact claim now invokes full verification. Only an empty-artifact metadata draft can defer capture checks |
| A relocated NeKo import remained valid after its original manifest and relocation record were deleted | Recorder-produced import paths now require both provenance files |
| A ZIP could contain both a file `model` and children `model/...` | File/directory prefix conflicts are rejected before a bundle is accepted |
| String conditions/time bounds and time-only CSVs could claim a successful simulation | Structural validation requires named conditions, finite increasing bounds, real numeric data columns, complete coverage and matching condition/time grids |
| Malformed nested source fields could raise an untyped exception | Nested structures are validated explicitly; duplicate/nonfinite JSON and malformed ZIP errors are also rejected |

Simulation checks were aligned with the local BioMASS backend's report format. They make no scientific positivity, units or calibration assumptions. A server-generated revision ID may still be reported in a metadata-only draft before project capture, but it does not establish verified preservation.

Three bounded software helper tasks assisted with capture publication, evidence validation, and independent review/simulation checks. These were software tasks, not scientific specialists or a new test of modelling-process isolation.

## Final validation

| Environment | Codex | Claude | Setup | Total | Exit |
|---|---:|---:|---:|---:|---:|
| Python 3.14.4, no MCP SDK, restricted sandbox | 213 passed, 4 skipped | 19 passed | 26 passed | 258 passed, 4 skipped | 0 |
| Existing Python 3.14.6, MCP 2.0.0, AnyIO 4.14.2, outside socket restriction | 217 passed | 19 passed | 26 passed | 262 passed, 0 skipped | 0 |

Commands from this integration worktree:

```text
python3 -B scripts/run_tests.py
/home/marcorusc/miniforge3/envs/mcp_modelling/bin/python -B scripts/run_tests.py
```

The investigation wrapped each command in a 180-second shell timeout; the common runner retains its 120-second per-suite bound. The default run explicitly skips the four existing SDK protocol tests. All four execute in the SDK run. The intentional nested one-test runner fixture is not counted as an extra repository test.

Focused coverage includes 36 ODE integration tests, 17 capture tests (including separate-process contention and forced termination), 16 ODE evidence tests, 15 simulation-artifact tests, and 11 literature-writer tests. Full-suite totals include these tests; do not add the focused counts again.

[Machine-readable results](phase2-validation.json) record versions, suite durations, temporary raw-log paths/hashes and preserved scientific-state hashes. The temporary logs are not packaged evidence; this report and the JSON are the durable summary.

## Boundaries and remaining work

- All six scientific source-of-truth files match the preparation receipt. Model directories still contain only `.gitkeep`; no scientific sessions were created.
- The original experiment remains at `8f0e0af6efb02f363b39449f7136847611070af5` with its original format and no tracked changes from this work.
- Dispatcher routes, shared runtime, CLI launcher, specialist profiles, `.claude/`, skills, installed dependencies and global configuration are unchanged. ODE evidence validation defaults to edge-only unless explicitly selected; Phase 3 must transport `review_kind=ode` through the runtime.
- These are software and protocol checks. No live ODE specialist, biological validation or remote CI run is claimed. Python 3.11/3.13 CI remains to be run externally.
- Approval snapshots establish record consistency, not researcher identity or the scientific scope of a prompt. The orchestrator must still enforce actual authorization and exact tool permissions.
- Capture publication covers cooperating POSIX recorders. Hidden staging and persistent lock files can remain after interruption. Automatic recovery, cleanup, power-loss durability and noncooperating writers are outside this phase.
- Numerical artifact checks do not execute a solver or prove that reported values were produced by the claimed equations. Semantic model validation and independently reproduced simulations remain separate work.

## Next phase for discussion

Phase 3 connects `start_ode_modeler` to the existing isolated runtime and transports ODE evidence mode through dispatcher inputs, CLI, validation and provenance. It should preserve the fixed BioMASS-only profile, disabled parent/other-specialist BioMASS access, disabled apps and recursive dispatch, exact tool permissions, and existing CLI/dispatcher equivalence. That routing implementation has not started.
