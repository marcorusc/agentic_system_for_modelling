"""Specialist launcher process helpers."""

from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, NamedTuple, TextIO


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
