# Handoff validation

`scripts/codex/validate_handoff.py` validates the provider-neutral handoff and,
when `status` is `completed`, the files supporting completion. ODE results also
verify any claimed captured revision, simulation, approval or bundle while
scientific approval is pending. It does not approve
scientific conclusions, run a simulator, or authorize a conclusive handoff export.

## Drafts and completion

A read-only specialist that returns proposed reports or paths must use
`needs_approval`, list the outstanding work in `decisions_required`, and recommend
`null` while awaiting approval. The orchestrator persists reports through the
appropriate writer, assembles the stage manifest, computes hashes, and validates
the completed result. Preserve the original invocation and draft result as
provenance; do not rewrite them to claim the specialist wrote the final files.
An existing completed result must pass the current validator before it can be
used for a stage transition. Do not downgrade its status merely to bypass checks.

Completed artifact entries use the existing object form:

```json
{"path": "runs/network-curator/SESSION/report.md", "sha256": "64 hexadecimal digits"}
```

The validator requires nonempty validation checks and a nonempty artifact list.
Every listed artifact must be a nonempty regular file, without symlinks in its
path, under the exact specialist/session directory. Duplicate paths, missing
hashes, and changed file contents are rejected. Plain path strings remain valid
for drafts but cannot establish completion.

## Required stage files

| Specialist | Required completed artifacts |
|---|---|
| Network curator | `manifest.json`, Markdown report, SIF export, `important_paths.md`, `literature_queue.json` |
| Boolean dynamics modeler | `manifest.json`, Markdown report, BND and CFG exports |
| Multicellular configurator | `manifest.json`, Markdown report, XML configuration export |
| ODE modeler | Identity manifest, report and fully inventoried generated revision; additional checks for simulation, provisional bundles and conclusive export |
| Literature reviewer | Session-scoped edge reports, or explicitly selected ODE claim reports, that pass their content validator |

Modelling files belong under `runs/<specialist-directory>/<session_id>/`.
Literature reports belong under `evidence/reports/<neko_session_id>/`. The NeKo
queue is a session-scoped copy for Codex, not a replacement for Claude's shared
queue. A valid queue JSON object or array is accepted; edge semantics still
require review. XML must parse; this does not validate a PhysiCell simulation.

The typed `manifest.json` must contain `schema_version`, `specialist`, `stage`,
`session_id`, and `derived_from_session_id` matching the handoff. It is a separate
file from the result that lists and hashes it, avoiding a self-referential hash.
Additional provenance and scientific fields should be retained. Other export and
report filenames are unrestricted; extensions identify BND, CFG, SIF, and XML.

These checks enforce the repository's artifact requirements, but do not establish
SIF topology correctness, BND/CFG semantics, evidence quality, approval history, or
whether an upstream registry row is exported. The orchestrator must still compare
the actual session registry, decisions, lineage, and `VALIDATION_PLAN.md` before
requesting a stage transition.

## Validation responsibilities

| Workflow | Current validator | Limitation |
|---|---|---|
| Claude `.claude/skills/validate-stage` | Requires `scientific-reviewer` and `reproducibility-auditor` | Read-only definitions are present; live Claude invocation and review completion still require verification |
| Codex `skills/validate-stage` | Main orchestrator runs machine checks, then scientific and reproducibility checks, followed by researcher approval | Review is not independent of the orchestrator |

This documents current behavior without changing either workflow. Implementing
independent review for Codex or changing Claude's review requirement is separate
scientific-policy work.

## Launcher inventory

Every enabled specialist MCP must be allowlisted: exactly the matching modelling
server for a modelling specialist, and only optional `pubmed` for literature.
Unknown enabled names are rejected, including aliases. Disabled unrelated entries
are allowed. The inventory checks configuration, not whether a server binary is
trustworthy or responds correctly; required server startup and tool availability
must still succeed. Parent desktop-tool isolation remains an external requirement.

## Versioned ODE alternative

See the [ODE artifact contract](ode-contract.md) for `ode_modeler`,
`ode.contract_version=2`, provisional preservation, revision approval, capture
publication and ODE claim evidence. The common envelope and existing Boolean/
PhysiCell contracts remain version 1. These Phase 2 helpers do not activate a
new dispatcher route or change scientific stage policy.

## Capture an existing NeKo Boolean export

After the approved export exists, the parent can preserve it with the pure-file
recorder. Use the modelling environment's Python for the backend's typed contract
reader; this imports no modelling server and runs no engine:

```sh
python scripts/codex/record_neko_boolean_handoff.py \
  --server-root /absolute/NeKo/server/root \
  --manifest /absolute/NeKo/server/root/artifacts/SESSION/export.handoff.json \
  --capture-id approved-export
```

The recorder verifies session ownership, safe paths, artifact hashes, the typed
manifest and exact BNET target order. It atomically publishes original bytes,
a separately relocated import manifest and provenance under the source session's
`boolean-handoffs/` directory. It refuses an existing capture ID and does not
re-export a model, modify rules, approve a stage or write shared scientific state.
Parent approval and completed-handoff validation still apply.
