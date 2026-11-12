from __future__ import annotations

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.data.vendor_lock import (
    UPSTREAM_COMMIT,
    VENDOR_ROOT,
    VENDORED_SKILLS,
    verify_lock,
)

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / VENDOR_ROOT


class VendorTests(unittest.TestCase):
    def test_all_skills_present(self):
        self.assertEqual(len(VENDORED_SKILLS), 10)
        for name in VENDORED_SKILLS:
            skill = ROOT / name / "SKILL.md"
            self.assertTrue(skill.is_file(), name)
            match = re.search(r"^name:\s*(\S+)\s*$", skill.read_text(encoding="utf-8"), re.M)
            self.assertIsNotNone(match, name)
            self.assertEqual(match.group(1).strip("\"'"), name)

    def test_lock_verifies(self):
        self.assertEqual(verify_lock(ROOT), [])

    def test_tampered_file_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "vendor"
            shutil.copytree(ROOT, copy)
            with (copy / "depmap/SKILL.md").open("ab") as handle:
                handle.write(b"x")
            errors = verify_lock(copy)
        self.assertEqual(len(errors), 1)
        self.assertIn("depmap/SKILL.md", errors[0])

    def test_pydeseq2_modification_recorded(self):
        rel = "pydeseq2/scripts/run_deseq2_analysis.py"
        lock = json.loads((ROOT / "VENDOR.lock.json").read_text(encoding="utf-8"))
        self.assertIn(rel, lock["modified"])
        self.assertEqual(lock["commit"], UPSTREAM_COMMIT)
        text = (ROOT / rel).read_text(encoding="utf-8")
        self.assertIn("# Local modification (agentic_system_for_modelling, 2026-11-12)", text)

    def test_notices_cover_every_skill(self):
        text = (REPO / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        for needle in (
            *VENDORED_SKILLS,
            "CC-BY-4.0",
            "Kuan-lin Huang",
            "2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5",
            "Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents",
        ):
            self.assertIn(needle, text)

    def test_bsd_license_texts_present(self):
        text = (REPO / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        self.assertIn("Redistribution and use in source and binary forms", text)
        self.assertIn("Neither the name of", text)
        self.assertIn("Copyright (c) 2025 K-Dense Inc.", text)
        self.assertIn("BSD 2-Clause License", text)
        self.assertIn("BSD 3-Clause License", text)

    def test_not_under_skill_discovery(self):
        for base in (".claude/skills", "skills"):
            for name in VENDORED_SKILLS:
                self.assertFalse((REPO / base / name).exists(), f"{base}/{name}")


if __name__ == "__main__":
    unittest.main()
