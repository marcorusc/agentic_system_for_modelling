"""Shared isolated specialist execution; no scientific routing decisions."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from scripts.codex.validate_handoff import HandoffValidationError, validate_handoff
from scripts.codex.launcher_config import (
    PROJECT_ROOT, MINIMUM_CODEX_VERSION, MODELLING_SERVERS, SPECIALISTS,
    resolve_codex_executable,
    profile_path, load_permitted_transport, parse_version,
    build_mcp_list_command, validate_mcp_inventory, build_command,
)
from scripts.codex.launcher_process import (
    emit_status, stream_jsonl_process, redact_text, sanitize_json_value,
)
from scripts.codex.launcher_provenance import (
    utc_now, sha256_file, create_launcher_run, record_invocation,
)
from .models import SpecialistInvocationRequest, SpecialistExecutionResult, ExecutionState


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


def _run(request: SpecialistInvocationRequest, execution: SpecialistExecutionResult,
         *, codex_executable: str | None = None) -> int:
    started_at = execution.started_at
    invocation_id = execution.invocation_id
    launcher_started = time.monotonic()
    prompt = request.task
    try:
        codex = resolve_codex_executable(codex_executable)
        approved_tools = list(request.approved_tools)
    except (OSError, ValueError) as exc:
        execution.handoff_error = redact_text(str(exc))
        emit_status(f"preflight failed: {exc}")
        return 2

    profile, _ = SPECIALISTS[request.specialist]
    emit_status(
        f"launcher_run={invocation_id} specialist={request.specialist} "
        f"profile={profile} started"
    )
    local_profile = profile_path(profile)
    if not local_profile.is_file():
        execution.handoff_error = f"Missing user-local Codex profile {local_profile.name}"
        emit_status(
            f"preflight failed: missing user-local Codex profile {local_profile.name}"
        )
        return 2
    try:
        transport_arguments = load_permitted_transport(local_profile, request.specialist)
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
        pubmed_transport = bool(transport_arguments) and request.specialist == "literature_reviewer"
        inventory_result = subprocess.run(
            build_mcp_list_command(
                codex,
                request.specialist,
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
            request.specialist,
            pubmed_expected=pubmed_transport,
        )
    except (
        json.JSONDecodeError,
        OSError,
        subprocess.CalledProcessError,
        ValueError,
    ) as exc:
        execution.handoff_error = redact_text(str(exc))
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
    effective_web_search = bool(request.allow_web_search and not pubmed_available)
    if request.specialist == "literature_reviewer":
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

    if request.specialist == "literature_reviewer" and literature_backend == "unavailable":
        handoff = unavailable_literature_handoff(request.record_session_id)
        final_output = json.dumps(handoff, indent=2, sort_keys=True) + "\n"
        handoff_error = None
        provenance = {
            "schema_version": 1,
            "invocation_id": invocation_id,
            "launcher_run_id": invocation_id,
            "specialist": request.specialist,
            "profile": profile,
            "transport": request.provenance_transport,
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
                expected_specialist=request.specialist,
                expected_session_id=request.record_session_id,
            )
            artifact_dir = record_invocation(
                project_root=PROJECT_ROOT,
                specialist=request.specialist,
                prompt=prompt,
                final_output=final_output,
                handoff=handoff,
                expected_session_id=request.record_session_id,
                provenance=provenance,
                invocation_id=invocation_id,
            )
        except (HandoffValidationError, OSError, ValueError) as error:
            emit_status(f"failed to record blocked literature invocation: {error}")
            return 3
        execution.artifact_dir = artifact_dir
        execution.event_stream = (
            artifact_dir / "events.jsonl" if (artifact_dir / "events.jsonl").is_file() else None
        )
        execution.handoff = handoff if handoff_error is None else None
        emit_status(
            f"Recorded specialist invocation: {artifact_dir.relative_to(PROJECT_ROOT)}"
        )
        emit_status(
            f"launcher_run={invocation_id} final exit status=0 "
            f"elapsed={time.monotonic() - launcher_started:.1f}s"
        )
        return 0

    prompt_digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    try:
        launcher_dir = create_launcher_run(
            project_root=PROJECT_ROOT,
            specialist=request.specialist,
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
            request.specialist,
            prompt,
            effective_web_search,
            str(output_path),
            transport_arguments,
            approved_tools,
            pubmed_transport=pubmed_transport,
        )
        execution.artifact_dir = launcher_dir
        execution.event_stream = launcher_dir / "events.jsonl"
        execution.execution_state = ExecutionState.RUNNING
        result = stream_jsonl_process(
            command,
            cwd=PROJECT_ROOT,
            environment=execution_environment,
            event_path=launcher_dir / "events.jsonl",
            specialist=request.specialist,
            profile=profile,
            launcher_run_id=invocation_id,
        )
    except (OSError, ValueError) as exc:
        emit_status(f"specialist launch failed: {exc}")
        return 2

    execution.execution_state = ExecutionState.VALIDATING
    final_output = (
        output_path.read_text(encoding="utf-8") if output_path.is_file() else ""
    )
    final_output = redact_text(final_output)
    output_path.write_text(final_output, encoding="utf-8")

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
                expected_specialist=request.specialist,
                expected_session_id=request.record_session_id,
            )
        except HandoffValidationError as error:
            handoff_error = str(error)
    if handoff_error is None and result.malformed_event_count:
        handoff_error = (
            f"Codex emitted {result.malformed_event_count} malformed JSONL event(s)"
        )

    execution.handoff_error = handoff_error
    execution.execution_state = ExecutionState.RECORDING
    provenance = {
        "schema_version": 1,
        "invocation_id": invocation_id,
        "launcher_run_id": invocation_id,
        "specialist": request.specialist,
        "profile": profile,
        "transport": request.provenance_transport,
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
            literature_backend if request.specialist == "literature_reviewer" else None
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
            specialist=request.specialist,
            prompt=prompt,
            final_output=final_output,
            handoff=handoff,
            expected_session_id=request.record_session_id,
            provenance=provenance,
            invocation_id=invocation_id,
            launcher_dir=launcher_dir,
        )
        execution.artifact_dir = artifact_dir
        execution.event_stream = (
            artifact_dir / "events.jsonl" if (artifact_dir / "events.jsonl").is_file() else None
        )
        execution.handoff = handoff if handoff_error is None else None
        emit_status(
            f"Recorded specialist invocation: {artifact_dir.relative_to(PROJECT_ROOT)}"
        )
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


def execute(request: SpecialistInvocationRequest, *,
            codex_executable: str | None = None) -> SpecialistExecutionResult:
    """Execute directly in this process; only the isolated Codex child is spawned.

    Executable overrides are internal/CLI-only and never part of the MCP contract.
    """
    started_at = utc_now()
    execution = SpecialistExecutionResult(
        invocation_id=f"{started_at[:19].replace(':', '')}-{uuid.uuid4()}",
        started_at=started_at,
        execution_state=ExecutionState.PREFLIGHTING,
    )
    try:
        code = _run(request, execution, codex_executable=codex_executable)
    except (OSError, ValueError) as error:
        execution.handoff_error = redact_text(str(error))
        emit_status(f"specialist execution failed: {error}")
        code = 3
    if code != 0:
        execution.handoff = None
    execution.return_code = code
    execution.finished_at = utc_now()
    execution.execution_state = (
        ExecutionState.SUCCEEDED if code == 0 else
        ExecutionState.CANCELLED if code == 130 else ExecutionState.FAILED
    )
    if code != 0 and execution.handoff_error is None:
        execution.handoff_error = f"Specialist execution failed (exit {code}); see launcher diagnostics"
    return execution
