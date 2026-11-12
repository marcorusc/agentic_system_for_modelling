from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.capture.record_invocation import record
from scripts.data import manifest, session
from scripts.data.common import session_dir


def transcript_events(sid: str, digest: str) -> list[dict]:
    command = ".venv-data/bin/python -E -s scripts/data/session.py new --purpose x"
    return [
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": command}}]}},
        {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t1",
             "content": f"...\nData session created: {sid} (snapshot sha256={digest})"}]}},
    ]


class RecordDataInvocationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name).resolve()
        self.root, self.outside = base / "project", base / "transcripts"
        self.root.mkdir(); self.outside.mkdir()
        patcher = mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(self.root)})
        patcher.start()
        self.addCleanup(patcher.stop)
        (self.root / "DECISIONS.md").write_text("original\n", encoding="utf-8")
        (self.root / "setup").mkdir()
        (self.root / "setup" / "data-requirements.lock").write_text("pkg==1\n", encoding="utf-8")
        (self.root / ".venv-data" / "bin").mkdir(parents=True)
        (self.root / ".venv-data" / "bin" / "python").symlink_to(sys.executable)
        (self.root / "scripts" / "data").mkdir(parents=True)
        (self.root / "scripts" / "data" / "session.py").write_text("")
        self.sid, self.digest = session.new_session(self.root, "x", None)
        manifest.build(self.root, self.sid, [])

    def payload(self, events, name="agent-1"):
        path = self.outside / f"{name}.jsonl"
        path.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
        return {"agent_type": "data-analyst", "agent_id": name, "agent_transcript_path": str(path)}

    def integrity(self):
        return json.loads((session_dir(self.root, self.sid) / "integrity.json").read_text())

    def test_recorder_writes_integrity_clean(self):
        result = record(self.root, self.payload(transcript_events(self.sid, self.digest)))
        self.assertEqual(result["session_id"], self.sid)
        integrity = self.integrity()
        self.assertTrue(integrity["passed"])
        self.assertEqual(integrity["changed"], [])
        self.assertEqual(integrity["invocation_id"], "agent-1")
        invocation = session_dir(self.root, self.sid) / "invocation" / "agent-1" / "invocation.json"
        self.assertEqual(json.loads(invocation.read_text())["integrity"], integrity)

    def test_recorder_writes_integrity_and_detects_tamper(self):
        (self.root / "DECISIONS.md").write_text("tampered\n", encoding="utf-8")
        record(self.root, self.payload(transcript_events(self.sid, self.digest)))
        integrity = self.integrity()
        self.assertFalse(integrity["passed"])
        self.assertEqual(integrity["changed"], ["DECISIONS.md"])
        self.assertTrue(integrity["identity_intact"])

    def test_wrong_digest_marks_identity_not_intact(self):
        record(self.root, self.payload(transcript_events(self.sid, "b" * 64)))
        integrity = self.integrity()
        self.assertFalse(integrity["passed"])
        self.assertFalse(integrity["identity_intact"])

    def test_missing_identity_fails_closed(self):
        (session_dir(self.root, self.sid) / "identity.json").unlink()
        record(self.root, self.payload(transcript_events(self.sid, self.digest)))
        integrity = self.integrity()
        self.assertFalse(integrity["passed"])
        self.assertFalse(integrity["identity_intact"])
        self.assertEqual(integrity["changed"], [])
        self.assertIn("error", integrity)

    def test_retry_is_idempotent(self):
        payload = self.payload(transcript_events(self.sid, self.digest))
        first = record(self.root, payload)
        verdict = self.integrity()
        second = record(self.root, payload)
        self.assertEqual(first, second)
        self.assertEqual(self.integrity(), verdict)
        self.assertTrue(verdict["passed"])

    test_retry_index_only_change_excused = test_retry_is_idempotent

    def test_retry_with_other_change_fails(self):
        payload = self.payload(transcript_events(self.sid, self.digest))
        record(self.root, payload)
        (self.root / "DECISIONS.md").write_text("tampered later\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            record(self.root, payload)
        integrity = self.integrity()
        self.assertFalse(integrity["passed"])
        self.assertIn("verdict changed on retry", integrity["error"])

    def test_retry_after_register_failure_recovers(self):
        payload = self.payload(transcript_events(self.sid, self.digest))
        with mock.patch("scripts.capture.record_invocation.register_capture", side_effect=ValueError("boom")):
            with self.assertRaises(ValueError):
                record(self.root, payload)
        first = self.integrity()
        result = record(self.root, payload)
        self.assertEqual(self.integrity(), first)
        self.assertTrue(first["passed"])
        index = json.loads((self.root / "runs" / "index.json").read_text())
        self.assertEqual(len(index["runs"]), 1)
        self.assertEqual(result["session_id"], self.sid)

    def test_forged_index_does_not_skip_verification(self):
        import hashlib
        (self.root / "DECISIONS.md").write_text("tampered\n", encoding="utf-8")
        forged = {"integrity": {"schema_version": 1, "session_id": self.sid, "invocation_id": "agent-1",
                                "checked_at": "x", "passed": True, "changed": [], "identity_intact": True}}
        rel = f"runs/data-analyst/{self.sid}/invocation/agent-1"
        (self.root / rel).mkdir(parents=True)
        raw = json.dumps(forged).encode()
        (self.root / rel / "invocation.json").write_bytes(raw)
        (self.root / "runs" / "index.json").write_text(json.dumps({"runs": [{
            "capture_path": rel, "artifacts": [{"path": rel + "/invocation.json",
                                                "sha256": hashlib.sha256(raw).hexdigest()}]}]}))
        with self.assertRaises(ValueError):
            record(self.root, self.payload(transcript_events(self.sid, self.digest)))
        integrity = self.integrity()
        self.assertFalse(integrity["passed"])
        self.assertIn("DECISIONS.md", integrity["changed"])

    def test_symlinked_integrity_replaced(self):
        target = self.outside / "elsewhere.json"
        target.write_text("keep")
        (session_dir(self.root, self.sid) / "integrity.json").symlink_to(target)
        record(self.root, self.payload(transcript_events(self.sid, self.digest)))
        self.assertEqual(target.read_text(), "keep")
        self.assertTrue(self.integrity()["passed"])

    def forge(self, invocation="agent-1"):
        (session_dir(self.root, self.sid) / "integrity.json").write_text(json.dumps({
            "schema_version": 1, "session_id": self.sid, "invocation_id": invocation,
            "checked_at": "2026-11-12T00:00:00+00:00", "passed": True, "changed": [],
            "identity_intact": True}), encoding="utf-8")

    def test_forged_integrity_same_invocation_not_reused(self):
        self.forge("agent-1")
        (self.root / "DECISIONS.md").write_text("tampered\n", encoding="utf-8")
        record(self.root, self.payload(transcript_events(self.sid, self.digest)))
        integrity = self.integrity()
        self.assertFalse(integrity["passed"])
        self.assertEqual(integrity["changed"], ["DECISIONS.md"])

    def test_preexisting_integrity_other_invocation_overwritten(self):
        self.forge("someone-else")
        (self.root / "DECISIONS.md").write_text("tampered\n", encoding="utf-8")
        record(self.root, self.payload(transcript_events(self.sid, self.digest)))
        integrity = self.integrity()
        self.assertEqual(integrity["invocation_id"], "agent-1")
        self.assertFalse(integrity["passed"])

    def test_malformed_identity_fails_closed(self):
        self.forge("agent-1")
        path = session_dir(self.root, self.sid) / "identity.json"
        data = json.loads(path.read_text())
        data["protected_snapshot"] = []
        path.write_text(json.dumps(data))
        record(self.root, self.payload(transcript_events(self.sid, self.digest)))
        integrity = self.integrity()
        self.assertFalse(integrity["passed"])
        self.assertFalse(integrity["identity_intact"])
        self.assertIn("error", integrity)

    def test_recorder_ignores_unbound_data_invocation(self):
        result = record(self.root, self.payload([], name="agent-2"))
        self.assertEqual(result["status"], "unbound")
        self.assertFalse((session_dir(self.root, self.sid) / "integrity.json").exists())
        self.assertFalse((self.root / "runs" / "index.json").exists())


if __name__ == "__main__":
    unittest.main()
