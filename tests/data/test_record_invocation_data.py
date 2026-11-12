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
        record(self.root, payload)
        record(self.root, payload)

    def test_recorder_ignores_unbound_data_invocation(self):
        result = record(self.root, self.payload([], name="agent-2"))
        self.assertEqual(result["status"], "unbound")
        self.assertFalse((session_dir(self.root, self.sid) / "integrity.json").exists())
        self.assertFalse((self.root / "runs" / "index.json").exists())


if __name__ == "__main__":
    unittest.main()
