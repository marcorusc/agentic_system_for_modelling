---
name: validate-stage
description: Validate a completed biological-modelling stage against lineage, artifacts, approvals, reproducibility, and VALIDATION_PLAN.md before any transition.
---

# Validate a modelling stage

The orchestrator must identify the claimed stage and conclusions, then inspect the
recorded specialist invocation, typed handoff, mandatory exports, hashes, warnings,
and upstream lineage. Reject unknown specialist/stage pairs, artifacts outside the
approved session directory, failed validation marked completed, and any skipped
researcher gate.

Compare the claims and limitations to `VALIDATION_PLAN.md`. Keep model behavior,
literature evidence, assumptions, and conclusions distinct. Classify the result as
`approved`, `approved_with_limitations`, `revision_required`, or `blocked` and ask
for researcher judgment on unresolved consequential assumptions.

Do not advance the stage merely because execution succeeded. First run the
provider-neutral `scripts/codex/validate_handoff.py` against the recorded JSON and
the expected specialist/session identity, then perform the scientific checks above;
machine-valid structure is not scientific validity. Record an accepted outcome in
`DECISIONS.md` and `CURRENT_STATE.md` only after researcher approval.
