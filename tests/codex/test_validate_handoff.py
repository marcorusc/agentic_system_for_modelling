from __future__ import annotations

import copy
import hashlib
import json
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

def materialize(root: Path, payload: dict) -> None:
    """Create real stage outputs, including a distinct identity manifest."""
    role = payload["specialist"]
    session = payload["session_id"]
    if role == "literature_reviewer":
        try:
            from .test_literature_report_writer import VALID_REPORT
        except ImportError:  # unittest discovery imports this module at top level.
            from test_literature_report_writer import VALID_REPORT
        base = f"evidence/reports/{session}"
        outputs = {"GAB1__AKT1.md": VALID_REPORT}
    else:
        base = payload["artifacts"][0].rsplit("/", 1)[0]
        identity = {field: payload[field] for field in (
            "schema_version", "specialist", "stage", "session_id", "derived_from_session_id"
        )}
        outputs = {"manifest.json": json.dumps(identity), "report.md": "# Stage report\n"}
        if role == "network_curator":
            outputs.update({"network.sif": "A 1 B\n", "important_paths.md": "A -> B\n",
                            "literature_queue.json": '[["A", 1, "B"]]'})
        elif role == "boolean_dynamics_modeler":
            outputs.update({"model.bnd": "Node A { logic = A; }\n", "model.cfg": "max_time = 1;\n"})
        else:
            outputs["settings.xml"] = "<PhysiCell_settings/>"
    payload["artifacts"] = []
    for name, text in outputs.items():
        path = f"{base}/{name}"
        file = root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text, encoding="utf-8")
        payload["artifacts"].append({"path": path, "sha256": hashlib.sha256(file.read_bytes()).hexdigest()})



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
                materialize(self.root, payload)
                self.assertIs(validate_handoff(payload, project_root=self.root), payload)

    def test_completed_requires_existing_hashed_stage_artifacts(self) -> None:
        for failure in ("empty", "missing", "hash", "missing_hash", "directory", "missing_sif", "manifest_identity"):
            payload = handoff_for("network_curator", "neko_network", "neko-1", None)
            materialize(self.root, payload)
            first = payload["artifacts"][0]
            if failure == "empty":
                payload["artifacts"] = []
            elif failure == "missing":
                first["path"] += ".missing"
            elif failure == "hash":
                first["sha256"] = "0" * 64
            elif failure == "missing_hash":
                del first["sha256"]
            elif failure == "directory":
                first["path"] = "runs/network-curator/neko-1"
            elif failure == "missing_sif":
                payload["artifacts"] = [e for e in payload["artifacts"] if not e["path"].endswith(".sif")]
            else:
                file = self.root / first["path"]
                manifest = json.loads(file.read_text())
                manifest["session_id"] = "wrong-session"
                file.write_text(json.dumps(manifest))
                first["sha256"] = hashlib.sha256(file.read_bytes()).hexdigest()
            with self.subTest(failure=failure):
                with self.assertRaises(HandoffValidationError):
                    validate_handoff(payload, project_root=self.root)

    def test_in_project_artifact_symlink_is_rejected(self) -> None:
        payload = handoff_for("network_curator", "neko_network", "neko-1", None)
        file = self.root / payload["artifacts"][0]
        file.parent.mkdir(parents=True)
        target = self.root / "other.md"
        target.write_text("other session")
        file.symlink_to(target)
        with self.assertRaisesRegex(HandoffValidationError, "symlink"):
            validate_handoff(payload, project_root=self.root)

    def test_drafts_can_reference_not_yet_written_reports(self) -> None:
        payload = handoff_for("literature_reviewer", "literature_review", "neko-1", None)
        payload.update(status="needs_approval", decisions_required=["Persist and verify report drafts"],
                       recommended_next_stage=None)
        validate_handoff(payload, project_root=self.root)

    def test_malformed_enum_types_are_rejected_cleanly(self) -> None:
        for field in ("specialist", "status", "recommended_next_stage"):
            payload = handoff_for("network_curator", "neko_network", "neko-1", None)
            payload[field] = []
            with self.subTest(field=field):
                with self.assertRaises(HandoffValidationError):
                    validate_handoff(payload, project_root=self.root)

    def test_missing_exports_are_rejected_for_downstream_stages(self) -> None:
        for role, stage, extension in (
            ("boolean_dynamics_modeler", "maboss_dynamics", ".cfg"),
            ("multicellular_configurator", "physicell_configuration", ".xml"),
        ):
            payload = handoff_for(role, stage, "session-1", "upstream-1")
            materialize(self.root, payload)
            payload["artifacts"] = [entry for entry in payload["artifacts"]
                                    if not entry["path"].endswith(extension)]
            with self.subTest(role=role):
                with self.assertRaises(HandoffValidationError):
                    validate_handoff(payload, project_root=self.root)

    def test_invalid_export_json_and_xml_are_rejected_even_with_correct_hashes(self) -> None:
        for role, stage, name in (
            ("network_curator", "neko_network", "literature_queue.json"),
            ("multicellular_configurator", "physicell_configuration", "settings.xml"),
        ):
            payload = handoff_for(role, stage, "session-2", "upstream-1")
            materialize(self.root, payload)
            entry = next(e for e in payload["artifacts"] if e["path"].endswith(name))
            file = self.root / entry["path"]
            file.write_text("invalid content", encoding="utf-8")
            entry["sha256"] = hashlib.sha256(file.read_bytes()).hexdigest()
            with self.subTest(role=role):
                with self.assertRaises(HandoffValidationError):
                    validate_handoff(payload, project_root=self.root)

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
        payload["recommended_next_stage"] = None
        with self.assertRaisesRegex(HandoffValidationError, "decisions_required"):
            validate_handoff(payload, project_root=self.root)

    def test_needs_approval_cannot_recommend_a_next_stage(self) -> None:
        payload = handoff_for("network_curator", "neko_network", "neko-1", None)
        payload.update(
            status="needs_approval",
            decisions_required=["Researcher approval is required"],
            recommended_next_stage="researcher_approval",
        )
        with self.assertRaisesRegex(HandoffValidationError, "must recommend null"):
            validate_handoff(payload, project_root=self.root)

    def test_required_fields_are_enforced(self) -> None:
        payload = handoff_for("network_curator", "neko_network", "neko-1", None)
        del payload["actions"]
        with self.assertRaisesRegex(HandoffValidationError, "missing required"):
            validate_handoff(payload, project_root=self.root)


if __name__ == "__main__":
    unittest.main()
