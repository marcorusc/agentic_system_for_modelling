from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.codex.launcher_config import validate_session_id
from scripts.data import session, snapshot
from scripts.data.common import SESSION_RE

REPO = Path(__file__).resolve().parents[2]
SESSION_PY = REPO / "scripts" / "data" / "session.py"


class SessionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        patcher = mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(self.root)})
        patcher.start()
        self.addCleanup(patcher.stop)
        (self.root / "DECISIONS.md").write_text("original\n", encoding="utf-8")

    def run_new(self, *extra):
        return subprocess.run(
            [sys.executable, str(SESSION_PY), "new", "--purpose", "test purpose", *extra],
            env=os.environ.copy(),
            capture_output=True,
            text=True,
        )

    def new_session(self):
        proc = self.run_new()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        last = proc.stdout.strip().splitlines()[-1]
        match = re.fullmatch(
            r"Data session created: (\S+) \(snapshot sha256=([0-9a-f]{64})\)", last
        )
        self.assertIsNotNone(match, last)
        return match.group(1), match.group(2)

    def test_new_session_layout_and_id(self):
        sid, digest = self.new_session()
        self.assertRegex(sid, SESSION_RE)
        self.assertRegex(sid, r"\Adata-\d{8}T\d{6}Z-[0-9a-f]{8}\Z")
        self.assertEqual(validate_session_id(sid), sid)
        base = self.root / "runs" / "data-analyst" / sid
        for sub in ("scripts", "raw", "outputs", "proposals"):
            self.assertTrue((base / sub).is_dir(), sub)
        identity = json.loads((base / "identity.json").read_text(encoding="utf-8"))
        self.assertEqual(identity["schema_version"], 1)
        self.assertEqual(identity["session_id"], sid)
        self.assertEqual(identity["purpose"], "test purpose")
        self.assertTrue(identity["created_at"].endswith("+00:00"))
        self.assertIsNone(identity["derived_from_session_id"])
        self.assertIn("DECISIONS.md", identity["protected_snapshot"])
        self.assertEqual(
            session.snapshot_digest(identity["protected_snapshot"]), digest
        )

    def test_snapshot_excludes_heavy_and_own_dirs(self):
        for rel in (".git/x", ".venv-data/x", "data-cache/x", "a/__pycache__/x"):
            p = self.root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("x", encoding="utf-8")
        sid, _ = self.new_session()
        snap = json.loads(
            (self.root / "runs/data-analyst" / sid / "identity.json").read_text()
        )["protected_snapshot"]
        self.assertIn("DECISIONS.md", snap)
        for rel in snap:
            self.assertFalse(
                rel.startswith((".git/", ".venv-data/", "data-cache/"))
                or "__pycache__" in rel
                or rel.startswith(f"runs/data-analyst/{sid}/"),
                rel,
            )

    def test_tamper_detected(self):
        sid, digest = self.new_session()
        (self.root / "DECISIONS.md").write_text("tampered\n", encoding="utf-8")
        result = snapshot.verify_session(self.root, sid, digest)
        self.assertFalse(result["passed"])
        self.assertEqual(result["changed"], ["DECISIONS.md"])
        self.assertTrue(result["identity_intact"])

    def test_clean_verify_passes(self):
        sid, digest = self.new_session()
        result = snapshot.verify_session(self.root, sid, digest)
        self.assertEqual(result, {"passed": True, "changed": [], "identity_intact": True})

    def test_identity_rewrite_detected(self):
        sid, digest = self.new_session()
        path = self.root / "runs/data-analyst" / sid / "identity.json"
        identity = json.loads(path.read_text())
        identity["protected_snapshot"] = {}
        path.write_text(json.dumps(identity), encoding="utf-8")
        result = snapshot.verify_session(self.root, sid, digest)
        self.assertFalse(result["identity_intact"])
        self.assertFalse(result["passed"])

    def test_symlink_recorded_and_diff(self):
        (self.root / "link").symlink_to("DECISIONS.md")
        snap = snapshot.take(self.root, "data-x")
        self.assertEqual(snap["link"], "symlink:DECISIONS.md")
        after = dict(snap)
        after["new"] = "1"
        del after["link"]
        after["DECISIONS.md"] = "0"
        self.assertEqual(snapshot.diff(snap, after), ["DECISIONS.md", "link", "new"])

    def test_derived_from_must_exist(self):
        proc = self.run_new("--derived-from", "data-20200101T000000Z-deadbeef")
        self.assertNotEqual(proc.returncode, 0)
        proc = self.run_new("--derived-from", "../etc")
        self.assertNotEqual(proc.returncode, 0)
        sid, _ = self.new_session()
        proc = self.run_new("--derived-from", sid)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        new_id = re.search(r"created: (\S+)", proc.stdout).group(1)
        identity = json.loads(
            (self.root / "runs/data-analyst" / new_id / "identity.json").read_text()
        )
        self.assertEqual(identity["derived_from_session_id"], sid)


if __name__ == "__main__":
    unittest.main()
