from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from scripts.capture import recover
from scripts.capture.transcripts import project_slug

ROOT = Path(__file__).resolve().parents[2]
AID = "agent-1"
REPORT = "# Curation report\n\nAll done."


def events(session="sess-1", report=REPORT):
    ev = [{"type": "user", "timestamp": "2026-10-05T00:00:00Z", "message": {"content": "Curate"}}]
    if session:
        ev += [
            {"type": "assistant", "timestamp": "2026-10-05T00:00:01Z", "message": {"id": "one", "usage": {"input_tokens": 1, "output_tokens": 1}, "content": [
                {"type": "tool_use", "id": "call", "name": "mcp__neko-agent__create_session", "input": {}}]}},
            {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "call",
                                                      "content": f"Session created: {session}"}]}},
        ]
    ev.append({"type": "assistant", "timestamp": "2026-10-05T00:00:10Z", "message": {"id": "two", "usage": {"input_tokens": 1, "output_tokens": 1}, "content": [
        {"type": "tool_use", "id": "hand", "name": "SubagentHandback", "input": {"message": report}}]}})
    return ev


class RecoverTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name).resolve()
        self.root, self.troot = base / "proj", base / "projects"
        self.root.mkdir()
        self.troot.mkdir()

    def place(self, main="uuid-1", session="sess-1", aid=AID):
        d = self.troot / project_slug(self.root) / main / "subagents"
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"agent-{aid}.jsonl"
        path.write_text("".join(json.dumps(e) + "\n" for e in events(session)), encoding="utf-8")
        return path

    def run_recover(self, specialist="network-curator", agent=AID, session=None):
        return recover.recover(self.root, specialist, agent, session, self.troot)

    def test_recovers_missing_network_curator_capture(self):
        self.place()
        result = self.run_recover()
        self.assertEqual(result["status"], "recorded")
        self.assertEqual(result["session_id"], "sess-1")
        cap = self.root / result["capture_path"]
        self.assertTrue(cap.is_dir())
        index = json.loads((self.root / "runs/index.json").read_text())
        self.assertTrue(any(r.get("capture_path") == result["capture_path"] for r in index["runs"]))
        report = self.root / "runs/network-curator/sess-1/report.md"
        self.assertEqual(report.read_bytes(), (cap / "final_report.md").read_bytes())

    def test_already_recorded_is_noop(self):
        self.place()
        self.run_recover()
        snap = {p: p.read_bytes() for p in (self.root / "runs").rglob("*") if p.is_file()}
        result = self.run_recover()
        self.assertEqual(result["status"], "already-recorded")
        self.assertEqual(result["session_id"], "sess-1")
        self.assertEqual({p: p.read_bytes() for p in (self.root / "runs").rglob("*") if p.is_file()}, snap)

    def test_session_mismatch_refused_without_recording(self):
        self.place()
        with self.assertRaisesRegex(ValueError, "binds session sess-1, not other.*check --agent-id; nothing was recorded"):
            self.run_recover(session="other")
        self.assertFalse((self.root / "runs").exists())

    def test_session_given_but_none_bound_refused(self):
        self.place(session=None)
        with self.assertRaisesRegex(ValueError, "binds no session"):
            self.run_recover(session="sess-1")
        self.assertFalse((self.root / "runs").exists())

    def test_no_and_two_transcript_matches_fail(self):
        with self.assertRaisesRegex(ValueError, "no transcript"):
            self.run_recover()
        self.place("uuid-1")
        self.place("uuid-2")
        with self.assertRaisesRegex(ValueError, "exactly one"):
            self.run_recover()
        self.assertFalse((self.root / "runs").exists())

    def test_unknown_specialist_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown specialist"):
            self.run_recover(specialist="not-a-specialist")

    def test_bad_agent_id_rejected(self):
        for bad in ("../x", "a/b", "", "a" * 129):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "agent id"):
                self.run_recover(agent=bad)

    def test_unbound_invocation_reported(self):
        self.place(session=None)
        result = self.run_recover()
        self.assertEqual(result["status"], "unbound")
        self.assertIsNone(result["session_id"])
        self.assertTrue((self.root / result["capture_path"]).is_dir())
        self.assertIsNone(result["report_md"])

    def test_cli_last_line_and_exit_codes(self):
        self.place()
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(self.root)}
        cmd = [sys.executable, str(ROOT / "scripts/capture/recover.py"), "--specialist", "network-curator",
               "--agent-id", AID, "--transcript-root", str(self.troot)]
        ok = subprocess.run(cmd, env=env, text=True, capture_output=True)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertEqual(ok.stdout.splitlines()[-1], "RECOVERED network-curator sess-1 recorded")
        again = subprocess.run(cmd, env=env, text=True, capture_output=True)
        self.assertEqual(again.stdout.splitlines()[-1], "RECOVERED network-curator sess-1 already-recorded")
        bad = subprocess.run(cmd[:-3] + ["nope", "--transcript-root", str(self.troot)], env=env, text=True,
                             capture_output=True)
        self.assertEqual(bad.returncode, 1)
        self.assertTrue(bad.stderr.startswith("RECOVER FAILED: "), bad.stderr)
        mismatch = subprocess.run(cmd + ["--session", "other"], env=env, text=True, capture_output=True)
        self.assertEqual(mismatch.returncode, 1)
        self.assertIn("RECOVER FAILED:", mismatch.stderr)

    def test_main_in_process(self):
        self.place()
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.root)
        self.addCleanup(os.environ.pop, "CLAUDE_PROJECT_DIR", None)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = recover.main(["--specialist", "network-curator", "--agent-id", AID,
                                 "--transcript-root", str(self.troot)])
        self.assertEqual(code, 0, err.getvalue())


if __name__ == "__main__":
    unittest.main()
