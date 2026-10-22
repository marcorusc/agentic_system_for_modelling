# Documentation map

Start with the [project README](../README.md). This index lists every document under
`docs/` by purpose. **Current** documents describe release 1.0.0 and are kept in step
with the code. **Historical records** are evidence of how the system was built and
tested; they are not updated and may describe superseded versions or procedures.

## Current guides

| Document | Use it for |
|---|---|
| [automatic-setup.md](automatic-setup.md) | Installing and verifying: plugin (uv) mode, managed/reuse environments, BioMASS, source installs, `--check` |
| [agentic-operations.md](agentic-operations.md) | Day-to-day governance: state records, stage gates, captures, reviews, literature slices, failure handling |
| [ode-workflow.md](ode-workflow.md) | Formulating and running the optional BioMASS ODE branch, and its readiness gate |
| [specialist-dispatcher.md](specialist-dispatcher.md) | The Codex specialist dispatcher: setup, task lifecycle, recovery, troubleshooting |
| [neko-curation-continuity.md](neko-curation-continuity.md) | Continuing NeKo curation from exported artifacts in fresh sessions |

Related guides outside `docs/`:
[capture scripts](../scripts/capture/README.md),
[validators](../scripts/validate/README.md),
[dispatcher startup](../scripts/codex/dispatcher/README.md),
[Codex profiles](../.codex/profiles/README.md),
[changelog](../CHANGELOG.md).

## Reference contracts and design

| Document | Contents |
|---|---|
| [handoff-validation.md](handoff-validation.md) | Provider-neutral handoff schema, completion requirements, validation responsibilities |
| [ode-contract.md](ode-contract.md) | ODE result and artifact contract (version 2), evidence and export states |
| [codex-phase4-enforcement.md](codex-phase4-enforcement.md) | How each Claude enforcement is mapped for Codex |
| [codex-phase3-plugin.md](codex-phase3-plugin.md) | The repository Codex plugin and the CLI fallback route |
| [agentic-biomodelling-architecture.md](agentic-biomodelling-architecture.md) | System architecture and design rationale: roles, isolation, stages, approvals, provenance, context and parallelism policy |
| [subagent-workflow.mmd](subagent-workflow.mmd), [runtime-deployment.mmd](runtime-deployment.mmd) | Workflow and deployment diagrams (Mermaid) |

The orchestrator policies themselves are [`CLAUDE.md`](../CLAUDE.md) and
[`AGENTS.md`](../AGENTS.md).

## Historical records (evidence; not maintained)

| Document | Records |
|---|---|
| [wave2-design-decisions.md](wave2-design-decisions.md) | Wave 2 design decisions W2-D001–D020 behind the 2.5.0 server features |
| [wave1-pr-review.md](wave1-pr-review.md) | Wave 1 PR review, companion releases and ordering |
| [improvement-plan-2026-10-05.md](improvement-plan-2026-10-05.md) | Diagnostic-driven improvement plan that defined Waves 1 and 2 |
| [code-review-improvement-plan.md](code-review-improvement-plan.md) | September 2026 code-review implementation plan |
| [codex-mcp-isolation-0.153.0.md](codex-mcp-isolation-0.153.0.md) | Codex 0.153.0 MCP isolation validation (2026-09-03) |
| [neko-phase7-timeout-diagnosis.md](neko-phase7-timeout-diagnosis.md) | Diagnosis of a NeKo Phase 7 invocation timeout |
| [phase7-benchmark-proposal.md](phase7-benchmark-proposal.md), `phase7-construction-request.json`, `phase7-gene-pool.csv`, `phase7-reference-manifest.json` | De novo construction benchmark proposal and its inputs |
| `specialist-dispatcher-phase*-validation.json` | Dispatcher phase validation records |
| [integration/](integration/) | ODE-into-dispatcher integration plan, phase decisions and validation |
| [audits/](audits/) | Dated audits: the 2026-09-15 Claude ODE integration validation, branch comparison, system retrospective and diagnostic, toy cell-cycle benchmark, Point A, Wave 1 lineage/error fixes and installed baseline |
