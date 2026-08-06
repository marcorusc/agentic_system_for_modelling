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
