---
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

Apply docs/ode-workflow.md for biomass_ode. Verify full lineage, selected document
version/revision, evidence, numerical origins, actual scenario values, artifact hashes
and matching researcher export approval. Include runs/ode-modeler and session-scoped
ODE evidence in existing lifecycle/checkpoint boundaries. Generated models and
successful solves do not establish scientific validity. Preserve existing independent
review requirements and report missing reviewer definitions as blockers.
