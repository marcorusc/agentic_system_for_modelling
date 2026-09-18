# Phase 2 — ODE contract decisions

## D1: provisional bundle preservation — accepted 2026-09-18

**Researcher decision:** “yes let's do this.” This answers the proposal to save provisional ODE bundles automatically within an already approved workflow, while requiring researcher approval to accept scientific assumptions or advance the modelling stage.

### Agreed behavior

| Operation | Authority and meaning |
|---|---|
| Save a provisional candidate bundle | Permitted within an already authorized workflow; preserves a candidate for review and recovery |
| Verify files, hashes, session, revision and provenance | Required for a verified candidate as well as an accepted result |
| Accept proposed scientific assumptions or the selected model | Requires researcher approval with the applicable scope and exact model revision |
| Advance a scientific stage or make a conclusive handoff | Existing researcher approval and validated handoff gates still apply |

The existing task must already authorize the drafting or modelling operations used to create the candidate. Automatic preservation adds no authority for new topology, numerical values, simulation scenarios, or otherwise unapproved modelling work.

A saved bundle is not proof of scientific acceptance, successful simulation, or biological validity. A provisional bundle must remain visibly provisional and must not turn the scientific session registry's handoff status into `exported`. A physical ZIP export and a conclusive scientific handoff are separate facts.

### Implementation requirements

1. Represent artifact preservation independently from scientific acceptance. Choose explicit versioned fields with the final contract decision; do not silently reinterpret historical `export_status` values.
2. Verify any bundle claimed as preserved: approved project location, session/revision ownership, complete revision inventory, hashes, safe ZIP members and required reproduction files. Pending approval must not bypass these checks.
3. Preserve exact-revision approval checks for scientific acceptance, including the immutable decision snapshot and consistency with the orchestrator's decision record. Approval for one revision does not apply to an edited revision.
4. Preserve source and upstream lineage. This decision does not change the approval requirements for NeKo topology export or input selection.
5. Record technical capture failures as technical failures, retaining recoverable artifacts. Do not request new scientific approval merely because a copy or report-writing step failed.
6. Update the ODE workflow instructions and tests consistently when the integrated contract is implemented. Do not change the existing Boolean/PhysiCell contracts as a side effect.

### Source checks informing the implementation

Inspected immutable source `1e8f9a43c4fc249e43d94c71316fc798ee7ad01d` (`ODE-specialist`):

- `docs/ode-workflow.md`, workflow step 7 and specialist-interface table: `export_model_bundle` follows approval; `export_status` currently combines pending, approved and exported.
- `scripts/codex/ode_artifacts.py`, `validate_completion`: exact session/revision approval is checked for approved/exported status, while ZIP integrity is checked only for exported status. The new separation must preserve both checks in their appropriate circumstances.
- `scripts/codex/validate_handoff.py`: `needs_approval` validates ODE metadata, while complete artifact verification currently runs only for `completed`. A preserved candidate must not become a shortcut around artifact verification.
- `tests/codex/test_ode_integration.py`, `test_export_requires_matching_revision_approval_and_bundle`: retain wrong-revision rejection while adding positive provisional-preservation coverage and negative provisional-integrity cases.

These are design requirements, not a claim that the new behavior is already implemented. Runtime integration remains governed by the phase plan.

## D2: canonical contract and historical compatibility — pending

**Recommendation:** use the dedicated ODE branch's `ode_modeler` role, `biomass_ode` stage, and `runs/ode-modeler/` artifact root for new work, with an explicit contract version for the revised semantics. Leave the existing cell-cycle experiment and its `ode_dynamics_modeler` records unchanged and verifiable with their original code revision.

**Decision requested:** must the new runtime directly accept the older experiment handoffs now, or can those records remain historical inputs to their original verifier? Immediate compatibility requires explicit format discrimination and additional tests; it must never weaken the new integrity requirements or imply that historical artifacts passed checks they did not undergo.

The recommendation preserves historical artifacts and defers an adapter until needed. It does not delete data or rewrite old evidence. The exact version field and migration behavior will follow the approved choice.

## Status

D1 is accepted. D2 is awaiting the researcher. Phase 2 implementation is not complete; no routing, scientific record, specialist profile or dependency change accompanies this decision record.
