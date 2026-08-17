"""End-to-end tests for the Git-backed model lifecycle."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[2]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ModelLifecycleTest(unittest.TestCase):
    def git(self, root: Path, *arguments: str) -> str:
        result = subprocess.run(
            ["git", *arguments], cwd=root, check=True, text=True, capture_output=True
        )
        return result.stdout.strip()

    def lifecycle(self, root: Path, *arguments: str) -> str:
        result = subprocess.run(
            [sys.executable, ".claude/scripts/model_lifecycle.py", *arguments],
            cwd=root,
            check=True,
            text=True,
            capture_output=True,
        )
        return result.stdout

    def make_repository(self, root: Path) -> None:
        (root / ".claude" / "scripts").mkdir(parents=True)
        (root / ".model" / "manifests").mkdir(parents=True)
        shutil.copy2(
            SOURCE_ROOT / ".claude" / "scripts" / "model_lifecycle.py",
            root / ".claude" / "scripts" / "model_lifecycle.py",
        )
        for name in ("config.json", "state.json", "archives.json"):
            shutil.copy2(SOURCE_ROOT / ".model" / name, root / ".model" / name)
        shutil.copytree(SOURCE_ROOT / "templates", root / "templates")

        config = json.loads((root / ".model" / "config.json").read_text(encoding="utf-8"))
        for destination, template in config["reset_files"].items():
            destination_path = root / destination
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / template, destination_path)
        for directory in config["state_directories"]:
            (root / directory).mkdir(parents=True, exist_ok=True)
            (root / directory / ".gitkeep").touch()
        (root / "inputs").mkdir()
        (root / "inputs" / "observations.tsv").write_text("baseline\n", encoding="utf-8")

        self.git(root, "init")
        self.git(root, "config", "user.name", "Lifecycle Test")
        self.git(root, "config", "user.email", "lifecycle@example.invalid")
        self.git(root, "config", "core.autocrlf", "false")
        self.git(root, "add", "-A")
        self.git(root, "commit", "-m", "test: initialize model repository")

    def test_archive_restart_restore_round_trip(self) -> None:
        with tempfile.TemporaryDirectory(prefix="model-lifecycle-test-") as temporary:
            root = Path(temporary)
            self.make_repository(root)
            script_hash = digest(root / ".claude" / "scripts" / "model_lifecycle.py")
            config_hash = digest(root / ".model" / "config.json")

            (root / "MODEL_SPEC.md").write_text("# Archived model\n", encoding="utf-8")
            (root / "runs" / "result.txt").write_text("stable state\n", encoding="utf-8")
            archived_hash = digest(root / "MODEL_SPEC.md")
            output = self.lifecycle(
                root,
                "archive",
                "original hypothesis",
                "--summary",
                "Original scientific direction.",
            )
            self.assertIn("model/archive/original-hypothesis", output)

            (root / "MODEL_SPEC.md").write_text("# Wrong direction\n", encoding="utf-8")
            (root / "inputs" / "observations.tsv").write_text(
                "user-supplied update\n", encoding="utf-8"
            )
            preview = self.lifecycle(root, "restart")
            self.assertIn("MODEL RESTART PREVIEW", preview)
            self.lifecycle(root, "restart", "--yes")
            self.assertEqual(
                (root / "MODEL_SPEC.md").read_bytes(),
                (root / "templates" / "MODEL_SPEC.md").read_bytes(),
            )
            self.assertFalse((root / "runs" / "result.txt").exists())

            preview = self.lifecycle(root, "restore", "original hypothesis")
            self.assertIn("MODEL RESTORE PREVIEW", preview)
            output = self.lifecycle(root, "restore", "original hypothesis", "--yes")
            self.assertIn("model/archive/original-hypothesis", output)
            self.assertEqual(digest(root / "MODEL_SPEC.md"), archived_hash)
            self.assertEqual(
                (root / "runs" / "result.txt").read_text(encoding="utf-8"),
                "stable state\n",
            )
            self.assertEqual(
                (root / "inputs" / "observations.tsv").read_text(encoding="utf-8"),
                "user-supplied update\n",
            )
            self.assertEqual(digest(root / ".claude" / "scripts" / "model_lifecycle.py"), script_hash)
            self.assertEqual(digest(root / ".model" / "config.json"), config_hash)

            tags = self.git(root, "tag", "--list", "model/*").splitlines()
            self.assertEqual(len(tags), 3)
            self.assertEqual(sum(tag.startswith("model/recovery/") for tag in tags), 2)
            listing = self.lifecycle(root, "list", "--all")
            self.assertIn("original hypothesis [archive]", listing)
            self.assertEqual(
                self.git(root, "status", "--short"),
                "M inputs/observations.tsv",
            )


if __name__ == "__main__":
    unittest.main()
