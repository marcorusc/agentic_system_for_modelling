# ODE integration into the specialist dispatcher

## Status and approved direction

The researcher approved creating a separate worktree based on `codex/specialist-dispatcher` and integrating the features of `ODE-specialist`. They also requested a substantive design discussion before implementing the retrospective recommendations. Phase 0 prepared that discussion. The researcher then approved Phase 1 only: port the heartbeat synchronization fix, diagnose the SDK shutdown stall, test and commit, keeping dependency versions unchanged. On 2026-09-18, they also approved automatic preservation of provisional ODE bundles within an already approved workflow; scientific acceptance and stage transitions remain approval-gated.

- Working branch: `codex/modelling-architecture-integration`.
- Base: `315cebcbc954068eafc16a26dfdfe784dc06a0a5`.
- ODE feature source: `1e8f9a43c4fc249e43d94c71316fc798ee7ad01d`.
- Preserved experiment: `model/cell-cycle-core`, audited at `3ce097e` and comparison committed at `8f0e0af`.
- Current stage: **Phase 4 complete; Phase 5 integration verification discussion next**.

## Evidence carried into this worktree

- [System retrospective](../audits/2026-09-17-system-retrospective/README.md).
- [Three-branch comparison](../audits/2026-09-17-branch-comparison/README.md).
- [Preparation checks](worktree-readiness.json).
- [Phase 1 results and shutdown diagnosis](phase1-validation.md).
- [Phase 2 contract and artifact validation](phase2-validation.md).
- [Phase 3 execution and isolation validation](phase3-validation.md).
- [Phase 4 skills, profiles and optional setup validation](phase4-validation.md).

The audit packages are byte-preserved from the experiment commit, including their hashes. They are historical records. Some relative links within them identify model artifacts or ODE documents in the original audited branches; those targets have deliberately not been copied into this software checkout. Resolve them using their recorded Git revision or the original experiment worktree. The audit reports are not the active scientific state.

The six scientific state files remain the dispatcher's empty specification baseline. `runs/`, `evidence/` and `inputs/` contain only their original placeholders. No scientific lifecycle restart or cleanup was needed.

## Integration approach

Use the dispatcher's execution framework and adapt the richer ODE features to it. Keep one shared runtime for CLI and dispatcher invocation, fixed specialist isolation, explicit app/dispatcher disabling, JSON-safe redaction, separate scientific status and durable provenance.

Import the ODE branch's authoring skills, local references, input modes, evidence schema, artifact helpers, validators, setup capabilities and Codex/Claude definitions. Adapt their routing and contracts instead of restoring the older standalone launcher. Keep the experiment's relevant regression fixes and checks as selected changes.

A temporary merge probe found nine text conflicts. Automatic merges also miss semantic changes: ODE evidence mode must pass through the dispatcher schema, invocation request, executor, validator and provenance recorder. Resolve those explicitly and test the full route.

## Proposed phases and completion criteria

Each implementation phase should have its own descriptive commit. Scientific data and experiment checkpoints are not merged into this branch.

| Phase | Work | Completion criterion |
|---|---|---|
| 0 — Preparation | Create clean worktree, preserve audit packages, configure local bootstrap, pin sources and discussion points | Baseline state and source hashes verified; no runtime changes |
| 1 — Reliable baseline | Port the heartbeat-test synchronization fix; diagnose the SDK asynchronous shutdown stall; make test completion bounded and explicit | Default and SDK test jobs terminate with accurately reported results; no unreported skips |
| 2 — ODE contracts and artifacts | Bring in ODE metadata, claim reports, source/revision checks, capture and NeKo relocation helpers; strengthen partial-publication handling | Negative tests cover stale/wrong revisions, changed artifacts, failed simulations, unsafe paths and interrupted capture publication |
| 3 — Shared execution route | Add one canonical ODE role and dispatcher entry point; transport `review_kind`; preserve CLI/dispatcher equivalence and evidence provenance | Fake-worker tests cover every start/query/result path; inventory isolation fails closed for every role |
| 4 — Skills and setup | Integrate BioMASS workflows/references for Codex and Claude, optional BioMASS, environment reuse and capability checks; reconcile profile/plugin references | Existing workflows retain their behaviour; generated configuration is consistent; optional ODE does not become a dependency for every installation |
| 5 — Integration verification | Exercise the combined contracts and approved software fixtures; validate reproduction and documentation | Record separate unit, protocol, inventory and execution results; retain every unresolved limitation |

This first implementation sequence integrates the existing feature set and necessary correctness fixes. Larger retrospective changes follow a separately discussed sequence, rather than being hidden inside the merge.

## Phase 1 outcome

Completed under the researcher's explicit approval on 2026-09-17. The heartbeat test now waits for both a heartbeat and reported tool activity. The common test runner bounds each suite to 120 seconds, reports timeouts as failures, cleans up the timed-out POSIX process group and continues the remaining suites.

The SDK stall reproduces with a minimal `asyncio.to_thread()` test without MCP or repository imports. Sandbox restrictions deny Python's internal wake-up socket writes (`PermissionError: [Errno 1] Operation not permitted`); the same test and all four SDK protocol tests terminate outside that sandbox. No dispatcher runtime or dependency change was needed. See the [validation report](phase1-validation.md) for reproduction and limits.

The SDK run passed all 176 tests. The default run passed 172 tests with four explicitly reported SDK skips. The original experiment, scientific state, routing and dependency declarations remain unchanged. Phase 2 subsequently began after approval of provisional preservation and the richer `ode_modeler` contract.

## Phase 2 outcome

Completed after approval of the two contract decisions. The richer ODE contract and evidence mode are integrated with versioned provisional-preservation semantics; capture publication is atomic for cooperating POSIX recorders. Independent software review identified five validation gaps, all fixed and regression-tested. Final SDK run: 262 passed. Default run: 258 passed and four explicit SDK skips. See [Phase 2 validation](phase2-validation.md).

## Phase 3 outcome

The researcher approved the canonical ODE start tool and explicit ODE evidence mode
through the existing isolated runtime. Both dispatcher and CLI now use that route;
software fixtures check isolation, mode/session validation, failure recording and
artifact round trips. Credential redaction preserves typed public ODE authorization
metadata, and early-failure provenance retains the requested scientific session.
Orchestrator instructions, specialist profiles, installed configuration and
scientific state remain unchanged. See [Phase 3 validation](phase3-validation.md).

## Phase 4 outcome

Completed after the researcher approved the richer ODE skills, Codex/Claude
profiles and optional setup. BioMASS setup is opt-in; existing environments can be
verified and reused without installation. Actual capabilities are checked before
optional configuration writes. Candidate-saving instructions preserve complete
workflows within one invocation and distinguish technical capture from scientific
acceptance. Review fixes cover old profile migration, custom Graphviz paths,
probe-child cleanup and literature isolation. SDK run: 335 passed. Default run:
329 passed and six explicit SDK skips. Live activation remains gated on Phase 5;
see [Phase 4 validation](phase4-validation.md).

## Contract choices

### 1. Canonical role and historical compatibility — approved 2026-09-18

Approved choice: use the dedicated feature branch's `ode_modeler`, `biomass_ode` and `runs/ode-modeler` names for the new implementation, with `start_ode_modeler` as its dispatcher tool. These align the role, skills and stronger artifact contract. Preserve all historical `ode_dynamics_modeler` records unchanged in the experiment.

New runs use the richer contract with `ode.contract_version=2`. Historical experiment records remain unchanged and use their original verifier; an adapter is deferred. The common envelope remains version 1 for existing roles. See the accepted [Phase 2 decisions](phase2-decisions.md).

### 2. Routine snapshots versus scientific acceptance — approved 2026-09-18

Approved policy: saving a provisional candidate, recording hashes and exporting a reproducible review snapshot should proceed within an already authorized workflow. These operations preserve work and do not imply scientific approval. Researcher approval should apply to accepting new scientific assumptions, consequential model changes, experiments outside the approved scope, and conclusive stage acceptance.

The ODE branch currently treats `export_model_bundle` as a conclusive operation requiring exact revision approval, while the experiment used exports to preserve review candidates. The researcher approved separating routine preservation from scientific acceptance. Preserve provenance for both provisional and accepted artifacts. A candidate export must never masquerade as an accepted model. The exact decisions and implementation requirements are recorded in [Phase 2 decisions](phase2-decisions.md). The Phase 2 validator and artifact helpers implement this distinction; runtime routing follows in Phase 3.

### 3. Completion and failure states

Recommendation: distinguish execution outcome, artifact-finalization state and scientific-decision state. Keep technical failure and scientific rejection separate. A missing parent-side report should not be presented as a new scientific approval question.

Do not automatically rerun mutations after a timeout or restart. Recover by verifying durable operation receipts and artifact identities; only repeat an operation under an explicit, safe invocation policy.

### 4. Codex and Claude support

Recommendation: bring both sets of ODE definitions and skills across, as included in the feature branch, while preserving the existing Boolean/PhysiCell routes. Validate the integrations separately. Existing documentation reports unresolved Claude parent inventory and missing independent reviewer definitions; adding an ODE agent does not resolve those issues by itself.

### 5. Scope of the first integration

Recommendation: complete the feature integration and the known correctness fixes first. Then implement compact outputs, permission/dependency plans, automatic finalization, usage/configuration telemetry and independent review as explicit work packages. This keeps regression attribution and review manageable.

## Remaining retrospective work by owner

| Area | Proposed owner and direction |
|---|---|
| Compact responses, immutable bundle loading | BioMASS/MaBoSS/NeKo backend interfaces, with dispatcher measurements |
| Connector collateral expansion and rich network round trips | NeKo backend and corresponding fixtures |
| Trajectory/snapshot distinction and durable raw results | MaBoSS backend/export contract |
| Molecular composition mapping and reaction semantics | BioMASS backend and semantic regression fixtures |
| Trusted permission receipts and per-job dependency checks | Dispatcher/shared runtime |
| Durable finalization and interrupted-operation recovery | Dispatcher plus artifact recorders/backend receipts |
| Model/effort/profile/tool-schema and token usage records | Shared runtime and operational reporting |
| Installed configuration drift and multi-client startup | Setup, dispatcher lifecycle and client integration |
| Consolidated approval and independent scientific review | Workflow design and dedicated read-only review roles |

No external backend repository has been modified or selected for implementation in this preparation phase.

## Local runtime preparation

Ignored `.setup/local.json` and `.setup/dispatcher.local.json` select the existing modelling Python, native Codex home and Codex executable. This does not install packages, change user-global profiles, activate a new plugin, or import operational state from the experiment.

The desktop task that created this worktree remains attached to the original checkout. Development commands must explicitly use this worktree as their working directory. Its scientific dispatcher context must be loaded/verified before any future modelling invocation; do not send a job to the original checkout's dispatcher merely because its tools are already visible. Software checks can run directly in this worktree without starting modelling sessions.

## Discussion checkpoint

Phases 0–4 are complete. The next discussion concerns Phase 5: verify this
worktree's deployment and actual specialist/parent isolation, then exercise bounded
software fixtures and reproduction. Decide the client scope and temporary profile
strategy before touching installed configuration. Keep scientific ODE work gated
until the applicable live checks pass. Broader telemetry, recovery and independent
review work remains separately scoped.
