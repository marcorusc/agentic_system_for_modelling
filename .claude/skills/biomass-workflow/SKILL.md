---
name: biomass-workflow
description: Route authorized ODE construction, Text2Model editing, BioMASS validation, provisional candidate preservation and approved exploratory simulation through the isolated ODE specialist.
---

# BioMASS workflow

The orchestrator never calls modelling MCPs. Follow `AGENTS.md` and
`docs/ode-contract.md`; use this route only after the configured client and
specialist isolation checks have passed. New results use `ode_modeler`,
`biomass_ode`, `schema_version=1`, and `ode.contract_version=2`.
Read `docs/ode-workflow.md` for formulation choices and the Phase 5 live-readiness
gate. Template installation or passing software tests alone does not activate live
ODE modelling.

## Delegation and inputs

For Codex send the bounded `task` to `specialist_dispatcher.start_ode_modeler`.
Supply `record_session_id` only for an existing BioMASS session, never the upstream
NeKo ID when creating a new one. Put the full upstream ID and manifest in the task.
Use exact `approved_tools` only for writes already authorized for this invocation.
Query `get_specialist_events` with its sequence cursor and `get_specialist_task`
until terminal. Only `succeeded` carries a validated handoff; then inspect its
independent scientific status. Cancellation preserves partial artifacts and never
authorizes automatic resumption. For Claude, delegate to `ode-modeler` under the
repository's Claude isolation gate. Neither specialist delegates further.

Resolve the active session from `CURRENT_STATE.md`. Use a fresh session for each
independent hypothesis unless reuse or reconstruction is explicitly authorized.
Name the objective and one authorized input kind:

- `neko`: verified exported NeKo-to-BioMASS graph handoff and complete source-session
  lineage. A BNET file or signed network is not a biochemical reaction model.
- `standalone_text`: explicit standalone authorization, exact Text2Model source and
  source hash; no NeKo session or connected graph is required.
- `reactions`: explicit standalone authorization and the exact bounded reaction
  construction request; preserve it in the result.

Include authorized mechanisms, kinetic laws, species/compartment mappings,
observables, numerical/scenario settings, proposed assumptions, required evidence,
and expected artifacts. A consolidated drafting authorization permits a complete
candidate for one review; proposed assumptions remain unaccepted. Do not request
repeated per-reaction approval merely to continue that authorized draft.

## Authoring references and specialist work

Read [reaction syntax](references/reaction_syntax.md) when authoring Text2Model,
[examples](references/authoring_examples.md) for the mechanism being drafted, and
[editing](references/model_editing.md) before revising an existing document.
For NeKo imports also read [network interpretation](references/network_to_reactions.md).
[Provenance](references/provenance.json) records the exact BioMASS 0.14/server 2.3
reference hashes. Revalidate tool semantics after upgrades.

These upstream references describe standalone server capabilities. Their literature
retrieval instructions mean return evidence requests to the orchestrator, which
routes at most 13 coherent literal claims per isolated literature invocation with
`review_kind=ode` and the full BioMASS `record_session_id`; no modelling specialist
uses literature tools. Their illustrative quantities are not approved defaults.
Their restore instructions require explicit session-reuse authority. Claude reads
these local files; references to BioMASS documentation resources resolve to the
matching local filename and do not require MCP resource bridge calls.

1. Inspect or create the authorized session and verify upstream integrity. Inspect
   exact reaction IDs, species, generated symbols, document version and revision.
2. Preserve the original edge set and many-to-many edge/reaction mappings. Record
   represented, combined/indirect and unresolved coverage; never add dummy reactions
   to satisfy a coverage count. Evidence for an edge does not establish kinetics.
3. Store reviewed evidence. Preview exact `build_reactions` edits with
   `expected_version`, then apply only the authorized batch. Whole-list
   `set_reactions`, `import_text` and whole-configuration `configure_model` replace
   state or clear settings; inspect and reapply only approved compatible values.
4. Validate syntax and generate only within the authorized scope. Inspect equations,
   evidence, coverage and quantity origins. Missing units remain unknown; generated
   defaults remain placeholders. Generation is separate from numerical simulation.
5. Simulate only requested, approved scenarios with explicit time bounds and approved
   numerical choices. Keep `allow_placeholders=false` unless the exact hypothetical
   values and opt-in were approved. Record actual condition settings and solver
   outcomes. Visualization is optional. Calibration, sensitivity analysis and
   ODE-to-PhysiCell integration are outside this route.
6. Return report content, server artifacts and hashes, revision/version, coverage,
   numerical settings and limitations. Keep server paths in `server_artifacts`
   until verified repository copies exist; never claim incomplete artifacts complete.

## Preserve candidates and distinguish acceptance

Within an already authorized workflow, save a provisional candidate bundle without
asking for another scientific approval merely to preserve it. The orchestrator
records the existing session-scoped `workflow_authorization` once. The parent-finalized result uses
`export_status=provisional`; verify the selected revision, complete inventory,
hashes and bundle with the same rigor as a conclusive export.

Preservation does not accept assumptions, authorize simulation, advance a stage or
mark the scientific registry handoff `exported`. Conclusive export requires the
reviewed exact revision's `export_approval` and explicit export instruction. A new
revision does not inherit conclusive approval. Retain sessions and diagnostics;
technical capture failure is a technical blocker, not a new scientific decision.

The orchestrator records verified project copies using
`scripts/codex/record_ode_artifacts.py`, persists the report and matching manifest,
and runs the common handoff validator before synthesis or any transition. Artifacts
belong under `runs/ode-modeler/{biomass_session_id}/`. A generated revision, a
successful numerical run and biological validation are separate claims.


## Read-only result and parent finalization

Execute the complete authorized workflow, including a requested server-side candidate
bundle, in one specialist invocation where its prerequisites permit. For a new session,
pass the existing researcher authorization and exact scope in the task. The parent
binds that already granted preservation authority to the returned full session ID
when recording the project snapshot; no bootstrap return is required solely to
create this session-bound record. Do not assume a process-local session survives
into a later invocation. Later correction workflows use approved artifacts and
explicitly authorized fresh import/reconstruction.

Until project capture exists, return a metadata-only `needs_approval` handoff with
`ode.export_status=pending`, `artifacts=[]`, `simulation_paths=[]`, and no
`revision_path`, `bundle_path`, `workflow_authorization` or `export_approval` claim.
The actual server revision/version, external inventory and hashes, report draft,
and performed operations belong in metadata, `server_artifacts`, and actions.
Identify pending parent recording separately from unresolved scientific decisions;
`recommended_next_stage` stays null. The dispatcher can validate this intermediate
result without treating external files as verified project artifacts.

The current envelope requires nonempty `decisions_required` for `needs_approval`.
List operational work there with the prefix `Technical parent recording only`,
for example: “Capture and verify the inventory, record the already approved
preservation authority, and create the provisional completion; no new researcher
approval is requested.” Keep actual scientific decisions as separate entries.
The parent performs this recording work rather than sending it as an approval question.

The parent records the existing authority, captures and verifies the complete
returned inventory, writes the report and matching manifest, and creates a separate
completion result with `export_status=provisional` and its project paths/hashes.
Validate that completion before synthesis. Preserve the original specialist result.
Technical recording does not require another scientific approval; acceptance of
proposed assumptions and stage advancement retain their existing gates.

The server's reaction label `assumed` is not a researcher decision. Report each such
mechanism as proposed or accepted with the actual decision reference. Small-subsystem
examples describe internal assembly techniques, not repeated approval boundaries
inside an authorized whole-model draft. Load examples only when the current syntax
or mechanism needs them; read editing guidance for edits and network interpretation
for NeKo-derived work.

## CLI fallback

If the dispatcher is unavailable, use the same shared runtime through
`python scripts/codex/run_specialist.py ode_modeler --prompt-file
.codex-tasks/<invocation>.txt`. Add `--record-session-id` for an existing BioMASS
session and exact `--approve-tool` entries for already authorized writes. Preserve
the same input, isolation, provenance and scientific gates; this fallback does not
permit another backend, a same-process modelling agent, or automatic retry.
