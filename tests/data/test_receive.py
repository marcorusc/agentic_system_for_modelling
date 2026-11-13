from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from scripts.capture.record_invocation import record
from scripts.codex.validate_handoff import validate_handoff
from scripts.data import handoff, manifest, receive, session
from scripts.data.common import session_dir, sha256_file
from tests.data.test_record_invocation_data import transcript_events

AID = "a1b2c3"


class ReceiveTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name).resolve()
        self.root, self.troot = base / "my_project", base / "projects"
        self.root.mkdir()
        self.troot.mkdir()
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
        self.dir = session_dir(self.root, self.sid)
        (self.dir / "proposals" / "P1_seed_genes.csv").write_text("gene\nA\n", encoding="utf-8")
        (self.dir / "proposals" / "index.json").write_text(json.dumps([{
            "id": "P1", "target_layer": "neko", "kind": "seed_genes",
            "path": "proposals/P1_seed_genes.csv", "method": "padj", "thresholds": {"padj": 0.05}}]),
            encoding="utf-8")
        manifest.build(self.root, self.sid, [])
        (self.dir / "handoff_notes.json").write_text("{}", encoding="utf-8")
        handoff.build(self.root, self.sid, "needs_approval", "handoff_notes.json")
        self.transcript = self.place_transcript("uuid-1")

    def place_transcript(self, main_session, handoff_line=None):
        directory = self.troot / receive.project_slug(self.root) / main_session / "subagents"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"agent-{AID}.jsonl"
        path.write_text("".join(json.dumps(e) + "\n" for e in self.events(handoff_line)), encoding="utf-8")
        return path

    def events(self, handoff_line=None):
        """The session.py new call, then the final report ending in the Handoff line."""
        rel = f"runs/data-analyst/{self.sid}/handoff.json"
        if handoff_line is None:
            handoff_line = f"Handoff: {rel} sha256={sha256_file(self.root / rel)}"
        report = f"# Report\n\nDone.\n\n{handoff_line}".rstrip()
        return transcript_events(self.sid, self.digest) + [
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": "t9", "name": "SubagentHandback", "input": {"message": report}}]}}]

    def hook_record(self):
        record(self.root, {"agent_type": "data-analyst", "agent_id": AID,
                           "agent_transcript_path": str(self.transcript)})

    def test_receive_happy_path(self):
        self.hook_record()
        result = receive.receive(self.root, self.sid, AID, self.troot)
        self.assertFalse(result["recovered"])
        self.assertEqual([r["id"] for r in result["rows"]], ["P1"])
        self.assertEqual(result["rows"][0]["layer"], "neko")

    def test_cli_prints_table_and_received(self):
        self.hook_record()
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = receive.main(["--session", self.sid, "--agent-id", AID, "--transcript-root", str(self.troot)])
        self.assertEqual(code, 0, err.getvalue())
        lines = out.getvalue().splitlines()
        self.assertTrue(lines[0].startswith("P1 | seed_genes | neko | "))
        self.assertEqual(lines[-1], f"RECEIVED {self.sid} OK")

    def test_completed_handoff_end_to_end(self):
        """C1: handoff.py completed (outputs only) -> recorder -> validate_handoff and receive.py."""
        (self.dir / "proposals" / "P1_seed_genes.csv").unlink()
        (self.dir / "proposals" / "index.json").write_text("[]", encoding="utf-8")
        (self.dir / "outputs" / "de.csv").write_text("gene,padj\nA,0.01\n", encoding="utf-8")
        (self.dir / "outputs" / "index.json").write_text(json.dumps([{
            "path": "outputs/de.csv", "description": "DE", "units": {"padj": "dimensionless"},
            "identifiers": "HGNC symbol"}]), encoding="utf-8")
        manifest.build(self.root, self.sid, [])
        path, _ = handoff.build(self.root, self.sid, "completed", "handoff_notes.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["status"], "completed")
        self.assertNotIn("report.md", " ".join(a["path"] for a in data["artifacts"]))
        self.place_transcript("uuid-1")
        self.hook_record()
        validate_handoff(data, project_root=self.root, expected_specialist="data_analyst",
                         expected_session_id=self.sid)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = receive.main(["--session", self.sid, "--agent-id", AID, "--transcript-root", str(self.troot)])
        self.assertEqual(code, 0, err.getvalue())
        self.assertEqual(out.getvalue().splitlines()[-1], f"RECEIVED {self.sid} OK")

    def test_wrong_agent_id_never_records_another_session(self):
        """I2: an --agent-id whose transcript binds an earlier session must not touch it."""
        self.hook_record()
        receive.receive(self.root, self.sid, AID, self.troot)
        earlier = (self.dir / "integrity.json").read_bytes()
        (self.root / "DECISIONS.md").write_text("changed after the earlier run\n", encoding="utf-8")
        sid2, _ = session.new_session(self.root, "y", None)
        with self.assertRaisesRegex(ValueError, f"binds data session {self.sid}, not {sid2}.*--agent-id"):
            receive.receive(self.root, sid2, AID, self.troot)
        self.assertEqual((self.dir / "integrity.json").read_bytes(), earlier)
        with mock.patch("scripts.capture.recover.record") as recorder:
            with self.assertRaises(ValueError):
                receive.receive(self.root, sid2, AID, self.troot)
            recorder.assert_not_called()
        self.assertFalse((session_dir(self.root, sid2) / "invocation").exists())

    def test_transcript_without_session_refused(self):
        self.transcript.write_text("", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "binds no data session"):
            receive.receive(self.root, self.sid, AID, self.troot)
        self.assertFalse((self.dir / "invocation").exists())

    def test_cli_prints_handoff_status(self):
        self.hook_record()
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = receive.main(["--session", self.sid, "--agent-id", AID, "--transcript-root", str(self.troot)])
        self.assertEqual(code, 0, err.getvalue())
        self.assertEqual(out.getvalue().splitlines()[-2], "Handoff status: needs_approval")
        self.assertEqual(receive.receive(self.root, self.sid, AID, self.troot)["status"], "needs_approval")

    def test_note_decision_artifact_path_shown(self):
        (self.dir / "outputs" / "volcano.png").write_bytes(b"png")
        (self.dir / "outputs" / "index.json").write_text(json.dumps([{
            "path": "outputs/volcano.png", "description": "volcano plot", "units": {},
            "identifiers": "HGNC symbol"}]), encoding="utf-8")
        manifest.build(self.root, self.sid, [])
        (self.dir / "handoff_notes.json").write_text(json.dumps({"decisions": [
            {"id": "D1", "question": "accept?", "artifact": "outputs/volcano.png"}]}), encoding="utf-8")
        handoff.build(self.root, self.sid, "needs_approval", "handoff_notes.json")
        self.place_transcript("uuid-1")
        self.hook_record()
        rows = {r["id"]: r for r in receive.receive(self.root, self.sid, AID, self.troot)["rows"]}
        self.assertEqual(rows["D1"]["path"], f"runs/data-analyst/{self.sid}/outputs/volcano.png")
        self.assertEqual(rows["D1"]["sha256"], sha256_file(self.dir / "outputs" / "volcano.png")[:12])

    def test_missing_handoff_line_fails(self):
        self.place_transcript("uuid-1", handoff_line="")
        self.hook_record()
        with self.assertRaisesRegex(ValueError, "does not end with the `Handoff: "):
            receive.receive(self.root, self.sid, AID, self.troot)

    def test_mismatched_handoff_line_fails(self):
        rel = f"runs/data-analyst/{self.sid}/handoff.json"
        self.place_transcript("uuid-1", handoff_line=f"Handoff: {rel} sha256={'0' * 64}")
        self.hook_record()
        with self.assertRaisesRegex(ValueError, "differs from handoff.json"):
            receive.receive(self.root, self.sid, AID, self.troot)

    def test_handoff_rebuilt_after_final_message_fails(self):
        self.hook_record()
        (self.dir / "handoff_notes.json").write_text(json.dumps({"actions": ["later"]}), encoding="utf-8")
        handoff.build(self.root, self.sid, "needs_approval", "handoff_notes.json")
        with self.assertRaisesRegex(ValueError, "differs from handoff.json"):
            receive.receive(self.root, self.sid, AID, self.troot)

    def test_recovers_missing_capture(self):
        self.assertFalse((self.dir / "integrity.json").exists())
        result = receive.receive(self.root, self.sid, AID, self.troot)
        self.assertTrue(result["recovered"])
        self.assertTrue((self.dir / "integrity.json").is_file())

    def test_recovers_when_index_registration_missing(self):
        with mock.patch("scripts.capture.record_invocation.register_capture", side_effect=ValueError("boom")):
            with self.assertRaises(ValueError):
                self.hook_record()
        result = receive.receive(self.root, self.sid, AID, self.troot)
        self.assertTrue(result["recovered"])

    def test_no_transcript_match_fails(self):
        self.transcript.unlink()
        with self.assertRaisesRegex(ValueError, "no transcript"):
            receive.receive(self.root, self.sid, AID, self.troot)

    def test_two_transcript_matches_fail(self):
        self.place_transcript("uuid-2")
        with self.assertRaisesRegex(ValueError, "exactly one"):
            receive.receive(self.root, self.sid, AID, self.troot)

    def test_project_slug_with_underscores(self):
        self.assertEqual(receive.project_slug(Path("/home/a_b/c-d.e")), "-home-a-b-c-d-e")

    def test_invalid_agent_id_rejected(self):
        for bad in ("../x", "a/b", "", "a" * 129, "a b"):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "agent id"):
                receive.receive(self.root, self.sid, bad, self.troot)

    def test_invalid_handoff_fails(self):
        self.hook_record()
        (self.dir / "proposals" / "P1_seed_genes.csv").write_text("gene\nTAMPERED\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            receive.receive(self.root, self.sid, AID, self.troot)

    def test_default_transcript_root(self):
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": "/cfg"}):
            self.assertEqual(receive.default_transcript_root(), Path("/cfg/projects"))


if __name__ == "__main__":
    unittest.main()
