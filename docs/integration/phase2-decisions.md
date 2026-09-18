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

## D2: canonical contract and historical compatibility — accepted 2026-09-18

**Researcher decision:** “Let's use the richer ode_modeler.” This accepts the recommendation for new runs: role `ode_modeler`, stage `biomass_ode`, artifacts under `runs/ode-modeler/`, and an explicitly versioned ODE payload. The corresponding dispatcher entry point is `start_ode_modeler` in Phase 3.

The existing cell-cycle experiment and its `ode_dynamics_modeler` records stay unchanged, verifiable with their original code revision. Immediate ingestion of historical ODE payloads into the new validator is deferred. This preserves the historical evidence without claiming it passed the newer checks.

## Implementation of D1 and D2

The common result envelope remains `schema_version=1`; ODE-specific semantics require `ode.contract_version=2`. Unversioned and other ODE contract versions are rejected rather than silently interpreted as the new format. Existing non-ODE contracts retain their version.

The richer branch's `export_status` gains `provisional`. `pending` identifies work without a preserved bundle or final approval; `provisional` identifies a verified saved candidate under workflow authorization; `approved` records exact-revision conclusive-export approval; `exported` requires that approval and the verified bundle. None of these fields changes the global stage or session registry automatically.

A provisional bundle uses a session-scoped `workflow_authorization` snapshot of the already approved bounded workflow. The orchestrator records this authorization once; it must not ask for a new approval merely to save another candidate in the same scope. This snapshot is separate from the exact-revision `export_approval` required for conclusive export. Validators check consistency of the records, not researcher identity or biological truth.

Integrity verification applies to generated-revision, simulation, approval and bundle claims even when the top-level result is `needs_approval`, `blocked` or `failed`. Metadata-only authoring drafts can still be returned before artifacts have been captured. Technical artifact completion and pending scientific review can coexist.

The imported capture helpers stage and verify all files, then publish the complete directory once under a persistent POSIX lock. Cooperating recorder processes cannot replace an existing capture. Interrupted operations may leave hidden staging files; they do not expose a partial final capture or modify source files. They do not automatically resume, clean up scientific state or rerun modelling operations.

See [ODE artifact contract](../ode-contract.md) for fields, approval records and reproduction commands. Phase 3 will carry these contracts through the shared runtime; Phase 4 will align specialist instructions and setup.

## Status

D1 and D2 are accepted. Phase 2 implementation is complete; [validation results](phase2-validation.md) record the passing suites and independent review fixes. Dispatcher routing, scientific state, installed profiles and dependencies remain unchanged.
