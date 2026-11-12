from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.codex.validate_handoff import HandoffValidationError, validate_handoff
from scripts.data import manifest, session
from scripts.data.common import session_dir
from scripts import state


class DataHandoffTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        patcher = mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(self.root)})
        patcher.start()
        self.addCleanup(patcher.stop)
        (self.root / "DECISIONS.md").write_text("x\n", encoding="utf-8")
        (self.root / "setup").mkdir()
        (self.root / "setup" / "data-requirements.lock").write_text("pkg==1\n", encoding="utf-8")
        self.sid, _ = session.new_session(self.root, "t", None)
        self.dir = session_dir(self.root, self.sid)
        (self.dir / "outputs" / "de.csv").write_text("gene,padj\nA,0.01\n", encoding="utf-8")
        (self.dir / "outputs" / "index.json").write_text(json.dumps([
            {"path": "outputs/de.csv", "description": "DE", "units": {"padj": "dimensionless"},
             "identifiers": "HGNC symbol"}]), encoding="utf-8")
        (self.dir / "report.md").write_text("# Report\n", encoding="utf-8")
        self.write_integrity(True)

    def write_integrity(self, passed):
        (self.dir / "integrity.json").write_text(json.dumps({
            "schema_version": 1, "session_id": self.sid, "invocation_id": "a1",
            "checked_at": "2026-11-12T00:00:00+00:00", "passed": passed,
            "changed": [] if passed else ["DECISIONS.md"], "identity_intact": True}), encoding="utf-8")

    def add_proposal(self):
        (self.dir / "proposals" / "P1_seed_genes.csv").write_text("gene\nA\n", encoding="utf-8")
        (self.dir / "proposals" / "index.json").write_text(json.dumps([
            {"id": "P1", "target_layer": "neko", "kind": "seed_genes",
             "path": "proposals/P1_seed_genes.csv", "method": "m", "thresholds": {}}]), encoding="utf-8")

    def handoff(self, status="completed", decisions=()):
        manifest.build(self.root, self.sid, [])
        base = f"runs/data-analyst/{self.sid}"
        names = ["manifest.json", "report.md", "outputs/de.csv"]
        artifacts = [{"path": f"{base}/{n}",
                      "sha256": hashlib.sha256((self.root / base / n).read_bytes()).hexdigest()}
                     for n in names]
        return {"schema_version": 1, "specialist": "data_analyst", "status": status, "stage": "data",
                "session_id": self.sid, "derived_from_session_id": None, "actions": ["analysed"],
                "assumptions": [], "decisions_required": list(decisions), "artifacts": artifacts,
                "validation": {"checks": ["manifest verified"], "passed": True},
                "recommended_next_stage": None if status == "needs_approval" else "researcher_approval"}

    def check(self, payload):
        return validate_handoff(payload, project_root=self.root, expected_specialist="data_analyst")

    def test_valid_data_handoff_accepted(self):
        self.check(self.handoff())

    def test_proposals_require_needs_approval(self):
        self.add_proposal()
        with self.assertRaisesRegex(HandoffValidationError, "proposals require needs_approval"):
            self.check(self.handoff())

    def test_needs_approval_with_proposals_accepted(self):
        self.add_proposal()
        self.check(self.handoff("needs_approval", ["approve P1?"]))

    def test_needs_approval_requires_decision_per_proposal(self):
        self.add_proposal()
        with self.assertRaisesRegex(HandoffValidationError, "decision"):
            self.check(self.handoff("needs_approval", []))

    def test_failed_integrity_rejected(self):
        self.write_integrity(False)
        with self.assertRaisesRegex(HandoffValidationError, "integrity"):
            self.check(self.handoff())

    def test_missing_integrity_rejected(self):
        payload = self.handoff()
        (self.dir / "integrity.json").unlink()
        with self.assertRaisesRegex(HandoffValidationError, "integrity"):
            self.check(payload)

    def test_manifest_error_rejected(self):
        payload = self.handoff()
        data = json.loads((self.dir / "manifest.json").read_text())
        data["stage"] = "bogus"
        (self.dir / "manifest.json").write_text(json.dumps(data))
        payload["artifacts"][0]["sha256"] = hashlib.sha256((self.dir / "manifest.json").read_bytes()).hexdigest()
        with self.assertRaisesRegex(HandoffValidationError, "manifest"):
            self.check(payload)

    def test_completed_requires_output_artifact(self):
        payload = self.handoff()
        payload["artifacts"] = payload["artifacts"][:2]
        with self.assertRaisesRegex(HandoffValidationError, "outputs/ or proposals/"):
            self.check(payload)

    def test_state_registry_accepts_data_analyst(self):
        self.assertEqual(state.ROLES["data-analyst"], "data")


if __name__ == "__main__":
    unittest.main()
