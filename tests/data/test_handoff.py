from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from scripts.data import handoff, manifest, session
from scripts.data.common import session_dir


class HandoffTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        patcher = mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(self.root)})
        patcher.start()
        self.addCleanup(patcher.stop)
        (self.root / "DECISIONS.md").write_text("original\n", encoding="utf-8")
        (self.root / "setup").mkdir()
        (self.root / "setup" / "data-requirements.lock").write_text("pkg==1\n", encoding="utf-8")
        self.sid, _ = session.new_session(self.root, "test", None)
        self.dir = session_dir(self.root, self.sid)
        self.prefix = f"runs/data-analyst/{self.sid}"

    def write_json(self, rel, data):
        (self.dir / rel).write_text(json.dumps(data), encoding="utf-8")

    def add_outputs(self):
        (self.dir / "scripts" / "01_de.py").write_text("print(1)\n", encoding="utf-8")
        (self.dir / "outputs" / "de.csv").write_text("gene,padj\nA,0.01\n", encoding="utf-8")
        self.write_json("outputs/index.json", [{
            "path": "outputs/de.csv", "description": "DE", "units": {"padj": "dimensionless"},
            "identifiers": "HGNC symbol"}])

    def add_proposal(self):
        (self.dir / "proposals" / "P1_seed_genes.csv").write_text("gene\nA\n", encoding="utf-8")
        self.write_json("proposals/index.json", [{
            "id": "P1", "target_layer": "neko", "kind": "seed_genes",
            "path": "proposals/P1_seed_genes.csv", "method": "padj", "thresholds": {"padj": 0.05}}])

    def finish(self, notes=None, status="completed", build=True):
        if build:
            manifest.build(self.root, self.sid, [])
        self.write_json("handoff_notes.json", notes if notes is not None else {})
        return handoff.build(self.root, self.sid, status, "handoff_notes.json")

    def load(self):
        return json.loads((self.dir / "handoff.json").read_text(encoding="utf-8"))

    def sha(self, rel):
        return hashlib.sha256((self.dir / rel).read_bytes()).hexdigest()

    def test_needs_approval_with_proposals(self):
        self.add_outputs()
        self.add_proposal()
        path, digest = self.finish({"actions": ["a"], "validation_checks": ["extra"]}, "needs_approval")
        data = self.load()
        self.assertEqual(path, self.dir / "handoff.json")
        self.assertEqual(digest, self.sha("handoff.json"))
        self.assertIs(type(data["schema_version"]), int)
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual((data["specialist"], data["stage"]), ("data_analyst", "data"))
        self.assertEqual(data["session_id"], self.sid)
        self.assertIsNone(data["derived_from_session_id"])
        self.assertIsNone(data["recommended_next_stage"])
        paths = [a["path"] for a in data["artifacts"]]
        self.assertEqual(paths, [f"{self.prefix}/{r}" for r in (
            "manifest.json", "outputs/index.json", "proposals/index.json",
            "scripts/01_de.py", "outputs/de.csv", "proposals/P1_seed_genes.csv")])
        for art in data["artifacts"]:
            self.assertEqual(art["sha256"], self.sha(art["path"][len(f"runs/data-analyst/{self.sid}/"):]))
        (decision,) = data["decisions_required"]
        self.assertEqual(decision, {
            "id": "P1", "kind": "seed_genes", "target_layer": "neko",
            "path": f"{self.prefix}/proposals/P1_seed_genes.csv",
            "sha256": self.sha("proposals/P1_seed_genes.csv"),
            "question": "Approve, edit or reject seed_genes for neko"})
        self.assertEqual(data["validation"]["checks"][:2], ["manifest.py verify: passed", "extra"])
        self.assertTrue(data["validation"]["passed"])
        self.assertNotIn("handoff.json", " ".join(paths))

    def test_completed_without_proposals(self):
        self.add_outputs()
        self.finish({}, "completed")
        data = self.load()
        self.assertEqual(data["status"], "completed")
        self.assertEqual(data["decisions_required"], [])
        self.assertTrue(data["validation"]["passed"])

    def test_completed_with_proposals_refused(self):
        self.add_outputs()
        self.add_proposal()
        with self.assertRaisesRegex(ValueError, "needs_approval"):
            self.finish({}, "completed")
        self.assertFalse((self.dir / "handoff.json").exists())

    def test_blocked_with_outputs_refused(self):
        self.add_outputs()
        with self.assertRaisesRegex(ValueError, "blocked"):
            self.finish({"blocked": [{"what": "w", "why": "y", "remediation": "r"}]}, "blocked")

    def test_blocked_items_become_decisions(self):
        self.finish({"decisions": [{"id": "D1", "question": "q?"}],
                     "blocked": [{"what": "w1", "why": "y1", "remediation": "r1"},
                                 {"what": "w2", "why": "y2", "remediation": "r2"}]}, "blocked")
        data = self.load()
        self.assertEqual(data["decisions_required"], [
            {"id": "D1", "question": "q?"},
            {"id": "B1", "question": "w1 — y1; remediation: r1"},
            {"id": "B2", "question": "w2 — y2; remediation: r2"}])
        self.assertFalse(data["validation"]["passed"])

    def test_blocked_without_reason_refused(self):
        """G10: blocked needs a blocked item or a decision so the researcher sees why."""
        with self.assertRaisesRegex(ValueError, "status blocked needs a blocked item or a decision"):
            self.finish({}, "blocked")
        self.assertFalse((self.dir / "handoff.json").exists())

    def test_blocked_with_only_decision_accepted(self):
        self.finish({"decisions": [{"id": "D1", "question": "which release?"}]}, "blocked")
        self.assertEqual(self.load()["decisions_required"], [{"id": "D1", "question": "which release?"}])

    def test_needs_approval_without_proposals_accepted(self):
        """F4: notes decisions or blocked items alone justify needs_approval."""
        self.add_outputs()
        self.finish({"decisions": [{"id": "D1", "question": "accept the figure?"}]}, "needs_approval")
        self.assertEqual([d["id"] for d in self.load()["decisions_required"]], ["D1"])
        self.finish({"blocked": [{"what": "w", "why": "y", "remediation": "r"}]}, "needs_approval")
        self.assertEqual([d["id"] for d in self.load()["decisions_required"]], ["B1"])

    def test_needs_approval_without_anything_refused(self):
        self.add_outputs()
        with self.assertRaisesRegex(ValueError, "needs_approval needs a proposal, a decision or a blocked item"):
            self.finish({}, "needs_approval")

    def test_completed_with_blocked_items_refused(self):
        """F4: completed is refused while blocked items exist."""
        self.add_outputs()
        with self.assertRaisesRegex(ValueError, "completed needs outputs and no blocked items"):
            self.finish({"blocked": [{"what": "w", "why": "y", "remediation": "r"}]}, "completed")
        self.assertFalse((self.dir / "handoff.json").exists())

    def test_decision_artifact_hashed(self):
        self.add_outputs()
        self.finish({"decisions": [{"id": "D1", "question": "q", "artifact": "outputs/de.csv"}]},
                    "needs_approval")
        d = self.load()["decisions_required"][0]
        self.assertEqual((d["artifact"], d["sha256"]), ("outputs/de.csv", self.sha("outputs/de.csv")))

    def test_stale_manifest_refused(self):
        self.add_outputs()
        manifest.build(self.root, self.sid, [])
        (self.dir / "outputs" / "de.csv").write_text("gene,padj\nA,0.5\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "manifest.py verify failed"):
            self.finish({}, "completed", build=False)

    def test_failed_status_allows_verify_errors(self):
        self.add_outputs()
        manifest.build(self.root, self.sid, [])
        (self.dir / "outputs" / "de.csv").unlink()
        self.finish({}, "failed", build=False)
        data = self.load()
        self.assertFalse(data["validation"]["passed"])
        self.assertTrue(any(c.startswith("manifest.py verify: output outputs/de.csv")
                            for c in data["validation"]["checks"]))
        paths = [a["path"] for a in data["artifacts"]]
        self.assertNotIn(f"{self.prefix}/outputs/de.csv", paths)
        self.assertIn(f"{self.prefix}/manifest.json", paths)

    def test_failed_without_manifest(self):
        self.finish({}, "failed", build=False)
        data = self.load()
        self.assertEqual(data["validation"]["checks"], ["manifest.py verify: manifest.json is missing"])
        self.assertEqual(data["artifacts"], [])

    def test_notes_unknown_key_rejected(self):
        self.add_outputs()
        with self.assertRaisesRegex(ValueError, "unknown notes keys: status"):
            self.finish({"status": "completed"}, "completed")

    def test_notes_bad_decision_id_rejected(self):
        self.add_outputs()
        with self.assertRaisesRegex(ValueError, "decision id"):
            self.finish({"decisions": [{"id": "X1", "question": "q"}]}, "needs_approval")

    def test_notes_artifact_escape_rejected(self):
        self.add_outputs()
        outside = self.root / "secret.txt"
        outside.write_text("s", encoding="utf-8")
        (self.dir / "outputs" / "link.txt").symlink_to(outside)
        for bad in ("../x", str(outside), "outputs/link.txt", "outputs/missing.csv"):
            with self.subTest(artifact=bad):
                with self.assertRaises(ValueError):
                    self.finish({"decisions": [{"id": "D1", "question": "q", "artifact": bad}]},
                                "needs_approval")

    def test_notes_path_escape_rejected(self):
        self.add_outputs()
        manifest.build(self.root, self.sid, [])
        (self.root / "n.json").write_text("{}", encoding="utf-8")
        for bad in ("../../../../n.json", str(self.root / "n.json"), "nope.json"):
            with self.subTest(notes=bad):
                with self.assertRaises(ValueError):
                    handoff.build(self.root, self.sid, "completed", bad)

    def test_last_line_format(self):
        self.add_outputs()
        manifest.build(self.root, self.sid, [])
        self.write_json("handoff_notes.json", {})
        out = io.StringIO()
        with redirect_stdout(out):
            code = handoff.main(["build", "--session", self.sid, "--status", "completed",
                                 "--notes", "handoff_notes.json"])
        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue().splitlines()[-1],
                         f"Handoff written: {self.prefix}/handoff.json sha256={self.sha('handoff.json')}")

    def test_cli_refusal_exits_1(self):
        self.add_outputs()
        manifest.build(self.root, self.sid, [])
        self.write_json("handoff_notes.json", {"bogus": 1})
        err = io.StringIO()
        with redirect_stderr(err):
            code = handoff.main(["build", "--session", self.sid, "--status", "completed",
                                 "--notes", "handoff_notes.json"])
        self.assertEqual(code, 1)
        self.assertIn("unknown notes keys", err.getvalue())


if __name__ == "__main__":
    unittest.main()
