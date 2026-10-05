---
name: validate-stage
description: Coordinates independent scientific review and reproducibility audit before approving a modelling-stage transition.
---

# Validate a modelling stage

The main orchestrator must:

1. Identify the completed stage and claimed conclusions.
2. Ensure the stage has a run manifest and durable summary.
3. Invoke `scientific-reviewer`.
4. Invoke `reproducibility-auditor`.
5. Compare both reports against `VALIDATION_PLAN.md`.
6. Separate blocking issues from limitations.
7. Request researcher judgment for unresolved assumptions.
8. Record the outcome in `DECISIONS.md`.
9. Update `CURRENT_STATE.md`.

Return one status: `approved`, `approved_with_limitations`, `revision_required`, or `blocked`.


## ODE state

Apply `docs/ode-contract.md` to `ode_modeler` / `biomass_ode`. Verify source kind,
lineage, document version, selected revision, complete captured inventory, evidence,
actual numerical settings and scenario results. Validate ODE evidence with explicit
`--review-kind ode`. Distinguish provisional workflow authorization from exact
session/revision conclusive-export approval; a candidate snapshot keeps the
scientific registry pending. Existing `runs/` and `evidence/` lifecycle scopes
already include ODE artifacts. Successful solves are not biological validation.
Preserve independent reviewer/auditor requirements; missing definitions remain blockers.

## Required stage workflow

1. Reconstruct active state and full session IDs; inline the bounded objective,
   authorized operations, exact identifiers and relevant specification excerpts.
   Specialists read only additional files explicitly named in their task.
2. Before downstream dispatch, complete `validate-stage`, wait for both independent
   reviews, and obtain researcher approval of exact session/revision and outputs.
   Record both with `scripts/state.py record`. Run and quote
   `python3 scripts/gate.py check <downstream-stage> <upstream-session> --outputs ...`.
   Prefix the task with `STAGE_GATE {"upstream_session_id":"...","outputs":["..."]}`.
   The Agent/Task hook checks the durable records again. An approved standalone
   source uses `standalone_decision_id` instead; never invent an exemption.
3. Follow the specialist workflow; create a fresh session for a new hypothesis and
   inspect state/history before each authorized material mutation.
4. Capture exports with the provider-neutral `scripts/capture/` commands described
   in docs/agentic-operations.md. Validate relocated inputs/hashes and index entries;
   never manually copy/hash a server handoff or edit the run index by hand.
5. The specialist writes its guarded immutable report.md. Invocation capture stores
   prompt, tool calls/results, final report and available usage. Orchestrator-authored
   analysis and summaries belong under `runs/orchestrator/<purpose>/`.
6. Update state through `scripts/state.py`, validate artifacts and independent
   reviews, then checkpoint. A multicellular configuration needs its own scientific
   review and reproducibility audit before closure; an export is not a simulation.
7. Stop for consequential unresolved choices. Neither reviews nor gate helpers
   confer human approval. Never run validation concurrently with downstream work.

## Sequential review gate

Complete both independent scientific review and reproducibility audit before any
downstream dispatch. Persist reports under runs/orchestrator/reviews/<session>/.
Use scripts/state.py record for a stage_review record identifying exact session,
artifact hash, both report paths/hashes and outcome approved, approved_with_limitations,
revision_required or blocked. Then obtain and record researcher stage_approval for
that exact artifact and declared outputs. Run scripts/gate.py check and quote its
JSON result before dispatch; a review recommendation is not researcher approval.
A later blocking review or changed artifact invalidates the earlier gate.

PhysiCell closure also requires both reviews. Inspect all enabled package dependencies,
relative paths, NeKo/MaBoSS lineage, exact mappings, node/behavior existence, readout
exclusivity, timing/units, cycle phase exits/base rates, initial cells and declared
parameters. Read exported values after patches, especially apoptosis/necrosis/motility.
Record missing coverage as unverified; never equate valid XML/configuration with
an executed or scientifically validated multicellular simulation.
