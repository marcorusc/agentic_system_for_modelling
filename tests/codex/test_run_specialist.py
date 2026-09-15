from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
import time
import unittest
from argparse import Namespace
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
from unittest import mock


SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "codex" / "run_specialist.py"
)
SPEC = importlib.util.spec_from_file_location("run_specialist", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RecordingStream(io.StringIO):
    def __init__(self) -> None:
        super().__init__()
        self.writes: list[tuple[float, str]] = []
        self.flush_count = 0

    def write(self, value: str) -> int:
        self.writes.append((time.monotonic(), value))
        return super().write(value)

    def flush(self) -> None:
        self.flush_count += 1
        super().flush()


class RunSpecialistTests(unittest.TestCase):
    def run_streaming_child(
        self,
        source: str,
        *,
        heartbeat_interval: float = 0.03,
        cancellation_requested=None,
    ):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        event_path = root / "events.jsonl"
        status = RecordingStream()
        result = MODULE.stream_jsonl_process(
            [sys.executable, "-u", "-c", source],
            cwd=root,
            environment=os.environ.copy(),
            event_path=event_path,
            specialist="network_curator",
            profile="biomodel-network-curator",
            launcher_run_id="launcher-test",
            heartbeat_interval=heartbeat_interval,
            status_stream=status,
            cancellation_requested=cancellation_requested,
        )
        return temporary, event_path, status, result

    def test_each_modelling_role_enables_only_its_server(self) -> None:
        expected = {
            "network_curator": "neko",
            "boolean_dynamics_modeler": "maboss",
            "multicellular_configurator": "physicell",
        }
        for specialist, permitted in expected.items():
            command = MODULE.build_command("codex", specialist, "inspect")
            overrides = {
                command[index + 1]
                for index, value in enumerate(command[:-1])
                if value == "-c"
            }
            for server in MODULE.MODELLING_SERVERS:
                state = "true" if server == permitted else "false"
                self.assertIn(f"mcp_servers.{server}.enabled={state}", overrides)

    def test_execution_command_requests_jsonl_and_separate_last_message(self) -> None:
        command = MODULE.build_command(
            "codex",
            "network_curator",
            "inspect",
            output_last_message="/tmp/last-message.json",
        )
        self.assertIn("--json", command)
        self.assertIn("--output-last-message", command)
        self.assertEqual(
            command[command.index("--output-last-message") + 1],
            "/tmp/last-message.json",
        )

    def test_jsonl_events_are_streamed_and_flushed_as_they_arrive(self) -> None:
        source = """
import json, time
print(json.dumps({"type":"turn.started"}), flush=True)
time.sleep(0.08)
print(json.dumps({"type":"turn.completed"}), flush=True)
"""
        temporary, event_path, status, result = self.run_streaming_child(source)
        self.addCleanup(temporary.cleanup)
        started_times = [
            timestamp
            for timestamp, text in status.writes
            if "specialist turn started" in text
        ]
        completed_times = [
            timestamp
            for timestamp, text in status.writes
            if "specialist turn completed" in text
        ]
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.event_count, 2)
        self.assertTrue(started_times and completed_times)
        self.assertGreater(completed_times[0] - started_times[0], 0.04)
        self.assertGreaterEqual(status.flush_count, 3)
        self.assertEqual(len(event_path.read_text(encoding="utf-8").splitlines()), 2)

    def test_malformed_jsonl_is_preserved_as_a_sanitized_envelope(self) -> None:
        source = """
import json
print("broken TOKEN=unsafe-value", flush=True)
print(json.dumps({"type":"turn.completed"}), flush=True)
"""
        temporary, event_path, status, result = self.run_streaming_child(source)
        self.addCleanup(temporary.cleanup)
        events = [json.loads(line) for line in event_path.read_text().splitlines()]
        self.assertEqual(result.malformed_event_count, 1)
        self.assertEqual(events[0]["type"], "launcher.malformed_jsonl")
        self.assertNotIn("unsafe-value", json.dumps(events))
        self.assertIn("malformed JSONL event received", status.getvalue())

    def test_long_running_mcp_call_reports_heartbeats_and_completion(self) -> None:
        source = """
import json, time
item = {"id":"call-1","type":"mcp_tool_call","server":"neko","tool":"create_network","status":"in_progress"}
print(json.dumps({"type":"item.started","item":item}), flush=True)
time.sleep(0.12)
item["status"] = "completed"
print(json.dumps({"type":"item.completed","item":item}), flush=True)
"""
        temporary, _, status, result = self.run_streaming_child(
            source, heartbeat_interval=0.025
        )
        self.addCleanup(temporary.cleanup)
        output = status.getvalue()
        self.assertEqual(result.returncode, 0)
        self.assertIn("MCP tool call started: neko.create_network", output)
        self.assertIn("active tool=neko.create_network", output)
        self.assertIn("MCP tool call completed: neko.create_network", output)

    def test_failed_mcp_call_is_reported_without_result_payload(self) -> None:
        source = """
import json
item = {"id":"call-1","type":"mcp_tool_call","server":"neko","tool":"inspect","status":"failed","error":"TOKEN=unsafe-value"}
print(json.dumps({"type":"item.completed","item":item}), flush=True)
"""
        temporary, _, status, result = self.run_streaming_child(source)
        self.addCleanup(temporary.cleanup)
        self.assertEqual(result.returncode, 0)
        self.assertIn("MCP tool call failed: neko.inspect", status.getvalue())
        self.assertNotIn("unsafe-value", status.getvalue())

    def test_command_web_and_secret_values_are_safely_summarized(self) -> None:
        source = """
import json
secret = "sk-abcdefghijklmnop"
events = [
 {"type":"item.started","item":{"id":"c1","type":"command_execution","command":"OPENAI_API_KEY="+secret+" run"}},
 {"type":"item.completed","item":{"id":"w1","type":"web_search","query":"Authorization: Bearer "+secret,"status":"completed"}},
 {"type":"item.started","item":{"id":"m1","type":"mcp_tool_call","server":"neko","tool":"inspect","arguments":{"token":"unsafe-value","blob":"x"*10000}}},
]
for event in events: print(json.dumps(event), flush=True)
"""
        temporary, event_path, status, result = self.run_streaming_child(source)
        self.addCleanup(temporary.cleanup)
        output = status.getvalue()
        stored = [json.loads(line) for line in event_path.read_text().splitlines()]
        self.assertEqual(result.returncode, 0)
        self.assertIn("command execution started", output)
        self.assertIn("web search completed", output)
        self.assertNotIn("abcdefghijklmnop", output)
        self.assertNotIn("unsafe-value", output)
        self.assertNotIn("x" * 500, output)
        self.assertEqual(
            stored[2]["item"]["arguments"]["token"], "[REDACTED]"
        )

    def test_toml_transport_credentials_are_redacted_from_errors(self) -> None:
        message = (
            'failed command: mcp={"env"={"TOKEN"="unsafe-value"}} '
            "https://user:password@example.test Authorization: Basic dXNlcjpwYXNz"
        )
        redacted = MODULE.redact_text(message)
        self.assertNotIn("unsafe-value", redacted)
        self.assertNotIn("user:password", redacted)
        self.assertNotIn("dXNlcjpwYXNz", redacted)
        self.assertIn("[REDACTED]", redacted)

    def test_no_event_timeout_emits_non_speculative_heartbeat(self) -> None:
        temporary, _, status, result = self.run_streaming_child(
            "import time; time.sleep(0.09)", heartbeat_interval=0.025
        )
        self.addCleanup(temporary.cleanup)
        output = status.getvalue()
        self.assertEqual(result.returncode, 0)
        self.assertIn("heartbeat", output)
        self.assertIn("child=running", output)
        self.assertIn("last event=none", output)
        self.assertNotIn("probably", output.lower())

    def test_child_stderr_does_not_suppress_no_event_heartbeat(self) -> None:
        source = """
import sys, time
for _ in range(12):
    print("diagnostic", file=sys.stderr, flush=True)
    time.sleep(0.01)
"""
        temporary, _, status, result = self.run_streaming_child(
            source, heartbeat_interval=0.025
        )
        self.addCleanup(temporary.cleanup)
        self.assertEqual(result.returncode, 0)
        self.assertIn("heartbeat", status.getvalue())
        self.assertIn("last event=none", status.getvalue())

    def test_streaming_cancellation_stops_child(self) -> None:
        cancel_after = time.monotonic() + 0.05
        temporary, _, status, result = self.run_streaming_child(
            "import time; time.sleep(5)",
            heartbeat_interval=0.01,
            cancellation_requested=lambda: time.monotonic() >= cancel_after,
        )
        self.addCleanup(temporary.cleanup)
        self.assertTrue(result.cancelled)
        self.assertNotEqual(result.returncode, 0)
        self.assertLess(result.elapsed_seconds, 2)
        self.assertIn("cancellation requested", status.getvalue())

    def test_streaming_preserves_nonzero_exit_code(self) -> None:
        temporary, _, _, result = self.run_streaming_child(
            "raise SystemExit(17)"
        )
        self.addCleanup(temporary.cleanup)
        self.assertEqual(result.returncode, 17)

    def test_literature_role_disables_all_modelling_servers(self) -> None:
        command = MODULE.build_command("codex", "literature_reviewer", "inspect")
        for server in MODULE.MODELLING_SERVERS:
            self.assertIn(f"mcp_servers.{server}.enabled=false", command)
        self.assertIn(
            'mcp_servers.pubmed={"command"="__disabled_pubmed__","enabled"=false}',
            command,
        )

    def test_modelling_roles_always_disable_pubmed(self) -> None:
        for specialist in (
            "network_curator",
            "boolean_dynamics_modeler",
            "multicellular_configurator",
        ):
            command = MODULE.build_command("codex", specialist, "inspect")
            self.assertIn(
                'mcp_servers.pubmed={"command"="__disabled_pubmed__","enabled"=false}',
                command,
            )

    def test_literature_pubmed_transport_is_allowlisted_for_both_commands(self) -> None:
        transport = ["-c", 'mcp_servers.pubmed={"command"="server"}']
        commands = (
            MODULE.build_mcp_list_command(
                "codex",
                "literature_reviewer",
                transport,
                pubmed_transport=True,
            ),
            MODULE.build_command(
                "codex",
                "literature_reviewer",
                "review PMID 10647931",
                transport_arguments=transport,
                pubmed_transport=True,
            ),
        )
        for command in commands:
            self.assertIn(transport[1], command)
            self.assertIn("mcp_servers.pubmed.enabled=true", command)
            self.assertTrue(
                any(
                    value.startswith("mcp_servers.pubmed.enabled_tools=")
                    for value in command
                )
            )

    def test_optional_pubmed_transport_is_loaded_from_literature_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            profile = Path(temporary) / "literature.toml"
            profile.write_text(
                '[mcp_servers.pubmed]\ncommand = "/private/pubmed"\nenabled = true\n'
                '[mcp_servers.pubmed.env]\nNCBI_API_KEY = "secret"\n',
                encoding="utf-8",
            )
            arguments = MODULE.load_permitted_transport(
                profile, "literature_reviewer"
            )
        self.assertEqual(arguments[0], "-c")
        self.assertIn('"command"="/private/pubmed"', arguments[1])

    def test_missing_optional_pubmed_transport_uses_no_override(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            profile = Path(temporary) / "literature.toml"
            profile.write_text(
                '[mcp_servers.neko]\ncommand = "disabled"\nenabled = false\n',
                encoding="utf-8",
            )
            self.assertEqual(
                MODULE.load_permitted_transport(profile, "literature_reviewer"),
                [],
            )

    def test_expected_pubmed_inventory_must_be_enabled(self) -> None:
        inventory = [
            {"name": "neko", "enabled": False},
            {"name": "maboss", "enabled": False},
            {"name": "physicell", "enabled": False},
            {"name": "pubmed", "enabled": False},
        ]
        with self.assertRaisesRegex(ValueError, "pubmed"):
            MODULE.validate_mcp_inventory(
                inventory,
                "literature_reviewer",
                pubmed_expected=True,
            )

    def test_no_literature_backend_returns_typed_blocked_handoff(self) -> None:
        handoff = MODULE.unavailable_literature_handoff("neko-session-1")
        self.assertEqual(handoff["specialist"], "literature_reviewer")
        self.assertEqual(handoff["status"], "blocked")
        self.assertEqual(handoff["session_id"], "neko-session-1")
        self.assertFalse(handoff["validation"]["passed"])
        self.assertIsNone(handoff["recommended_next_stage"])

    def test_destructive_tools_are_disabled_for_modelling_roles(self) -> None:
        for specialist in (
            "network_curator",
            "boolean_dynamics_modeler",
            "multicellular_configurator",
        ):
            command = MODULE.build_command("codex", specialist, "inspect")
            self.assertTrue(
                any(
                    value.endswith(
                        'disabled_tools=["delete_session","clean_generated_files"]'
                    )
                    for value in command
                )
            )

    def test_explicit_tool_approvals_are_scoped_to_permitted_server(self) -> None:
        command = MODULE.build_command(
            "codex",
            "network_curator",
            "construct",
            approved_tools=["create_session", "create_network"],
        )
        self.assertIn(
            'mcp_servers.neko.tools.create_session.approval_mode="approve"',
            command,
        )
        self.assertIn(
            'mcp_servers.neko.tools.create_network.approval_mode="approve"',
            command,
        )
        self.assertFalse(
            any("mcp_servers.maboss.tools" in value for value in command)
        )

    def test_destructive_tools_cannot_be_approved(self) -> None:
        for tool in ("delete_session", "clean_generated_files"):
            with self.assertRaisesRegex(ValueError, "permanently disabled"):
                MODULE.build_command(
                    "codex",
                    "network_curator",
                    "construct",
                    approved_tools=[tool],
                )

    def test_web_search_is_literature_only(self) -> None:
        command = MODULE.build_command(
            "codex", "literature_reviewer", "inspect", allow_web_search=True
        )
        self.assertIn("--search", command)
        self.assertLess(command.index("--search"), command.index("exec"))
        with self.assertRaisesRegex(ValueError, "literature_reviewer"):
            MODULE.build_command(
                "codex", "network_curator", "inspect", allow_web_search=True
            )

    def test_prompt_file_cannot_escape_project(self) -> None:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8") as handle:
            handle.write("outside")
            handle.flush()
            with self.assertRaisesRegex(ValueError, "inside the project"):
                MODULE.load_prompt(None, handle.name)

    def test_version_parser(self) -> None:
        self.assertEqual(MODULE.parse_version("codex-cli 0.153.0"), (0, 153, 0))

    def test_mcp_list_command_has_fixed_isolation_overrides(self) -> None:
        command = MODULE.build_mcp_list_command("codex", "network_curator")
        self.assertNotIn("--strict-config", command)
        self.assertIn("--profile", command)
        self.assertIn("biomodel-network-curator", command)
        self.assertIn("mcp_servers.neko.enabled=true", command)
        self.assertIn("mcp_servers.maboss.enabled=false", command)
        self.assertIn("mcp_servers.physicell.enabled=false", command)
        self.assertEqual(command[-3:], ["mcp", "list", "--json"])

    def test_inventory_accepts_only_permitted_modelling_server(self) -> None:
        inventory = [
            {"name": "neko", "enabled": False},
            {"name": "maboss", "enabled": True},
            {"name": "physicell", "enabled": False},
        ]
        MODULE.validate_mcp_inventory(inventory, "boolean_dynamics_modeler")

    def test_inventory_rejects_prohibited_modelling_server(self) -> None:
        inventory = [
            {"name": "neko", "enabled": True},
            {"name": "maboss", "enabled": True},
            {"name": "physicell", "enabled": False},
        ]
        with self.assertRaisesRegex(ValueError, "prohibited.*neko"):
            MODULE.validate_mcp_inventory(inventory, "boolean_dynamics_modeler")

    def test_inventory_rejects_missing_permitted_server(self) -> None:
        inventory = [
            {"name": "neko", "enabled": False},
            {"name": "maboss", "enabled": False},
            {"name": "physicell", "enabled": False},
        ]
        with self.assertRaisesRegex(ValueError, "permitted.*maboss"):
            MODULE.validate_mcp_inventory(inventory, "boolean_dynamics_modeler")

    def test_inventory_rejects_unexpected_enabled_servers_for_every_role(self) -> None:
        for role, (_, permitted) in MODULE.SPECIALISTS.items():
            for extra in ("maboss_alias", "unrelated_connector"):
                inventory = [{"name": extra, "enabled": True}]
                if permitted:
                    inventory.append({"name": permitted, "enabled": True})
                with self.subTest(role=role, extra=extra):
                    with self.assertRaisesRegex(ValueError, "prohibited"):
                        MODULE.validate_mcp_inventory(inventory, role)

    def test_inventory_allows_disabled_unrelated_servers(self) -> None:
        MODULE.validate_mcp_inventory([
            {"name": "neko", "enabled": True},
            {"name": "maboss_alias", "enabled": False},
        ], "network_curator")

    def test_literature_inventory_accepts_no_modelling_servers(self) -> None:
        inventory = [
            {"name": "neko", "enabled": False},
            {"name": "maboss", "enabled": False},
            {"name": "physicell", "enabled": False},
        ]
        MODULE.validate_mcp_inventory(inventory, "literature_reviewer")

    def test_permitted_transport_is_identical_in_preflight_and_execution(self) -> None:
        transport = ["-c", 'mcp_servers.neko={"command"="server"}']
        preflight = MODULE.build_mcp_list_command(
            "codex", "network_curator", transport
        )
        execution = MODULE.build_command(
            "codex",
            "network_curator",
            "inspect",
            transport_arguments=transport,
        )
        self.assertIn(transport[1], preflight)
        self.assertIn(transport[1], execution)
        for argument in MODULE.mcp_config_arguments("network_curator"):
            self.assertIn(argument, preflight)
            self.assertIn(argument, execution)

    def test_profile_transport_is_loaded_without_exposing_it_in_repo_config(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            profile = Path(temporary) / "profile.toml"
            profile.write_text(
                '[mcp_servers.neko]\ncommand = "/private/server"\n'
                'args = ["--safe"]\n[mcp_servers.neko.env]\nTOKEN = "secret"\n',
                encoding="utf-8",
            )
            arguments = MODULE.load_permitted_transport(profile, "network_curator")
        self.assertEqual(arguments[0], "-c")
        self.assertIn('"command"="/private/server"', arguments[1])
        self.assertIn('"TOKEN"="secret"', arguments[1])

    def test_prompt_is_one_argument_without_shell_interpolation(self) -> None:
        prompt = "inspect; $(touch should-not-exist) `uname`"
        command = MODULE.build_command("codex", "network_curator", prompt)
        self.assertEqual(command[-1].count(prompt), 1)
        self.assertNotIn("sh", command)
        self.assertNotIn("bash", command)

    def test_windows_wsl_command_is_an_argument_vector(self) -> None:
        config = {
            "wsl_executable": "wsl.exe",
            "distribution": "local-distribution",
            "project_path": "/workspace/project",
            "python_executable": "python3",
            "codex_executable": "/tools/codex",
        }
        command = MODULE.build_wsl_command(
            config,
            "literature_reviewer",
            prompt=None,
            prompt_file=".codex-tasks/review.txt",
            allow_web_search=True,
            record_session_id="session-1",
        )
        self.assertEqual(command[0], "wsl.exe")
        self.assertIn("--distribution", command)
        self.assertIn("scripts/codex/run_specialist.py", command)
        self.assertIn("--allow-web-search", command)
        self.assertIn("session-1", command)
        self.assertNotIn("sh", command)
        self.assertNotIn("bash", command)

    def test_windows_prompt_path_traversal_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "project-relative"):
            MODULE.validate_wsl_prompt_file("../outside.txt")

    def test_windows_bridge_propagates_nonzero_exit(self) -> None:
        args = Namespace(
            launcher_config=".codex/launcher.local.json",
            specialist="network_curator",
            prompt="inspect",
            prompt_file=None,
            allow_web_search=False,
            record_session_id=None,
        )
        config = {
            "wsl_executable": "wsl.exe",
            "distribution": "local-distribution",
            "project_path": "/workspace/project",
            "python_executable": "python3",
            "codex_executable": "/tools/codex",
        }
        process = mock.Mock()
        process.wait.return_value = 17
        with mock.patch.object(MODULE, "load_windows_launcher_config", return_value=config):
            with mock.patch.object(
                MODULE.subprocess,
                "Popen",
                return_value=process,
            ):
                self.assertEqual(MODULE.run_windows_bridge(args), 17)

    def test_process_stop_kills_child_after_termination_timeout(self) -> None:
        process = mock.Mock()
        process.poll.return_value = None
        process.wait.side_effect = [
            MODULE.subprocess.TimeoutExpired(cmd="child", timeout=0.01),
            -9,
        ]
        MODULE.stop_process(process, grace_seconds=0.01)
        process.terminate.assert_called_once_with()
        process.kill.assert_called_once_with()

    def test_output_handoff_and_provenance_use_session_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            handoff = {
                "specialist": "boolean_dynamics_modeler",
                "session_id": "maboss-session-1",
                "status": "completed",
            }
            target = MODULE.record_invocation(
                project_root=root,
                specialist="boolean_dynamics_modeler",
                prompt="simulate",
                final_output=json.dumps(handoff),
                handoff=handoff,
                expected_session_id=None,
                provenance={"schema_version": 1},
                invocation_id="invocation-1",
            )
            expected = (
                root
                / "runs/boolean-dynamics-modeler/maboss-session-1"
                / "specialist-invocations/invocation-1"
            )
            self.assertEqual(target, expected)
            self.assertTrue((target / "task.txt").is_file())
            self.assertTrue((target / "specialist-output.txt").is_file())
            self.assertTrue((target / "handoff.json").is_file())
            self.assertTrue((target / "provenance.json").is_file())

    def test_launcher_event_stream_moves_to_resolved_session_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            handoff = {
                "specialist": "network_curator",
                "session_id": "neko-session-1",
                "status": "completed",
            }
            launcher = MODULE.create_launcher_run(
                project_root=root,
                specialist="network_curator",
                prompt="inspect",
                launcher_run_id="launcher-1",
            )
            (launcher / "events.jsonl").write_text(
                '{"type":"turn.completed"}\n', encoding="utf-8"
            )
            target = MODULE.record_invocation(
                project_root=root,
                specialist="network_curator",
                prompt="inspect",
                final_output=json.dumps(handoff),
                handoff=handoff,
                expected_session_id=None,
                provenance={"event_stream": "events.jsonl"},
                invocation_id="launcher-1",
                launcher_dir=launcher,
            )
            self.assertEqual(
                target,
                root
                / "runs/network-curator/neko-session-1"
                / "specialist-invocations/launcher-1",
            )
            self.assertTrue((target / "events.jsonl").is_file())
            self.assertFalse(launcher.exists())

    def test_output_rejects_session_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "session ID"):
                MODULE.record_invocation(
                    project_root=Path(temporary),
                    specialist="network_curator",
                    prompt="inspect",
                    final_output="{}",
                    handoff={"session_id": "../outside", "status": "completed"},
                    expected_session_id=None,
                    provenance={},
                    invocation_id="invocation-1",
                )

    def test_native_launcher_records_and_rejects_unbacked_completion(self) -> None:
        from test_validate_handoff import handoff_for

        for status, expected_exit in (("completed", 3), ("needs_approval", 0)):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                executable = root / "codex-fixture"
                executable.write_text("fixture executable")
                profile = root / "profile.toml"
                profile.write_text("fixture profile")
                payload = handoff_for("network_curator", "neko_network", "session-1", None)
                payload["status"] = status
                payload["artifacts"] = []
                if status == "needs_approval":
                    payload.update(decisions_required=["Persist draft stage artifacts"],
                                   recommended_next_stage=None)

                def stream(command, **kwargs):
                    output = Path(command[command.index("--output-last-message") + 1])
                    output.write_text(json.dumps(payload), encoding="utf-8")
                    kwargs["event_path"].write_text('{"type":"turn.completed"}\n')
                    return MODULE.StreamResult(0, 0.1, 1, 0, "turn.completed", False)

                args = MODULE.parser().parse_args(["network_curator", "--prompt", "inspect"])
                with ExitStack() as stack:
                    stack.enter_context(mock.patch.object(MODULE, "PROJECT_ROOT", root))
                    stack.enter_context(mock.patch.object(MODULE, "resolve_codex_executable", return_value=str(executable)))
                    stack.enter_context(mock.patch.object(MODULE, "profile_path", return_value=profile))
                    stack.enter_context(mock.patch.object(MODULE, "load_permitted_transport", return_value=[]))
                    stack.enter_context(mock.patch.object(MODULE.subprocess, "run", side_effect=[
                        mock.Mock(stdout="codex-cli 0.153.0", stderr=""),
                        mock.Mock(stdout='[{"name":"neko","enabled":true}]'),
                    ]))
                    stack.enter_context(mock.patch.object(MODULE, "stream_jsonl_process", side_effect=stream))
                    stack.enter_context(mock.patch.object(MODULE, "emit_status"))
                    stack.enter_context(redirect_stdout(io.StringIO()))
                    self.assertEqual(MODULE.run_native(args), expected_exit)
                records = list(root.glob("runs/network-curator/session-1/specialist-invocations/*"))
                self.assertEqual(len(records), 1)
                provenance = json.loads((records[0] / "provenance.json").read_text())
                self.assertEqual(provenance["handoff_parse_error"] is not None, status == "completed")
                self.assertEqual(json.loads((records[0] / "handoff.json").read_text()), payload)


if __name__ == "__main__":
    unittest.main()
