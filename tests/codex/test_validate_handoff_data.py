from __future__ import annotations

import hashlib
import shutil
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.capture.record_invocation import record
from scripts.codex.validate_handoff import HandoffValidationError, validate_handoff
from scripts.data import manifest, session
from scripts.data.common import session_dir
from scripts import state


class DataHandoffTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name).resolve()
        self.root, self.outside = base / "project", base / "transcripts"
        self.root.mkdir(); self.outside.mkdir()
        patcher = mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(self.root)})
        patcher.start()
        self.addCleanup(patcher.stop)
        (self.root / "DECISIONS.md").write_text("x\n", encoding="utf-8")
        (self.root / "setup").mkdir()
        (self.root / "setup" / "data-requirements.lock").write_text("pkg==1\n", encoding="utf-8")
        (self.root / ".venv-data" / "bin").mkdir(parents=True)
        (self.root / ".venv-data" / "bin" / "python").symlink_to(sys.executable)
        (self.root / "scripts" / "data").mkdir(parents=True)
        (self.root / "scripts" / "data" / "session.py").write_text("")
        self.sid, self.digest = session.new_session(self.root, "t", None)
        self.dir = session_dir(self.root, self.sid)
        (self.dir / "outputs" / "de.csv").write_text("gene,padj\nA,0.01\n", encoding="utf-8")
        (self.dir / "outputs" / "index.json").write_text(json.dumps([
            {"path": "outputs/de.csv", "description": "DE", "units": {"padj": "dimensionless"},
             "identifiers": "HGNC symbol"}]), encoding="utf-8")
        (self.dir / "report.md").write_text("# Report\n", encoding="utf-8")
        manifest.build(self.root, self.sid, [])
        self.record_integrity()

    def record_integrity(self):
        """Produce integrity.json and the indexed invocation record via the real recorder."""
        command = ".venv-data/bin/python -E -s scripts/data/session.py new --purpose x"
        events = [
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": command}}]}},
            {"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "t1",
                 "content": f"Data session created: {self.sid} (snapshot sha256={self.digest})"}]}}]
        path = self.outside / "agent-1.jsonl"
        path.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
        record(self.root, {"agent_type": "data-analyst", "agent_id": "agent-1",
                           "agent_transcript_path": str(path)})

    def write_integrity(self, passed):
        (self.dir / "integrity.json").write_text(json.dumps({
            "schema_version": 1, "session_id": self.sid, "invocation_id": "agent-1",
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
        (self.root / "DECISIONS.md").write_text("tampered\n", encoding="utf-8")
        (self.dir / "integrity.json").unlink()
        shutil.rmtree(self.dir / "invocation")
        (self.root / "runs" / "index.json").unlink()
        self.record_integrity()
        with self.assertRaisesRegex(HandoffValidationError, "integrity"):
            self.check(self.handoff())

    def test_missing_integrity_rejected(self):
        payload = self.handoff()
        (self.dir / "integrity.json").unlink()
        with self.assertRaisesRegex(HandoffValidationError, "integrity"):
            self.check(payload)

    def test_validator_rejects_integrity_without_registered_record(self):
        payload = self.handoff()
        (self.root / "runs" / "index.json").unlink()
        self.write_integrity(True)
        with self.assertRaisesRegex(HandoffValidationError, "registered"):
            self.check(payload)

    def test_validator_rejects_integrity_mismatch_with_record(self):
        payload = self.handoff()
        path = self.dir / "integrity.json"
        data = json.loads(path.read_text())
        data["checked_at"] = "2030-01-01T00:00:00+00:00"
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(HandoffValidationError, "differs"):
            self.check(payload)

    def test_forged_record_with_tamper_rejected(self):
        payload = self.handoff()
        (self.root / "DECISIONS.md").write_text("tampered\n", encoding="utf-8")
        rel = f"runs/data-analyst/{self.sid}/invocation/agent-1"
        forged = (self.root / rel / "invocation.json")
        index = self.root / "runs" / "index.json"
        data = json.loads(index.read_text())
        raw = forged.read_bytes()
        for item in data["runs"]:  # keep the forged record registered with a matching hash
            for artifact in item["artifacts"]:
                if artifact["path"] == rel + "/invocation.json":
                    artifact["sha256"] = hashlib.sha256(raw).hexdigest()
        index.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            self.record_integrity()
        with self.assertRaises(HandoffValidationError):
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
