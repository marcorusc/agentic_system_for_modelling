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
