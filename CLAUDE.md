# Biological modelling project

## Sources of truth

Durable files, never chat or memory, define scientific state:
- MODEL_SPEC.md: mechanistic/mathematical specification.
- DATA_DICTIONARY.md: identifiers, units, versions and provenance.
- ASSUMPTIONS.md: accepted and proposed assumptions kept distinct.
- DECISIONS.md: decisions, rationale, approval; topology entries cite exact reports
  and supporting PMIDs. Structured governance records live in this file too.
- CURRENT_STATE.md: active stage, append-only session registry, warnings, next action.
- VALIDATION_PLAN.md: declared criterion IDs and validator-generated results.
- VALIDATION_CRITERIA.yaml: explicit executable criteria; initialize from its empty
  template only when starting a model.
- runs/<specialist>/<full-session-id>/: immutable artifacts, specialist report,
  capture/invocation records. Each MCP issues its own ID; no pipeline-wide run ID.
- runs/orchestrator/<purpose>/: orchestrator-authored summaries, analyses and inputs.
  Manual inputs require CHANGES.md: base path+SHA256, ordered exact edits,
  evidence+supporting PMIDs, authorization, output path+SHA256, reproduction command
  or patch. Missing server capabilities never justify undocumented edits.
- evidence/reports/<neko-session>/<source>__<target>.md: immutable edge reviews;
  candidates/ contains proposed-edge reports, .r2.md etc. explicit revisions.
  Never overwrite evidence or reuse another session's report location.
- inputs/: preserved user sources; runs/index.json: script-maintained artifact/usage index.

## Main-agent role and isolation

The main Claude session is the sole scientific orchestrator and shared-state writer:
clarify objectives, delegate bounded tasks, validate returned handoffs, reconcile
conflicts, obtain researcher decisions and control every stage transition. Specialists
cannot delegate, alter shared state or advance stages. Guarded report Write is their
only local authoring exception; model files are written by permitted MCP tools.

The orchestrator must have no modelling MCP tools; stop if any are visible. Run the
setup isolation guard. Four specialist-inline *-agent transports expose only NeKo to
network-curator, MaBoSS to boolean-dynamics-modeler, PhysiCell to
multicellular-configurator and BioMASS to ode-modeler. No global/project modelling
registration, enabled marketplace modelling plugin (neko/maboss/physicell/biomass
@marcorusc connect to the main session) or project-wide allow rule is permitted.
PubMed is the default literature
backend; web search needs explicit researcher authorization. Missing/failed required
servers return blocked; never substitute another domain server.

Follow the specialist's preloaded workflow skill, not MCP resource bridge tools
(unavailable in background Claude agents). Codex uses its separate isolated dispatcher
runtime and AGENTS.md; never same-process modelling delegation.

## Scientific rules

- Never infer units.
- Never invent parameter values. Proposed values must be labelled hypotheses with
  source and consequence, then explicitly approved before scientific use.
- Never silently select output nodes, mutations, initial states, or mappings.
- Keep evidence, assumptions, model outputs, and conclusions distinct.
- Use one MCP session per independent modelling hypothesis.
- Record complete session identifiers.
- Inspect state before material mutation — material mutation means any change to
  network topology, node states, parameters, or session-defining configuration (i.e.
  any of the selections in the rule above).
- Prefer summary output.
- Store large outputs as artifacts and return summaries plus paths.
- Prefer typed cross-server handoffs.
- Never bypass handoff integrity checks.
- Do not delete sessions or artifacts without explicit approval.
- Successful execution is not evidence of scientific validity.

## Literature review

Evidence gathering may proceed autonomously; evidence-driven topology/database
changes require explicit authorization. Load review-literature-evidence. Send literal
[source, effect, target] triples and known PMIDs, at most 13 coherent edges per
invocation and two reviewers concurrently. Inline the bounded queue subset; SIF
lookup is source/target-scoped Grep, never full Read. After interruption redispatch
only missing reports unless re-review was explicitly requested. Never fabricate
findings or overstate abstract-only access. ODE reviews use explicit review_kind=ode
and their own session-scoped claim contract.

## Model refinement discipline

Refinement requires explicit researcher authorization naming nodes and a concrete
VALIDATION_PLAN target. Search only Boolean functions over those nodes' existing
incoming regulators. Never add nodes/edges or change unnamed rules; structural
needs return to topology and evidence review. Record every tested variant and
result. Every final rule and every manual edge needs a provenance tag in DECISIONS:

- `database-default`: imported database-derived rule/edge, not a literature claim.
- `literature-derived`: specific mechanism/rule supported by dedicated cited review.
- `manual-literature`: explicitly authorized manual edge with its own candidate
  report, supporting PMIDs, sign/direction assessment and approval. Apply it with
  NeKo `edit_interactions` between existing nodes, never by hand-editing SIF.
- `fitted-for-dynamics`: chosen against a named validation target; no independent
  literature claim for the fitted Boolean function.
- `readout`: researcher-named summary node added via MaBoSS `edit_maboss_readouts`
  with explicit rule, rates and initial probability; core regulators only, no
  regulatory targets unless a separate topology change is approved. Document
  definition, inputs and exclusivity proof; expression exclusivity does not prove
  exclusive simulated readout states.

## Session registry

CURRENT_STATE contains the append-only lineage table: Specialist, full Session ID,
Stage, Status, Derived from, Handoff, Artifacts. Mark superseded rows and append new
sessions; never replace history. Resolve active IDs from this table before dispatch.
Handoff is pending during review, approved only after researcher sign-off, exported
only after a verified conclusive artifact exists. Downstream sessions require the
exact upstream exported session: NeKo -> MaBoSS -> PhysiCell. These approvals do not
authorize later stages. Record full lineage, effective parameters/policies, initial
states, mutations, units, threads/seeds, NeKo state IDs, MaBoSS model revisions and
run IDs, manifests/hashes (including handoff `curation_file` history companions),
warnings and failures.

## Required stage workflow

Before each downstream dispatch, complete validate-stage, wait for both independent
reviews, and obtain exact session/revision/output approval. Any later interaction,
rule, readout or rate edit supersedes it: re-review and re-approve. Record review and approval
with state.py; run and quote `python3 scripts/gate.py check <stage> <session> --outputs ...`
(for biomass_ode the outputs are every node_id of the exported graph).
Prefix the bounded task with `STAGE_GATE {"upstream_session_id":"...","outputs":["..."]}`.
The dispatch hook checks the durable records again. Explicit standalone sources use
standalone_decision_id. Never run reviews in parallel with downstream work.

After authorized operations, use scripts/capture commands to validate, relocate, hash
and index exports (docs/agentic-operations.md). Curation-bearing handoffs (NeKo 2.1,
NeKo-to-BioMASS 2.0, and MaBoSS 2.1 with such a parent) are imported from the
recorder's `backend_import_manifest`, after `scripts/capture/verify_import_manifest.py`
passes; the capture stays the gate/approval record. Specialists write guarded immutable
report.md; invocation records persist task, tool calls/results, final output and usage.
Orchestrator summaries belong under runs/orchestrator. Update state using state.py,
validate and checkpoint; every stage, including multicellular, needs independent
scientific review and reproducibility audit before closure. Export is not simulation.

## Evidence records and executable checks

Use required evidence footers; cite only supporting_pmids, never excluded citations.
Each manual edge requires its own report. `gate.py resolve` checks a conditional
approval against immutable evidence; it never mutates a model or grants new authority.
Use state.py JSON-file inputs for decisions, registry, validation and checkpoints;
never shell heredocs or unchecked replacements. Missing/duplicate rows must fail.
Diff changes before checkpoints. Record timezone-aware ISO-8601 times (helpers use
UTC +00:00); preserve source offsets and convert before comparing calendar dates.

The orchestrator may run supported read-only scripts/validate artifact analyses:
fixed points, bounded reachable attractors, readout exclusivity and declared trajectory
criteria. This authorizes no modelling MCP calls or mutations. Incomplete checks
cannot pass. Only supported validator output updates VALIDATION_PLAN via state.py.

## Multiscale mapping and task-specific procedures

Use the PhysiCell workflow's explicit Boolean-to-phenotype formulas and timing
calibration; readout layers need an exclusivity proof and approved topology scope.
Calibration returns a proposal, requiring researcher approval of units and values.
After each parameter patch compare the returned stored value and inspect the exported
value; execution success is insufficient. A configuration bundle is not a run or approval.

Checkpoint at transitions and before compact/clear/session exit via checkpoint-model.
It contains the local model/* branch, explicit staging and two-commit procedure;
never automatically switch branches or push/pull/fetch/rebase/amend/tag/clean.
Lifecycle operations require explicit user intent and the model-* skills. Archive
before reset; restart/restore require a fresh confirmation after preview, preserve
infrastructure/inputs, and never delete MCP sessions. Archived session IDs are
provenance only. Clear conversation context before modelling a restarted/restored model.

For ODE work load biomass-workflow, docs/ode-workflow.md and docs/ode-contract.md.
Start ODE work only while the ODE readiness check in docs/ode-workflow.md passes for
the pinned backend (BioMASS smoke test plus a live read-only ode-modeler isolation
check); rerun it after any backend or transport change. Keep distinct sessions and
approved sources. Provisional preservation within existing workflow authorization is not
scientific acceptance, simulation permission or conclusive export. Respect whole-model
review; exact session/revision acceptance is required. No ODE calibration, sensitivity
analysis or ODE-to-PhysiCell coupling is included. Universal approval, evidence,
lineage and no-direct-modelling-tool rules apply to both branches.
