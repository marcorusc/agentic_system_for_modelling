from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.codex.cleanup_tasks import (
    cleanup_task_sources,
    consume_recorded_task,
    normalized_task_text,
    prompt_digest,
)


class TaskCleanupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="codex-task-cleanup-")
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def record(self, prompt: str, invocation: str = "invocation-1") -> Path:
        directory = (
            self.root
            / "runs/network-curator/session-1/specialist-invocations"
            / invocation
        )
        directory.mkdir(parents=True)
        (directory / "task.txt").write_text(
            normalized_task_text(prompt), encoding="utf-8"
        )
        (directory / "provenance.json").write_text(
            json.dumps({"prompt_sha256": prompt_digest(prompt)}) + "\n",
            encoding="utf-8",
        )
        return directory

    def task(self, relative: str, prompt: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(prompt, encoding="utf-8")
        return path

    def test_preview_verifies_without_deleting(self) -> None:
        prompt = "inspect the recorded session\n"
        source = self.task(".codex-tasks/inspect.txt", prompt)
        self.record(prompt)

        report = cleanup_task_sources(
            self.root, apply=False, include_git_history=False
        )

        self.assertTrue(source.exists())
        self.assertEqual([item["path"] for item in report["verified"]], [".codex-tasks/inspect.txt"])
        self.assertEqual(report["deleted"], [])
        self.assertEqual(report["unmatched"], [])

    def test_apply_deletes_verified_canonical_and_legacy_tasks(self) -> None:
        canonical_prompt = "canonical task"
        legacy_prompt = "legacy task\n\n"
        canonical = self.task(".codex-tasks/canonical.txt", canonical_prompt)
        legacy = self.task(".codex-task-legacy.txt", legacy_prompt)
        self.record(canonical_prompt, "invocation-1")
        self.record(legacy_prompt, "invocation-2")

        report = cleanup_task_sources(
            self.root, apply=True, include_git_history=False
        )

        self.assertFalse(canonical.exists())
        self.assertFalse(legacy.exists())
        self.assertEqual(
            report["deleted"],
            [".codex-task-legacy.txt", ".codex-tasks/canonical.txt"],
        )

    def test_unmatched_and_changed_tasks_are_preserved(self) -> None:
        unmatched = self.task(".codex-tasks/unmatched.txt", "not recorded")
        changed = self.task(".codex-task-changed.txt", "changed")
        self.record("original")

        report = cleanup_task_sources(
            self.root, apply=True, include_git_history=False
        )

        self.assertTrue(unmatched.exists())
        self.assertTrue(changed.exists())
        self.assertEqual(len(report["unmatched"]), 2)
        self.assertEqual(report["deleted"], [])

    def test_symlink_and_unapproved_paths_are_never_deleted(self) -> None:
        prompt = "recorded"
        outside = self.task("outside.txt", prompt)
        self.record(prompt)
        spool = self.root / ".codex-tasks"
        spool.mkdir()
        link = spool / "link.txt"
        try:
            link.symlink_to(outside)
        except OSError as error:
            self.skipTest(f"symlinks unavailable: {error}")

        report = cleanup_task_sources(
            self.root,
            apply=True,
            include_git_history=False,
            sources=[link, outside],
        )

        self.assertTrue(link.is_symlink())
        self.assertTrue(outside.exists())
        self.assertEqual(len(report["unmatched"]), 2)

    def test_launcher_consumes_only_after_exact_invocation_recording(self) -> None:
        prompt = "bounded task"
        source = self.task(".codex-tasks/bounded.txt", prompt)
        invocation = self.record(prompt)

        result = consume_recorded_task(
            project_root=self.root,
            source=source,
            invocation_dir=invocation,
        )

        self.assertEqual(result["status"], "deleted")
        self.assertFalse(source.exists())
        self.assertTrue((invocation / "task.txt").is_file())

    def test_launcher_retains_task_when_invocation_does_not_match(self) -> None:
        source = self.task(".codex-tasks/bounded.txt", "changed task")
        invocation = self.record("recorded task")

        result = consume_recorded_task(
            project_root=self.root,
            source=source,
            invocation_dir=invocation,
        )

        self.assertEqual(result["status"], "retained")
        self.assertTrue(source.exists())

    def test_reachable_git_history_can_verify_after_branch_state_is_absent(self) -> None:
        prompt = "task preserved in git history"
        source = self.task(".codex-task-history.txt", prompt)
        self.record(prompt)
        subprocess.run(["git", "init"], cwd=self.root, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Task Cleanup Test"],
            cwd=self.root,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "cleanup@example.invalid"],
            cwd=self.root,
            check=True,
        )
        subprocess.run(["git", "add", "runs"], cwd=self.root, check=True)
        subprocess.run(
            ["git", "commit", "-m", "record invocation"],
            cwd=self.root,
            check=True,
            capture_output=True,
        )
        for path in sorted((self.root / "runs").rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()

        report = cleanup_task_sources(self.root, apply=True, include_git_history=True)

        self.assertFalse(source.exists())
        self.assertEqual(report["deleted"], [".codex-task-history.txt"])
        self.assertTrue(report["verified"][0]["recorded_at"].startswith("git:"))


if __name__ == "__main__":
    unittest.main()
