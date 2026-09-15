"""Runtime contract and CLI equivalence tests, without model calls."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.codex.specialist_runtime import executor
from scripts.codex.specialist_runtime.models import (
    ExecutionState, SpecialistInvocationRequest,
)
from scripts.codex.launcher_config import build_command, SPECIALISTS


class RuntimeTests(unittest.TestCase):
    def test_request_rejects_unsafe_arguments(self):
        cases = [
            {"specialist": "shell"}, {"task": " "}, {"task": "x\x00y"},
            {"record_session_id": "../outside"}, {"record_session_id": 5},
            {"approved_tools": ["*"]}, {"approved_tools": ["create_*"]},
            {"approved_tools": ["maboss.create_session"]},
            {"approved_tools": ["delete_session"]},
            {"approved_tools": ["clean_generated_files"]},
            {"approved_tools": [5]}, {"approved_tools": "create_session"},
            {"allow_web_search": True}, {"allow_web_search": "false"},
            {"provenance_transport": "arbitrary"},
        ]
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                SpecialistInvocationRequest(**dict(
                    {"specialist": "network_curator", "task": "inspect"}, **changes))

    def test_duplicate_approvals_and_literature_search(self):
        request = SpecialistInvocationRequest(
            "network_curator", "inspect", approved_tools=("create_session", "create_session"))
        self.assertEqual(request.approved_tools, ("create_session",))
        SpecialistInvocationRequest("literature_reviewer", "inspect", allow_web_search=True)
        with self.assertRaises(ValueError):
            SpecialistInvocationRequest("literature_reviewer", "inspect", approved_tools=("search_articles",))

    def test_context_and_command_boundary_unchanged_for_every_specialist(self):
        for specialist in SPECIALISTS:
            request = SpecialistInvocationRequest(specialist, "bounded task")
            command = build_command("codex", request.specialist, request.task)
            self.assertIn("--ephemeral", command)
            self.assertIn("--strict-config", command)
            self.assertEqual(command[command.index("--sandbox") + 1], "read-only")
            self.assertNotIn("resume", command)
            self.assertIn("Task:\nbounded task", command[-1])
            self.assertEqual(command[command.index("--profile") + 1], SPECIALISTS[specialist][0])

    def test_missing_profile_fails_without_starting_child(self):
        with tempfile.TemporaryDirectory() as temporary:
            with mock.patch.object(executor, "resolve_codex_executable", return_value="codex"), \
                 mock.patch.object(executor, "profile_path", return_value=Path(temporary)/"missing"), \
                 mock.patch.object(executor, "stream_jsonl_process") as stream:
                result = executor.execute(SpecialistInvocationRequest("network_curator", "inspect"))
            stream.assert_not_called()
            self.assertEqual(result.execution_state, ExecutionState.FAILED)
            self.assertEqual(result.return_code, 2)
            self.assertIsNone(result.handoff)
            self.assertIsNotNone(result.finished_at)

    def test_backendless_literature_is_technical_success_with_scientific_blocker(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = root / "profile.toml"
            profile.write_text("[mcp_servers]\n")
            with mock.patch.object(executor, "PROJECT_ROOT", root), \
                 mock.patch.object(executor, "resolve_codex_executable", return_value=str(profile)), \
                 mock.patch.object(executor, "profile_path", return_value=profile), \
                 mock.patch.object(executor.subprocess, "run", side_effect=[
                     mock.Mock(stdout="codex-cli 0.153.0", stderr=""),
                     mock.Mock(stdout='[]')]), \
                 mock.patch.object(executor, "stream_jsonl_process") as stream:
                result = executor.execute(SpecialistInvocationRequest("literature_reviewer", "inspect"))
            stream.assert_not_called()
            self.assertEqual(result.execution_state, ExecutionState.SUCCEEDED)
            self.assertEqual(result.return_code, 0)
            self.assertEqual(result.handoff["status"], "blocked")
            self.assertTrue((result.artifact_dir / "task.txt").is_file())
            provenance = json.loads((result.artifact_dir / "provenance.json").read_text())
            self.assertFalse(provenance["process_started"])
            self.assertIsNone(result.event_stream)

    def test_independent_invocations_allocate_fresh_ids(self):
        with mock.patch.object(executor, "_run", return_value=2):
            a = executor.execute(SpecialistInvocationRequest("network_curator", "one"))
            b = executor.execute(SpecialistInvocationRequest("network_curator", "two"))
        self.assertNotEqual(a.invocation_id, b.invocation_id)
