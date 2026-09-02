#!/usr/bin/env python3
"""Regression tests for the literature-reviewer file guard."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[2]
GUARD = SOURCE_ROOT / ".claude" / "scripts" / "literature_file_guard.py"
AGENT = SOURCE_ROOT / ".claude" / "agents" / "literature-reviewer.md"


class LiteratureFileGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="literature-guard-test-")
        temporary_root = Path(self.temporary.name)
        self.project = temporary_root / "project"
        self.outside = temporary_root / "outside"
        self.project.mkdir()
        self.outside.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_guard(
        self,
        payload: object | None = None,
        *,
        raw_input: str | None = None,
        include_project_env: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        if (payload is None) == (raw_input is None):
            raise AssertionError("provide exactly one of payload or raw_input")

        environment = os.environ.copy()
        if include_project_env:
            environment["CLAUDE_PROJECT_DIR"] = str(self.project)
        else:
            environment.pop("CLAUDE_PROJECT_DIR", None)

        stdin = raw_input if raw_input is not None else json.dumps(payload)
        return subprocess.run(
            [sys.executable, str(GUARD)],
            input=stdin,
            text=True,
            capture_output=True,
            env=environment,
            check=False,
        )

    @staticmethod
    def tool_call(tool_name: str, file_path: Path) -> dict[str, object]:
        tool_input: dict[str, object] = {"file_path": str(file_path)}
        if tool_name == "Write":
            tool_input["content"] = "report content"
        return {"tool_name": tool_name, "tool_input": tool_input}

    def assert_blocked(
        self, result: subprocess.CompletedProcess[str], message: str
    ) -> None:
        self.assertEqual(result.returncode, 2, result)
        self.assertIn(message, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_write_below_reports_is_allowed_and_creates_parent(self) -> None:
        target = self.project / "evidence" / "reports" / "session-1" / "A__B.md"
        self.assertFalse(target.parent.exists())

        result = self.run_guard(self.tool_call("Write", target))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(target.parent.is_dir())
        self.assertFalse(target.exists(), "the guard must not write report content")

    def test_ordinary_reads_are_allowed(self) -> None:
        for target in (
            self.project / "README.md",
            self.project / "evidence" / "reports" / "session-1" / "A__B.md",
        ):
            with self.subTest(target=target):
                result = self.run_guard(self.tool_call("Read", target))
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_write_outside_reports_is_blocked(self) -> None:
        target = self.project / "notes" / "A__B.md"
        result = self.run_guard(self.tool_call("Write", target))
        self.assert_blocked(result, "Write is allowed only below")
        self.assertFalse(target.parent.exists())

    def test_lookalike_report_directory_is_blocked(self) -> None:
        target = self.project / "evidence" / "reports-evil" / "session" / "A__B.md"
        result = self.run_guard(self.tool_call("Write", target))
        self.assert_blocked(result, "Write is allowed only below")

    def test_parent_traversal_out_of_reports_is_blocked(self) -> None:
        target = (
            self.project
            / "evidence"
            / "reports"
            / "session"
            / ".."
            / ".."
            / "escaped.md"
        )
        result = self.run_guard(self.tool_call("Write", target))
        self.assert_blocked(result, "Write is allowed only below")

    def test_symlink_escape_below_reports_is_blocked(self) -> None:
        reports = self.project / "evidence" / "reports"
        reports.mkdir(parents=True)
        link = reports / "external"
        try:
            link.symlink_to(self.outside, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"directory symlinks are unavailable: {error}")

        target = link / "session" / "A__B.md"
        result = self.run_guard(self.tool_call("Write", target))
        self.assert_blocked(result, "Write is allowed only below")
        self.assertFalse((self.outside / "session").exists())

    def test_symlinked_report_root_is_blocked(self) -> None:
        evidence = self.project / "evidence"
        evidence.mkdir()
        try:
            (evidence / "reports").symlink_to(self.outside, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"directory symlinks are unavailable: {error}")

        target = evidence / "reports" / "session" / "A__B.md"
        result = self.run_guard(self.tool_call("Write", target))
        self.assert_blocked(result, "evidence/reports resolves outside")

    def test_queue_and_sif_full_reads_are_blocked(self) -> None:
        targets = (
            self.project / "runs" / "literature_queue.json",
            self.project / "runs" / "Network.sif",
            self.project / "runs" / "NETWORK.SIF",
        )
        for target in targets:
            with self.subTest(target=target):
                result = self.run_guard(self.tool_call("Read", target))
                self.assert_blocked(result, "do not Read literature_queue.json")

    def test_malformed_json_is_blocked(self) -> None:
        result = self.run_guard(raw_input="{not-json")
        self.assert_blocked(result, "invalid hook JSON input")

    def test_missing_or_invalid_fields_are_blocked(self) -> None:
        cases = (
            ({}, "unexpected tool_name"),
            ({"tool_name": "Write"}, "tool_input must be a JSON object"),
            (
                {"tool_name": "Write", "tool_input": {}},
                "tool_input.file_path must be a non-empty string",
            ),
            (
                {"tool_name": "Write", "tool_input": {"file_path": "relative.md"}},
                "tool_input.file_path must be absolute",
            ),
            (
                {"tool_name": "Grep", "tool_input": {"file_path": "/tmp/file"}},
                "unexpected tool_name",
            ),
        )
        for payload, message in cases:
            with self.subTest(payload=payload):
                result = self.run_guard(payload)
                self.assert_blocked(result, message)

    def test_missing_project_environment_is_blocked_for_writes(self) -> None:
        target = self.project / "evidence" / "reports" / "session" / "A__B.md"
        result = self.run_guard(
            self.tool_call("Write", target), include_project_env=False
        )
        self.assert_blocked(result, "CLAUDE_PROJECT_DIR is not set")

    def test_report_write_and_read_back_smoke(self) -> None:
        target = (
            self.project
            / "evidence"
            / "reports"
            / "smoke-session"
            / "PTPN11__AKT1.md"
        )
        content = """## Edge: PTPN11 -> AKT1

**Verdict:** supported
**Confidence:** medium

### Supporting evidence
- PMID 12345678 (DOI: none): smoke-test evidence
"""

        write_check = self.run_guard(self.tool_call("Write", target))
        self.assertEqual(write_check.returncode, 0, write_check.stderr)
        target.write_text(content, encoding="utf-8")

        read_check = self.run_guard(self.tool_call("Read", target))
        self.assertEqual(read_check.returncode, 0, read_check.stderr)
        read_back = target.read_text(encoding="utf-8")
        self.assertIn("## Edge: PTPN11 -> AKT1", read_back)
        self.assertIn("PMID 12345678", read_back)


class LiteratureReviewerDefinitionTests(unittest.TestCase):
    def test_agent_uses_repository_guard_without_jq(self) -> None:
        definition = AGENT.read_text(encoding="utf-8")
        self.assertIn("  - Write\n", definition)
        self.assertIn('    - matcher: "Read|Write"\n', definition)
        self.assertIn("          command: python\n", definition)
        self.assertIn(
            '            - "${CLAUDE_PROJECT_DIR}/.claude/scripts/'
            'literature_file_guard.py"\n',
            definition,
        )
        self.assertNotIn("jq", definition.lower())


if __name__ == "__main__":
    unittest.main()
