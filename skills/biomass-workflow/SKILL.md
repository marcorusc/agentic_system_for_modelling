---
name: biomass-workflow
description: Route approved ODE construction, Text2Model editing, BioMASS validation, exploratory simulation and final bundle export through the isolated ODE specialist.
---

# BioMASS workflow

The orchestrator delegates; it never calls modelling MCPs. Follow the formulation,
lineage, approval and artifact contract in `docs/ode-workflow.md`.

For Codex use `python scripts/codex/run_specialist.py ode_modeler --prompt-file
.codex-tasks/<invocation>.txt`. Add `--record-session-id` only for an existing
BioMASS session, never the upstream NeKo ID when creating a new session. Pass that
upstream ID in the task. Explicitly scoped `--approve-tool` flags express existing
authorization, not a new scientific approval. For Claude use `ode-modeler`.

Include input kind, exact approved source/handoff, objective, full lineage,
authorized reactions/kinetics/mappings, scenario settings, allowed assumptions,
required evidence, and expected artifacts. Await the result before durable updates.
The specialist returns evidence requests to the orchestrator, which routes bounded
ODE claims to literature_reviewer; it does not delegate itself.

## Specialist operations

Before authoring read [reaction syntax](references/reaction_syntax.md),
[examples](references/authoring_examples.md), and [editing](references/model_editing.md).
For NeKo imports also read [network interpretation](references/network_to_reactions.md).
These are versioned BioMASS 0.14 server references; see references/provenance.json.
Codex may instead read matching `docs://biomass/` resources. Claude must use these
local files because background agents have no MCP resource bridge.

1. Inspect or create the authorized session; verify upstream integrity on import.
2. Store reviewed evidence. Preview exact reaction edits with expected_version,
   then apply only already-approved changes. Preserve stable IDs and uncovered edges.
3. Inspect generated names before numerical configuration. Whole-document,
   whole-reaction-list and configuration replacement clear or replace settings;
   preserve and reapply only approved values after inspection.
4. Validate and generate. Inspect equations, evidence, coverage and quantity origins.
   Missing units stay null; generated defaults remain placeholders.
5. Run only requested scenarios with explicit time bounds and approved numerical
   choices. No placeholder opt-in without explicit authorization. Visualization
   is optional; missing graph dependencies do not block model construction.
6. Return artifacts, hashes, revision/version, coverage, actual numerical settings,
   warnings and draft report. Export the final bundle only on explicit approval
   of that revision. Preserve artifacts and sessions.

The orchestrator records verified project copies with
`scripts/codex/record_ode_artifacts.py`, persists reports/manifests, then runs the
common handoff validator. Keep syntax, numerical execution and biology separate.
