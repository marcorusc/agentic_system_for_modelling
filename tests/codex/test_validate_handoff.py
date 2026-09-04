from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from scripts.codex.validate_handoff import HandoffValidationError, validate_handoff


def handoff_for(specialist: str, stage: str, session: str, derived: str | None):
    run_roots = {
        "network_curator": "runs/network-curator",
        "literature_reviewer": "evidence/reports",
        "boolean_dynamics_modeler": "runs/boolean-dynamics-modeler",
        "multicellular_configurator": "runs/multicellular-configurator",
    }
    return {
        "schema_version": 1,
        "specialist": specialist,
        "status": "completed",
        "stage": stage,
        "session_id": session,
        "derived_from_session_id": derived,
        "actions": ["safe inspection"],
        "assumptions": [],
        "decisions_required": [],
        "artifacts": [f"{run_roots[specialist]}/{session}/report.md"],
        "validation": {"checks": ["artifact path checked"], "passed": True},
        "recommended_next_stage": (
            "literature_review" if specialist == "network_curator" else "researcher_approval"
        ),
    }


class HandoffValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="handoff-validation-")
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_valid_examples_for_all_specialists(self) -> None:
        examples = (
            handoff_for("network_curator", "neko_network", "neko-1", None),
            handoff_for("literature_reviewer", "literature_review", "neko-1", None),
            handoff_for("boolean_dynamics_modeler", "maboss_dynamics", "maboss-1", "neko-1"),
            handoff_for("multicellular_configurator", "physicell_configuration", "pc-1", "maboss-1"),
        )
        for payload in examples:
            with self.subTest(specialist=payload["specialist"]):
                self.assertIs(validate_handoff(payload, project_root=self.root), payload)

    def test_unknown_specialist_and_stage_are_rejected(self) -> None:
        payload = handoff_for("network_curator", "neko_network", "neko-1", None)
        for field, value in (("specialist", "other"), ("stage", "maboss_dynamics")):
            changed = copy.deepcopy(payload)
            changed[field] = value
            with self.subTest(field=field):
                with self.assertRaises(HandoffValidationError):
                    validate_handoff(changed, project_root=self.root)

    def test_missing_lineage_is_rejected_where_required(self) -> None:
        for specialist, stage in (
            ("boolean_dynamics_modeler", "maboss_dynamics"),
            ("multicellular_configurator", "physicell_configuration"),
        ):
            payload = handoff_for(specialist, stage, "session-1", "upstream-1")
            payload["derived_from_session_id"] = None
            with self.subTest(specialist=specialist):
                with self.assertRaisesRegex(HandoffValidationError, "lineage"):
                    validate_handoff(payload, project_root=self.root)

    def test_artifacts_outside_allowed_project_locations_are_rejected(self) -> None:
        payload = handoff_for("network_curator", "neko_network", "neko-1", None)
        for path in (
            "MODEL_SPEC.md",
            "runs/network-curator/other-session/report.md",
            "runs/network-curator/neko-1/../../../outside.md",
            "/tmp/outside.md",
        ):
            changed = copy.deepcopy(payload)
            changed["artifacts"] = [path]
            with self.subTest(path=path):
                with self.assertRaises(HandoffValidationError):
                    validate_handoff(changed, project_root=self.root)

    def test_completed_with_failed_validation_is_rejected(self) -> None:
        payload = handoff_for("network_curator", "neko_network", "neko-1", None)
        payload["validation"]["passed"] = False
        with self.assertRaisesRegex(HandoffValidationError, "completed"):
            validate_handoff(payload, project_root=self.root)

    def test_cross_stage_specialist_mismatch_is_rejected(self) -> None:
        payload = handoff_for("network_curator", "neko_network", "neko-1", None)
        with self.assertRaisesRegex(HandoffValidationError, "requested role"):
            validate_handoff(
                payload,
                project_root=self.root,
                expected_specialist="boolean_dynamics_modeler",
            )

    def test_direct_transition_across_approval_gate_is_rejected(self) -> None:
        cases = (
            ("network_curator", "neko_network", "maboss_dynamics"),
            ("literature_reviewer", "literature_review", "maboss_dynamics"),
            ("boolean_dynamics_modeler", "maboss_dynamics", "physicell_configuration"),
        )
        for specialist, stage, next_stage in cases:
            derived = "upstream-1" if specialist == "boolean_dynamics_modeler" else None
            payload = handoff_for(specialist, stage, "session-1", derived)
            payload["recommended_next_stage"] = next_stage
            with self.subTest(specialist=specialist):
                with self.assertRaisesRegex(HandoffValidationError, "approval gate"):
                    validate_handoff(payload, project_root=self.root)

    def test_blocked_handoff_may_have_no_session_or_artifacts(self) -> None:
        payload = handoff_for("network_curator", "neko_network", "neko-1", None)
        payload.update(
            status="blocked",
            session_id=None,
            artifacts=[],
            recommended_next_stage=None,
        )
        validate_handoff(payload, project_root=self.root)

    def test_needs_approval_requires_a_concrete_decision(self) -> None:
        payload = handoff_for("network_curator", "neko_network", "neko-1", None)
        payload["status"] = "needs_approval"
        payload["recommended_next_stage"] = "researcher_approval"
        with self.assertRaisesRegex(HandoffValidationError, "decisions_required"):
            validate_handoff(payload, project_root=self.root)

    def test_required_fields_are_enforced(self) -> None:
        payload = handoff_for("network_curator", "neko_network", "neko-1", None)
        del payload["actions"]
        with self.assertRaisesRegex(HandoffValidationError, "missing required"):
            validate_handoff(payload, project_root=self.root)


if __name__ == "__main__":
    unittest.main()
