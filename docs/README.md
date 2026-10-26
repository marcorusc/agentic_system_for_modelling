# Documentation map

Start with the [project README](../README.md). Everything listed here describes the
current release (see [`CHANGELOG.md`](../CHANGELOG.md)).

## For biologists

| Document | Use it for |
|---|---|
| [user-guide.md](user-guide.md) | Using the framework on your own project: what it can do, how a session goes, the decisions you make, the project files and how to read results |

## Install and operate

| Document | Use it for |
|---|---|
| [automatic-setup.md](automatic-setup.md) | Installing and verifying: plugin (uv) mode, managed or reused environments, BioMASS, source installs, `--check` |
| [agentic-operations.md](agentic-operations.md) | Day-to-day governance for the orchestrator: state records, stage gates, captures, reviews, literature slices, failure handling |
| [ode-workflow.md](ode-workflow.md) | The optional BioMASS ODE branch: formulation, inputs, the ODE readiness check, capture and the real-backend smoke test |
| [neko-curation-continuity.md](neko-curation-continuity.md) | Continuing NeKo curation from exported artifacts in a fresh session |
| [specialist-dispatcher.md](specialist-dispatcher.md) | The Codex specialist dispatcher: isolation, task lifecycle, plugin, CLI fallback, troubleshooting |

Related guides outside `docs/`:

- [capture scripts](../scripts/capture/README.md)
- [validators](../scripts/validate/README.md)
- [dispatcher startup](../scripts/codex/dispatcher/README.md)
- [Codex profiles](../.codex/profiles/README.md)

## Reference contracts and design

| Document | Contents |
|---|---|
| [agentic-biomodelling-architecture.md](agentic-biomodelling-architecture.md) | System architecture and design rationale: roles, isolation, stages, approvals, provenance, context and parallelism policy |
| [handoff-validation.md](handoff-validation.md) | Provider-neutral handoff schema, completion requirements, validation responsibilities |
| [ode-contract.md](ode-contract.md) | ODE result and artifact contract (version 2), evidence and export states |
| [codex-enforcement.md](codex-enforcement.md) | How each Claude enforcement mechanism is mapped for Codex |
| [subagent-workflow.mmd](subagent-workflow.mmd), [runtime-deployment.mmd](runtime-deployment.mmd) | Workflow and deployment diagrams (Mermaid) |

The orchestrator policies themselves are [`CLAUDE.md`](../CLAUDE.md) (Claude Code) and
[`AGENTS.md`](../AGENTS.md) (Codex).

## History

Development records from building and upgrading the system were removed from the
tree after release 1.0.1. They covered improvement plans, the Wave 1 and Wave 2
records, audits, benchmark proposals and the ODE integration phases. They remain
available in Git history and at tag
[`v1.0.1`](https://github.com/marcorusc/agentic_system_for_modelling/tree/v1.0.1/docs).
