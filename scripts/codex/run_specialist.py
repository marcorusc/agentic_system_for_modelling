#!/usr/bin/env python3
"""Launch one specialist Codex process with enforced MCP isolation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, NamedTuple, TextIO

try:
    from scripts.codex.cleanup_tasks import consume_recorded_task
    from scripts.codex.validate_handoff import (
        HandoffValidationError,
        validate_handoff,
    )
except ModuleNotFoundError:  # Direct execution adds scripts/codex, not repo root.
    from cleanup_tasks import consume_recorded_task
    from validate_handoff import HandoffValidationError, validate_handoff


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MINIMUM_CODEX_VERSION = (0, 153, 0)
MODELLING_SERVERS = ("neko", "maboss", "physicell")
PUBMED_TOOLS = (
    "search_articles",
    "get_article_metadata",
    "convert_article_ids",
    "get_full_text_article",
    "find_related_articles",
)
SPECIALISTS = {
    "network_curator": ("biomodel-network-curator", "neko"),
    "literature_reviewer": ("biomodel-literature-reviewer", None),
    "boolean_dynamics_modeler": ("biomodel-boolean-dynamics-modeler", "maboss"),
    "multicellular_configurator": ("biomodel-multicellular-configurator", "physicell"),
}
RUN_ROOTS = {
    "network_curator": Path("runs/network-curator"),
    "literature_reviewer": Path("runs/network-curator"),
    "boolean_dynamics_modeler": Path("runs/boolean-dynamics-modeler"),
    "multicellular_configurator": Path("runs/multicellular-configurator"),
}
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
MCP_TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
PERMANENTLY_DISABLED_TOOLS = {"delete_session", "clean_generated_files"}
WINDOWS_CONFIG_FIELDS = {
    "wsl_executable",
    "distribution",
    "project_path",
    "python_executable",
    "codex_executable",
}
HEARTBEAT_INTERVAL_SECONDS = 30.0
LIVE_VALUE_LIMIT = 240
SENSITIVE_FIELD_RE = re.compile(
    r"(?:auth(?:entication|orization)?|credential|cookie|password|passwd|"
    r"private[_-]?key|secret|session[_-]?token|access[_-]?(?:token|key)|"
    r"api[_-]?key|token)",
    re.IGNORECASE,
)
SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?i)((?:\"|')?\b[A-Z0-9_.-]*(?:TOKEN|SECRET|PASSWORD|PASSWD|"
    r"API[_-]?KEY|ACCESS[_-]?KEY|CREDENTIAL|COOKIE|AUTHORIZATION|"
    r"AUTHENTICATION)[A-Z0-9_.-]*\b(?:\"|')?"
    r"\s*[:=]\s*)(?:Bearer\s+\[REDACTED\]|\[REDACTED\]|"
    r"\"[^\"]*\"|'[^']*'|[^\s,}\]]+)"
)
AUTH_SCHEME_RE = re.compile(r"(?i)\b(?:Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+")
OPENAI_KEY_RE = re.compile(r"\b(?:sk|rk|pk)-[A-Za-z0-9_-]{12,}\b")
URL_CREDENTIAL_RE = re.compile(r"(?i)(https?://)[^/\s:@]+:[^/\s@]+@")
JSON_SENSITIVE_ASSIGNMENT_RE = re.compile(
    r'''(?i)((?:"|')[^"']*(?:TOKEN|SECRET|PASSWORD|PASSWD|API[_-]?KEY|'''
    r'''CREDENTIAL|COOKIE|AUTHORIZATION|AUTHENTICATION)[^"']*(?:"|')'''
    r'''\s*:\s*)(?:"[^"]*"|'[^']*'|[^\s,}\]]+)'''
)


class StreamResult(NamedTuple):
    returncode: int
    elapsed_seconds: float
    event_count: int
    malformed_event_count: int
    last_event: str | None
    cancelled: bool


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def redact_text(value: str) -> str:
    """Remove common credential forms before text reaches logs or the console."""

    value = AUTH_SCHEME_RE.sub("[REDACTED]", value)
    value = URL_CREDENTIAL_RE.sub(r"\1[REDACTED]@", value)
    value = OPENAI_KEY_RE.sub("[REDACTED]", value)
    value = JSON_SENSITIVE_ASSIGNMENT_RE.sub(r'\1"[REDACTED]"', value)
    return SENSITIVE_ASSIGNMENT_RE.sub(r'\1"[REDACTED]"', value)


def sanitize_json_value(value: object, *, key: str | None = None) -> object:
    """Preserve event structure while redacting values under sensitive keys."""

    if (
        key is not None
        and not key.lower().replace("-", "_").endswith("_tokens")
        and SENSITIVE_FIELD_RE.search(key)
    ):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {
            str(item_key): sanitize_json_value(item, key=str(item_key))
            for item_key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize_json_value(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def compact_live_value(value: object, limit: int = LIVE_VALUE_LIMIT) -> str:
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    text = " ".join(redact_text(text).split())
    if len(text) <= limit:
        return text
    return f"{text[:limit]}… [truncated {len(text) - limit} chars]"


def emit_status(message: str, stream: TextIO = sys.stderr) -> None:
    print(f"[specialist-launcher] {redact_text(message)}", file=stream, flush=True)


def _event_item(event: dict[str, Any]) -> dict[str, Any]:
    item = event.get("item")
    return item if isinstance(item, dict) else {}


def _mcp_tool_name(item: dict[str, Any]) -> str:
    tool = item.get("tool") or item.get("tool_name") or item.get("name") or "unknown"
    server = item.get("server") or item.get("server_name")
    tool_text = compact_live_value(tool, 128)
    if isinstance(server, str) and server and not tool_text.startswith(f"{server}."):
        return f"{compact_live_value(server, 64)}.{tool_text}"
    return tool_text


def summarize_event(
    event: dict[str, Any], active_tools: dict[str, str]
) -> tuple[str, str]:
    event_type = event.get("type")
    if not isinstance(event_type, str):
        event_type = "unknown"
    item = _event_item(event)
    item_type = item.get("type")
    item_id = item.get("id")
    item_key = str(item_id) if item_id is not None else f"anonymous-{id(item)}"

    if item_type == "mcp_tool_call":
        tool_name = _mcp_tool_name(item)
        failed = bool(item.get("error")) or item.get("status") in {"failed", "error"}
        if event_type == "item.started":
            active_tools[item_key] = tool_name
            return f"MCP tool call started: {tool_name}", event_type
        active_tools.pop(item_key, None)
        outcome = "failed" if failed or event_type in {"item.failed", "error"} else "completed"
        return f"MCP tool call {outcome}: {tool_name}", event_type

    if item_type == "command_execution":
        command = item.get("command")
        detail = f": {compact_live_value(command)}" if command is not None else ""
        failed = bool(item.get("error")) or item.get("status") in {"failed", "error"}
        if event_type == "item.started":
            return f"command execution started{detail}", event_type
        outcome = "failed" if failed or event_type == "item.failed" else "completed"
        return f"command execution {outcome}{detail}", event_type

    if item_type == "web_search":
        query_value = item.get("query") or item.get("queries")
        detail = f": {compact_live_value(query_value)}" if query_value is not None else ""
        failed = bool(item.get("error")) or item.get("status") in {"failed", "error"}
        if event_type == "item.started":
            return f"web search started{detail}", event_type
        outcome = "failed" if failed or event_type == "item.failed" else "completed"
        return f"web search {outcome}{detail}", event_type

    if event_type == "thread.started":
        return "Codex thread started", event_type
    if event_type == "turn.started":
        return "specialist turn started", event_type
    if event_type == "turn.completed":
        return "specialist turn completed", event_type
    if event_type == "turn.failed":
        return "specialist turn failed", event_type
    if event_type == "error":
        return "Codex error event received", event_type
    if item_type == "agent_message":
        return "agent message received", event_type
    if item_type == "reasoning":
        return "reasoning update received", event_type
    if item_type == "plan_update":
        return "plan update received", event_type
    if item_type:
        return f"{event_type}: {compact_live_value(item_type, 80)}", event_type
    return f"event received: {compact_live_value(event_type, 80)}", event_type


def persist_event_line(
    line: str,
    *,
    event_handle: TextIO,
    active_tools: dict[str, str],
) -> tuple[str, str, bool]:
    raw_line = line.rstrip("\r\n")
    try:
        event = json.loads(raw_line)
        if not isinstance(event, dict):
            raise ValueError("event is not a JSON object")
        stored_event = sanitize_json_value(event)
        assert isinstance(stored_event, dict)
        event_handle.write(json.dumps(stored_event, ensure_ascii=False) + "\n")
        summary, event_type = summarize_event(event, active_tools)
        malformed = False
    except (json.JSONDecodeError, ValueError):
        envelope = {
            "type": "launcher.malformed_jsonl",
            "raw": redact_text(raw_line),
        }
        event_handle.write(json.dumps(envelope, ensure_ascii=False) + "\n")
        summary = "malformed JSONL event received"
        event_type = "malformed_jsonl"
        malformed = True
    event_handle.flush()
    return summary, event_type, malformed


def _pipe_reader(
    pipe: TextIO, stream_name: str, messages: queue.Queue[tuple[str, str | None]]
) -> None:
    try:
        for line in iter(pipe.readline, ""):
            messages.put((stream_name, line))
    finally:
        pipe.close()
        messages.put((stream_name, None))


def stop_process(process: subprocess.Popen[str], grace_seconds: float = 5.0) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def stream_jsonl_process(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    event_path: Path,
    specialist: str,
    profile: str,
    launcher_run_id: str,
    heartbeat_interval: float = HEARTBEAT_INTERVAL_SECONDS,
    status_stream: TextIO = sys.stderr,
    monotonic: Callable[[], float] = time.monotonic,
    cancellation_requested: Callable[[], bool] | None = None,
) -> StreamResult:
    """Stream, sanitize, summarize, and persist one `codex exec --json` run."""

    if heartbeat_interval <= 0:
        raise ValueError("heartbeat interval must be positive")
    event_path.parent.mkdir(parents=True, exist_ok=True)
    event_handle = event_path.open("x", encoding="utf-8")
    os.chmod(event_path, 0o600)
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=environment,
        )
    except BaseException:
        event_handle.close()
        raise
    assert process.stdout is not None
    assert process.stderr is not None
    messages: queue.Queue[tuple[str, str | None]] = queue.Queue()
    readers = [
        threading.Thread(
            target=_pipe_reader,
            args=(process.stdout, "stdout", messages),
            daemon=True,
        ),
        threading.Thread(
            target=_pipe_reader,
            args=(process.stderr, "stderr", messages),
            daemon=True,
        ),
    ]
    for reader in readers:
        reader.start()

    started = monotonic()
    last_event_at = started
    last_event: str | None = None
    event_count = 0
    malformed_count = 0
    active_tools: dict[str, str] = {}
    closed_streams: set[str] = set()
    cancelled = False
    try:
        while len(closed_streams) < 2 or process.poll() is None or not messages.empty():
            if (
                not cancelled
                and cancellation_requested is not None
                and cancellation_requested()
            ):
                cancelled = True
                emit_status(
                    f"launcher_run={launcher_run_id} cancellation requested; stopping child",
                    status_stream,
                )
                stop_process(process)

            now = monotonic()
            inactive_for = now - last_event_at
            if inactive_for >= heartbeat_interval:
                process_state = (
                    "running"
                    if process.poll() is None
                    else f"exited({process.returncode})"
                )
                if active_tools:
                    observation = "active tool=" + ",".join(active_tools.values())
                else:
                    observation = f"last event={last_event or 'none'}"
                emit_status(
                    f"heartbeat launcher_run={launcher_run_id} "
                    f"elapsed={now - started:.1f}s child={process_state} {observation}",
                    status_stream,
                )
                last_event_at = now
                continue

            heartbeat_due_in = heartbeat_interval - inactive_for
            wait_seconds = min(heartbeat_due_in, 0.5)
            try:
                stream_name, line = messages.get(timeout=wait_seconds)
            except queue.Empty:
                continue

            if line is None:
                closed_streams.add(stream_name)
                continue
            if stream_name == "stderr":
                emit_status(
                    f"child stderr: {compact_live_value(line.rstrip())}", status_stream
                )
                continue

            received_at = monotonic()
            last_event_at = received_at
            summary, last_event, malformed = persist_event_line(
                line, event_handle=event_handle, active_tools=active_tools
            )
            if malformed:
                malformed_count += 1
            event_count += 1
            emit_status(
                f"launcher_run={launcher_run_id} specialist={specialist} "
                f"profile={profile} {summary}",
                status_stream,
            )
    except KeyboardInterrupt:
        cancelled = True
        emit_status(
            f"launcher_run={launcher_run_id} interrupted; stopping child",
            status_stream,
        )
        stop_process(process)
        while len(closed_streams) < 2 or not messages.empty():
            try:
                stream_name, line = messages.get(timeout=0.1)
            except queue.Empty:
                if all(not reader.is_alive() for reader in readers):
                    break
                continue
            if line is None:
                closed_streams.add(stream_name)
            elif stream_name == "stderr":
                emit_status(
                    f"child stderr: {compact_live_value(line.rstrip())}",
                    status_stream,
                )
            else:
                summary, last_event, malformed = persist_event_line(
                    line, event_handle=event_handle, active_tools=active_tools
                )
                event_count += 1
                malformed_count += int(malformed)
                emit_status(
                    f"launcher_run={launcher_run_id} specialist={specialist} "
                    f"profile={profile} {summary}",
                    status_stream,
                )
    finally:
        event_handle.close()
        if process.poll() is None:
            stop_process(process)
        for reader in readers:
            reader.join(timeout=1.0)

    returncode = process.wait()
    elapsed = monotonic() - started
    emit_status(
        f"launcher_run={launcher_run_id} child exit status={returncode} "
        f"elapsed={elapsed:.1f}s",
        status_stream,
    )
    return StreamResult(
        returncode=returncode,
        elapsed_seconds=elapsed,
        event_count=event_count,
        malformed_event_count=malformed_count,
        last_event=last_event,
        cancelled=cancelled,
    )


def parse_version(output: str) -> tuple[int, int, int]:
    match = re.search(r"\b(\d+)\.(\d+)\.(\d+)\b", output)
    if match is None:
        raise ValueError("unable to parse Codex version")
    return tuple(int(part) for part in match.groups())


def profile_path(profile: str) -> Path:
    return Path.home() / ".codex" / f"{profile}.config.toml"


def validate_session_id(session_id: str) -> str:
    if SESSION_ID_RE.fullmatch(session_id) is None:
        raise ValueError(
            "session ID must contain only letters, digits, dot, dash, or underscore"
        )
    return session_id


def resolve_prompt_file(prompt_file: str) -> Path:
    path = Path(prompt_file)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path = path.resolve(strict=True)
    try:
        path.relative_to(PROJECT_ROOT)
    except ValueError as exc:
        raise ValueError("prompt files must be inside the project") from exc
    return path


def load_prompt(prompt: str | None, prompt_file: str | None) -> str:
    if prompt is not None:
        return prompt
    if prompt_file is None:
        raise ValueError("provide --prompt or --prompt-file")
    return resolve_prompt_file(prompt_file).read_text(encoding="utf-8")


def cleanup_recorded_prompt(
    prompt_source: Path | None,
    artifact_dir: Path,
) -> None:
    result = consume_recorded_task(
        project_root=PROJECT_ROOT,
        source=prompt_source,
        invocation_dir=artifact_dir,
    )
    if result is None:
        return
    status = result.get("status")
    path = result.get("path")
    if status == "deleted":
        emit_status(f"Removed verified task source: {path}")
    elif status == "retained":
        emit_status(
            f"Retained task source {path}: {result.get('reason', 'verification failed')}"
        )


def resolve_codex_executable(candidate: str | None) -> str:
    raw = candidate or shutil.which("codex")
    if raw is None:
        raise ValueError("Codex executable was not found")
    resolved = Path(raw).expanduser().resolve(strict=True)
    if not resolved.is_file():
        raise ValueError("Codex executable is not a file")
    return str(resolved)


def validate_approved_tools(
    specialist: str, approved_tools: list[str] | None
) -> list[str]:
    _, permitted_server = SPECIALISTS[specialist]
    requested: list[str] = []
    for tool in approved_tools or []:
        if permitted_server is None:
            raise ValueError(
                "--approve-tool is valid only for a modelling specialist"
            )
        if MCP_TOOL_NAME_RE.fullmatch(tool) is None:
            raise ValueError(f"invalid MCP tool name for approval: {tool}")
        if tool in PERMANENTLY_DISABLED_TOOLS:
            raise ValueError(f"MCP tool is permanently disabled: {tool}")
        if tool not in requested:
            requested.append(tool)
    return requested


def mcp_config_arguments(
    specialist: str,
    approved_tools: list[str] | None = None,
    *,
    pubmed_transport: bool = False,
) -> list[str]:
    _, permitted_server = SPECIALISTS[specialist]
    arguments: list[str] = []
    for server in MODELLING_SERVERS:
        enabled = "true" if server == permitted_server else "false"
        arguments.extend(["-c", f"mcp_servers.{server}.enabled={enabled}"])
    if permitted_server is not None:
        arguments.extend(["-c", f"mcp_servers.{permitted_server}.required=true"])
        arguments.extend(
            [
                "-c",
                (
                    f'mcp_servers.{permitted_server}.disabled_tools='
                    '["delete_session","clean_generated_files"]'
                ),
            ]
        )
        for tool in validate_approved_tools(specialist, approved_tools):
            arguments.extend(
                [
                    "-c",
                    (
                        f"mcp_servers.{permitted_server}.tools.{tool}."
                        'approval_mode="approve"'
                    ),
                ]
            )
        # A disabled server still needs a complete transport when no inherited
        # PubMed table exists; otherwise Codex rejects the partial override as an
        # invalid transport before inventory preflight can run.
        arguments.extend(
            [
                "-c",
                'mcp_servers.pubmed={"command"="__disabled_pubmed__","enabled"=false}',
            ]
        )
    elif pubmed_transport:
        arguments.extend(["-c", "mcp_servers.pubmed.enabled=true"])
        arguments.extend(["-c", "mcp_servers.pubmed.required=true"])
        arguments.extend(
            [
                "-c",
                "mcp_servers.pubmed.enabled_tools=" + json.dumps(PUBMED_TOOLS),
            ]
        )
    return arguments


def toml_literal(value: object) -> str:
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return repr(value)
    if isinstance(value, list):
        return "[" + ",".join(toml_literal(item) for item in value) + "]"
    if isinstance(value, dict):
        entries = [
            f"{json.dumps(str(key))}={toml_literal(item)}"
            for key, item in sorted(value.items())
        ]
        return "{" + ",".join(entries) + "}"
    raise ValueError(f"unsupported profile value type: {type(value).__name__}")


def load_permitted_transport(profile_file: Path, specialist: str) -> list[str]:
    import tomllib

    _, permitted_server = SPECIALISTS[specialist]
    payload = tomllib.loads(profile_file.read_text(encoding="utf-8"))
    servers = payload.get("mcp_servers")
    if not isinstance(servers, dict):
        raise ValueError("profile has no mcp_servers table")
    if permitted_server is None:
        pubmed = servers.get("pubmed")
        if pubmed is None:
            return []
        if not isinstance(pubmed, dict):
            raise ValueError("profile pubmed transport is not a table")
        if pubmed.get("enabled") is False:
            return []
        if not isinstance(pubmed.get("command"), str) and not isinstance(
            pubmed.get("url"), str
        ):
            raise ValueError("profile has no complete pubmed transport")
        return ["-c", f"mcp_servers.pubmed={toml_literal(pubmed)}"]
    transport = servers.get(permitted_server)
    if not isinstance(transport, dict):
        raise ValueError(f"profile has no {permitted_server} transport")
    if not isinstance(transport.get("command"), str) and not isinstance(
        transport.get("url"), str
    ):
        raise ValueError(f"profile has no complete {permitted_server} transport")
    return [
        "-c",
        f"mcp_servers.{permitted_server}={toml_literal(transport)}",
    ]


def build_command(
    codex: str,
    specialist: str,
    prompt: str,
    allow_web_search: bool = False,
    output_last_message: str | None = None,
    transport_arguments: list[str] | None = None,
    approved_tools: list[str] | None = None,
    pubmed_transport: bool = False,
) -> list[str]:
    profile, _ = SPECIALISTS[specialist]
    if allow_web_search and specialist != "literature_reviewer":
        raise ValueError("--allow-web-search is valid only for literature_reviewer")

    command = [codex]
    if allow_web_search:
        command.append("--search")
    command.extend(
        [
            "exec",
            "--strict-config",
            "--ephemeral",
            "--sandbox",
            "read-only",
            "--color",
            "never",
            "--json",
            "--profile",
            profile,
        ]
    )
    if output_last_message is not None:
        command.extend(["--output-last-message", output_last_message])
    command.extend(transport_arguments or [])
    command.extend(
        mcp_config_arguments(
            specialist,
            approved_tools,
            pubmed_transport=pubmed_transport,
        )
    )
    command.append(
        f"Act as {specialist}. Follow the active AGENTS.md and your profile's "
        f"developer instructions. Return exactly one JSON typed specialist handoff."
        f"\n\nTask:\n{prompt}"
    )
    return command


def build_mcp_list_command(
    codex: str,
    specialist: str,
    transport_arguments: list[str] | None = None,
    approved_tools: list[str] | None = None,
    pubmed_transport: bool = False,
) -> list[str]:
    profile, _ = SPECIALISTS[specialist]
    return [
        codex,
        "--profile",
        profile,
        *(transport_arguments or []),
        *mcp_config_arguments(
            specialist,
            approved_tools,
            pubmed_transport=pubmed_transport,
        ),
        "mcp",
        "list",
        "--json",
    ]


def validate_mcp_inventory(
    inventory: object,
    specialist: str,
    *,
    pubmed_expected: bool | None = None,
) -> dict[str, bool]:
    if not isinstance(inventory, list):
        raise ValueError("Codex MCP inventory is not a list")

    configured: dict[str, bool] = {}
    for item in inventory:
        if not isinstance(item, dict):
            raise ValueError("Codex MCP inventory contains a non-object entry")
        name = item.get("name")
        enabled = item.get("enabled")
        if not isinstance(name, str) or not isinstance(enabled, bool):
            raise ValueError("Codex MCP inventory entry lacks name/enabled")
        if name in configured:
            raise ValueError(f"duplicate MCP server entry: {name}")
        configured[name] = enabled

    _, permitted_server = SPECIALISTS[specialist]
    for server in MODELLING_SERVERS:
        enabled = configured.get(server, False)
        if server == permitted_server and not enabled:
            raise ValueError(f"permitted MCP server is not enabled: {server}")
        if server != permitted_server and enabled:
            raise ValueError(f"prohibited MCP server is enabled: {server}")
    if specialist == "literature_reviewer" and pubmed_expected is not None:
        if configured.get("pubmed", False) != pubmed_expected:
            state = "enabled" if pubmed_expected else "disabled"
            raise ValueError(f"pubmed MCP server was expected to be {state}")
    return configured


def parse_handoff(output: str) -> dict[str, Any] | None:
    stripped = output.strip()
    candidates = [stripped]
    if stripped.startswith("```") and stripped.endswith("```"):
        first_newline = stripped.find("\n")
        candidates.append(stripped[first_newline + 1 : stripped.rfind("```")].strip())
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value

    decoder = json.JSONDecoder()
    for index, character in enumerate(output):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(output[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and "specialist" in value:
            return value
    return None


def unavailable_literature_handoff(session_id: str | None) -> dict[str, Any]:
    """Return a valid fail-closed result without starting a backend-less agent."""

    return {
        "schema_version": 1,
        "specialist": "literature_reviewer",
        "status": "blocked",
        "stage": "literature_review",
        "session_id": session_id,
        "derived_from_session_id": None,
        "actions": ["checked isolated literature backend availability"],
        "assumptions": [],
        "decisions_required": [
            "Configure the optional PubMed MCP or explicitly authorize --allow-web-search"
        ],
        "artifacts": [],
        "validation": {
            "checks": [
                "NeKo, MaBoSS, and PhysiCell were disabled",
                "No PubMed MCP or explicitly enabled web-search backend was available",
            ],
            "passed": False,
        },
        "recommended_next_stage": None,
    }


def sha256_file(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def specialist_run_base(project_root: Path, specialist: str) -> Path:
    project = project_root.resolve(strict=True)
    base = (project / RUN_ROOTS[specialist]).resolve(strict=False)
    try:
        base.relative_to(project)
    except ValueError as exc:
        raise ValueError("specialist run root resolves outside the project") from exc
    return base


def create_launcher_run(
    *, project_root: Path, specialist: str, prompt: str, launcher_run_id: str
) -> Path:
    validate_session_id(launcher_run_id)
    base = specialist_run_base(project_root, specialist)
    target = (base / "_launcher-runs" / launcher_run_id).resolve(strict=False)
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise ValueError("launcher run resolves outside the specialist run root") from exc
    target.mkdir(parents=True, exist_ok=False)
    (target / "task.txt").write_text(prompt.rstrip() + "\n", encoding="utf-8")
    return target


def record_invocation(
    *,
    project_root: Path,
    specialist: str,
    prompt: str,
    final_output: str,
    handoff: dict[str, Any] | None,
    expected_session_id: str | None,
    provenance: dict[str, Any],
    invocation_id: str,
    launcher_dir: Path | None = None,
) -> Path:
    handoff_session_id = handoff.get("session_id") if handoff is not None else None
    if handoff_session_id is not None and not isinstance(handoff_session_id, str):
        raise ValueError("handoff session_id must be a string or null")
    if expected_session_id is not None:
        expected_session_id = validate_session_id(expected_session_id)
    if handoff_session_id is not None:
        handoff_session_id = validate_session_id(handoff_session_id)
    if (
        expected_session_id is not None
        and handoff_session_id is not None
        and expected_session_id != handoff_session_id
    ):
        raise ValueError("handoff session_id does not match --record-session-id")

    session_id = expected_session_id or handoff_session_id
    if session_id is None:
        status = handoff.get("status") if handoff is not None else None
        session_id = "_blocked" if status == "blocked" else "_unresolved"

    base = specialist_run_base(project_root, specialist)
    target = (base / session_id / "specialist-invocations" / invocation_id).resolve(
        strict=False
    )
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise ValueError("invocation output resolves outside the specialist run root") from exc

    if launcher_dir is None:
        target.mkdir(parents=True, exist_ok=False)
        (target / "task.txt").write_text(prompt.rstrip() + "\n", encoding="utf-8")
        working = target
    else:
        working = launcher_dir.resolve(strict=True)
        launcher_root = (base / "_launcher-runs").resolve(strict=False)
        try:
            working.relative_to(launcher_root)
        except ValueError as exc:
            raise ValueError("launcher directory is outside the launcher run root") from exc
        if working.name != invocation_id:
            raise ValueError("launcher directory does not match invocation ID")

    (working / "specialist-output.txt").write_text(final_output, encoding="utf-8")
    if handoff is not None:
        write_json(working / "handoff.json", handoff)
    write_json(working / "provenance.json", provenance)
    if launcher_dir is not None:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise ValueError("specialist invocation directory already exists")
        working.rename(target)
    return target


def load_windows_launcher_config(path_text: str) -> dict[str, str]:
    path = Path(path_text)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path = path.resolve(strict=True)
    try:
        path.relative_to(PROJECT_ROOT)
    except ValueError as exc:
        raise ValueError("Windows launcher config must be inside the project") from exc
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Windows launcher config must contain a JSON object")
    unknown = set(payload) - WINDOWS_CONFIG_FIELDS
    if unknown:
        raise ValueError(f"unknown Windows launcher config fields: {sorted(unknown)}")

    defaults = {"wsl_executable": "wsl.exe", "python_executable": "python3"}
    result: dict[str, str] = {}
    for field in WINDOWS_CONFIG_FIELDS:
        value = payload.get(field, defaults.get(field))
        if not isinstance(value, str) or not value or "\x00" in value:
            raise ValueError(
                f"Windows launcher config field {field} must be a non-empty string"
            )
        result[field] = value
    if not result["project_path"].startswith("/"):
        raise ValueError("Windows launcher project_path must be an absolute WSL path")
    return result


def validate_wsl_prompt_file(prompt_file: str) -> str:
    path = PurePosixPath(prompt_file)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Windows-to-WSL prompt file must be project-relative")
    return prompt_file


def build_wsl_command(
    config: dict[str, str],
    specialist: str,
    *,
    prompt: str | None,
    prompt_file: str | None,
    allow_web_search: bool,
    record_session_id: str | None,
    approved_tools: list[str] | None = None,
) -> list[str]:
    command = [
        config["wsl_executable"],
        "--distribution",
        config["distribution"],
        "--cd",
        config["project_path"],
        config["python_executable"],
        "scripts/codex/run_specialist.py",
        specialist,
        "--transport",
        "native",
        "--provenance-transport",
        "windows-wsl",
        "--codex-executable",
        config["codex_executable"],
    ]
    if prompt is not None:
        command.extend(["--prompt", prompt])
    elif prompt_file is not None:
        command.extend(["--prompt-file", validate_wsl_prompt_file(prompt_file)])
    else:
        raise ValueError("provide --prompt or --prompt-file")
    if allow_web_search:
        command.append("--allow-web-search")
    if record_session_id is not None:
        command.extend(["--record-session-id", validate_session_id(record_session_id)])
    for tool in validate_approved_tools(specialist, approved_tools):
        command.extend(["--approve-tool", tool])
    return command


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=(
            "Run one biological-modelling specialist in a separate, read-only "
            "Codex process with an explicitly restricted MCP set."
        )
    )
    result.add_argument("specialist", choices=sorted(SPECIALISTS))
    prompt_group = result.add_mutually_exclusive_group(required=True)
    prompt_group.add_argument("--prompt", help="Bounded specialist task text")
    prompt_group.add_argument("--prompt-file", help="UTF-8 task file inside the project")
    result.add_argument(
        "--allow-web-search",
        action="store_true",
        help="Enable live web search for the literature reviewer only",
    )
    result.add_argument(
        "--record-session-id",
        help="Expected existing/upstream session ID used to place invocation artifacts",
    )
    result.add_argument(
        "--approve-tool",
        action="append",
        default=[],
        help=(
            "Exact MCP tool already authorized for this bounded invocation; "
            "repeat for multiple tools"
        ),
    )
    result.add_argument(
        "--transport",
        choices=("native", "wsl"),
        default="native",
        help="Use native WSL execution or bridge from Windows through wsl.exe",
    )
    result.add_argument(
        "--launcher-config",
        default=".codex/launcher.local.json",
        help="Ignored local Windows-to-WSL configuration file",
    )
    result.add_argument("--codex-executable", help=argparse.SUPPRESS)
    result.add_argument(
        "--provenance-transport",
        choices=("native-wsl", "windows-wsl"),
        default="native-wsl",
        help=argparse.SUPPRESS,
    )
    return result


def run_windows_bridge(args: argparse.Namespace) -> int:
    try:
        config = load_windows_launcher_config(args.launcher_config)
        command = build_wsl_command(
            config,
            args.specialist,
            prompt=args.prompt,
            prompt_file=args.prompt_file,
            allow_web_search=args.allow_web_search,
            record_session_id=args.record_session_id,
            approved_tools=getattr(args, "approve_tool", []),
        )
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL)
        try:
            return process.wait()
        except KeyboardInterrupt:
            emit_status("Windows-to-WSL launcher interrupted; stopping child")
            stop_process(process)
            return 130
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        emit_status(f"Windows-to-WSL launch failed: {exc}")
        return 2


def run_native(args: argparse.Namespace) -> int:
    started_at = utc_now()
    invocation_id = f"{started_at[:19].replace(':', '')}-{uuid.uuid4()}"
    launcher_started = time.monotonic()
    try:
        prompt_source = (
            resolve_prompt_file(args.prompt_file) if args.prompt_file is not None else None
        )
        prompt = load_prompt(args.prompt, args.prompt_file)
        codex = resolve_codex_executable(args.codex_executable)
        approved_tools = validate_approved_tools(
            args.specialist, getattr(args, "approve_tool", [])
        )
        if args.record_session_id is not None:
            validate_session_id(args.record_session_id)
    except (OSError, ValueError) as exc:
        emit_status(f"preflight failed: {exc}")
        return 2

    profile, _ = SPECIALISTS[args.specialist]
    emit_status(
        f"launcher_run={invocation_id} specialist={args.specialist} "
        f"profile={profile} started"
    )
    local_profile = profile_path(profile)
    if not local_profile.is_file():
        emit_status(
            f"preflight failed: missing user-local Codex profile {local_profile.name}"
        )
        return 2
    try:
        transport_arguments = load_permitted_transport(local_profile, args.specialist)
    except (OSError, ValueError) as exc:
        emit_status(f"preflight failed: invalid user-local specialist profile: {exc}")
        return 2

    execution_environment = os.environ.copy()
    try:
        version_result = subprocess.run(
            [codex, "--version"],
            check=True,
            capture_output=True,
            text=True,
            env=execution_environment,
        )
        version_text = (version_result.stdout + version_result.stderr).strip()
        version = parse_version(version_text)
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        emit_status(f"preflight failed: unable to verify Codex version: {exc}")
        return 2
    if version < MINIMUM_CODEX_VERSION:
        emit_status("preflight failed: Codex 0.153.0 or newer is required")
        return 2

    try:
        pubmed_transport = bool(transport_arguments) and args.specialist == "literature_reviewer"
        inventory_result = subprocess.run(
            build_mcp_list_command(
                codex,
                args.specialist,
                transport_arguments,
                approved_tools,
                pubmed_transport=pubmed_transport,
            ),
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
            env=execution_environment,
        )
        configured = validate_mcp_inventory(
            json.loads(inventory_result.stdout),
            args.specialist,
            pubmed_expected=True if pubmed_transport else None,
        )
    except (
        json.JSONDecodeError,
        OSError,
        subprocess.CalledProcessError,
        ValueError,
    ) as exc:
        emit_status(f"MCP inventory preflight failed: {exc}")
        return 2

    modelling_inventory = ", ".join(
        f"{server}={'enabled' if configured.get(server, False) else 'disabled'}"
        for server in MODELLING_SERVERS
    )
    emit_status(
        f"launcher_run={invocation_id} MCP inventory preflight passed: "
        f"{modelling_inventory}"
    )
    pubmed_available = bool(configured.get("pubmed", False))
    effective_web_search = bool(args.allow_web_search and not pubmed_available)
    if args.specialist == "literature_reviewer":
        literature_backend = (
            "pubmed"
            if pubmed_available
            else "web_search"
            if effective_web_search
            else "unavailable"
        )
        emit_status(
            f"launcher_run={invocation_id} literature backend={literature_backend}"
        )

    if args.specialist == "literature_reviewer" and literature_backend == "unavailable":
        handoff = unavailable_literature_handoff(args.record_session_id)
        final_output = json.dumps(handoff, indent=2, sort_keys=True) + "\n"
        provenance = {
            "schema_version": 1,
            "invocation_id": invocation_id,
            "launcher_run_id": invocation_id,
            "specialist": args.specialist,
            "profile": profile,
            "transport": args.provenance_transport,
            "started_at": started_at,
            "finished_at": utc_now(),
            "codex_version": ".".join(str(part) for part in version),
            "codex_executable_sha256": sha256_file(Path(codex)),
            "mcp_enabled": {
                server: configured.get(server, False) for server in MODELLING_SERVERS
            },
            "approved_mcp_tools": approved_tools,
            "web_search_enabled": False,
            "literature_backend": "unavailable",
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "process_started": False,
            "process_exit_code": None,
            "process_elapsed_seconds": 0.0,
            "event_count": 0,
            "malformed_event_count": 0,
            "event_stream": None,
            "event_stream_credentials_redacted": True,
            "cancelled": False,
            "handoff_parse_error": None,
        }
        try:
            validate_handoff(
                handoff,
                project_root=PROJECT_ROOT,
                expected_specialist=args.specialist,
                expected_session_id=args.record_session_id,
            )
            artifact_dir = record_invocation(
                project_root=PROJECT_ROOT,
                specialist=args.specialist,
                prompt=prompt,
                final_output=final_output,
                handoff=handoff,
                expected_session_id=args.record_session_id,
                provenance=provenance,
                invocation_id=invocation_id,
            )
        except (HandoffValidationError, OSError, ValueError) as error:
            emit_status(f"failed to record blocked literature invocation: {error}")
            return 3
        sys.stdout.write(final_output)
        sys.stdout.flush()
        emit_status(
            f"Recorded specialist invocation: {artifact_dir.relative_to(PROJECT_ROOT)}"
        )
        cleanup_recorded_prompt(prompt_source, artifact_dir)
        emit_status(
            f"launcher_run={invocation_id} final exit status=0 "
            f"elapsed={time.monotonic() - launcher_started:.1f}s"
        )
        return 0

    prompt_digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    try:
        launcher_dir = create_launcher_run(
            project_root=PROJECT_ROOT,
            specialist=args.specialist,
            prompt=prompt,
            launcher_run_id=invocation_id,
        )
        output_path = launcher_dir / "specialist-output.txt"
        emit_status(
            f"launcher_run={invocation_id} event stream="
            f"{(launcher_dir / 'events.jsonl').relative_to(PROJECT_ROOT)}"
        )
        command = build_command(
            codex,
            args.specialist,
            prompt,
            effective_web_search,
            str(output_path),
            transport_arguments,
            approved_tools,
            pubmed_transport=pubmed_transport,
        )
        result = stream_jsonl_process(
            command,
            cwd=PROJECT_ROOT,
            environment=execution_environment,
            event_path=launcher_dir / "events.jsonl",
            specialist=args.specialist,
            profile=profile,
            launcher_run_id=invocation_id,
        )
    except (OSError, ValueError) as exc:
        emit_status(f"specialist launch failed: {exc}")
        return 2

    final_output = (
        output_path.read_text(encoding="utf-8") if output_path.is_file() else ""
    )
    final_output = redact_text(final_output)
    output_path.write_text(final_output, encoding="utf-8")
    sys.stdout.write(final_output)
    sys.stdout.flush()

    handoff = parse_handoff(final_output)
    if handoff is not None:
        sanitized_handoff = sanitize_json_value(handoff)
        assert isinstance(sanitized_handoff, dict)
        handoff = sanitized_handoff
    handoff_error: str | None = None
    if handoff is None:
        handoff_error = "specialist did not return a JSON handoff"
    else:
        try:
            validate_handoff(
                handoff,
                project_root=PROJECT_ROOT,
                expected_specialist=args.specialist,
                expected_session_id=args.record_session_id,
            )
        except HandoffValidationError as error:
            handoff_error = str(error)
    if handoff_error is None and result.malformed_event_count:
        handoff_error = (
            f"Codex emitted {result.malformed_event_count} malformed JSONL event(s)"
        )

    provenance = {
        "schema_version": 1,
        "invocation_id": invocation_id,
        "launcher_run_id": invocation_id,
        "specialist": args.specialist,
        "profile": profile,
        "transport": args.provenance_transport,
        "started_at": started_at,
        "finished_at": utc_now(),
        "codex_version": ".".join(str(part) for part in version),
        "codex_executable_sha256": sha256_file(Path(codex)),
        "mcp_enabled": {
            server: configured.get(server, False) for server in MODELLING_SERVERS
        },
        "approved_mcp_tools": approved_tools,
        "web_search_enabled": effective_web_search,
        "literature_backend": (
            literature_backend if args.specialist == "literature_reviewer" else None
        ),
        "prompt_sha256": prompt_digest,
        "process_exit_code": result.returncode,
        "process_elapsed_seconds": round(result.elapsed_seconds, 3),
        "event_count": result.event_count,
        "malformed_event_count": result.malformed_event_count,
        "event_stream": "events.jsonl",
        "event_stream_credentials_redacted": True,
        "cancelled": result.cancelled,
        "handoff_parse_error": handoff_error,
    }
    try:
        artifact_dir = record_invocation(
            project_root=PROJECT_ROOT,
            specialist=args.specialist,
            prompt=prompt,
            final_output=final_output,
            handoff=handoff,
            expected_session_id=args.record_session_id,
            provenance=provenance,
            invocation_id=invocation_id,
            launcher_dir=launcher_dir,
        )
        emit_status(
            f"Recorded specialist invocation: {artifact_dir.relative_to(PROJECT_ROOT)}"
        )
        cleanup_recorded_prompt(prompt_source, artifact_dir)
    except (OSError, ValueError) as exc:
        emit_status(f"failed to record specialist invocation: {exc}")
        if result.returncode == 0:
            emit_status(
                f"launcher_run={invocation_id} final exit status=3 "
                f"elapsed={time.monotonic() - launcher_started:.1f}s"
            )
            return 3

    if result.cancelled:
        emit_status(
            f"launcher_run={invocation_id} final exit status=130 "
            f"elapsed={time.monotonic() - launcher_started:.1f}s"
        )
        return 130
    if result.returncode != 0:
        emit_status(
            f"launcher_run={invocation_id} final exit status={result.returncode} "
            f"elapsed={time.monotonic() - launcher_started:.1f}s"
        )
        return result.returncode
    if handoff_error is not None:
        emit_status(f"specialist handoff rejected: {handoff_error}")
        emit_status(
            f"launcher_run={invocation_id} final exit status=3 "
            f"elapsed={time.monotonic() - launcher_started:.1f}s"
        )
        return 3
    emit_status(
        f"launcher_run={invocation_id} final exit status=0 "
        f"elapsed={time.monotonic() - launcher_started:.1f}s"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.allow_web_search and args.specialist != "literature_reviewer":
        print(
            "preflight failed: --allow-web-search is valid only for literature_reviewer",
            file=sys.stderr,
        )
        return 2
    if args.transport == "wsl":
        return run_windows_bridge(args)
    return run_native(args)


if __name__ == "__main__":
    raise SystemExit(main())
