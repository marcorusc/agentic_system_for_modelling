#!/usr/bin/env python3
"""Launch one specialist Codex process with enforced MCP isolation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

try:
    from scripts.codex.cleanup_tasks import consume_recorded_task
    from scripts.codex.validate_handoff import (
        HandoffValidationError,
        validate_handoff,
    )
except ModuleNotFoundError:  # Direct execution adds scripts/codex, not repo root.
    from cleanup_tasks import consume_recorded_task
    from validate_handoff import HandoffValidationError, validate_handoff


# Compatibility re-exports; implementation lives in the focused modules below.
try:
    from scripts.codex.launcher_config import (
        PROJECT_ROOT,
        MINIMUM_CODEX_VERSION,
        MODELLING_SERVERS,
        PUBMED_TOOLS,
        SPECIALISTS,
        SESSION_ID_RE,
        MCP_TOOL_NAME_RE,
        PERMANENTLY_DISABLED_TOOLS,
        WINDOWS_CONFIG_FIELDS,
        parse_version,
        profile_path,
        validate_session_id,
        resolve_codex_executable,
        validate_approved_tools,
        mcp_config_arguments,
        toml_literal,
        load_permitted_transport,
        build_command,
        build_mcp_list_command,
        validate_mcp_inventory,
        load_windows_launcher_config,
        validate_wsl_prompt_file,
        build_wsl_command,
    )
    from scripts.codex.launcher_process import (
        HEARTBEAT_INTERVAL_SECONDS,
        LIVE_VALUE_LIMIT,
        SENSITIVE_FIELD_RE,
        SENSITIVE_ASSIGNMENT_RE,
        AUTH_SCHEME_RE,
        OPENAI_KEY_RE,
        URL_CREDENTIAL_RE,
        JSON_SENSITIVE_ASSIGNMENT_RE,
        StreamResult,
        redact_text,
        sanitize_json_value,
        compact_live_value,
        emit_status,
        summarize_event,
        persist_event_line,
        stop_process,
        stream_jsonl_process,
    )
    from scripts.codex.launcher_provenance import (
        RUN_ROOTS,
        utc_now,
        sha256_file,
        write_json,
        specialist_run_base,
        create_launcher_run,
        record_invocation,
    )
except ModuleNotFoundError:  # Direct script execution.
    from launcher_config import (
        PROJECT_ROOT,
        MINIMUM_CODEX_VERSION,
        MODELLING_SERVERS,
        PUBMED_TOOLS,
        SPECIALISTS,
        SESSION_ID_RE,
        MCP_TOOL_NAME_RE,
        PERMANENTLY_DISABLED_TOOLS,
        WINDOWS_CONFIG_FIELDS,
        parse_version,
        profile_path,
        validate_session_id,
        resolve_codex_executable,
        validate_approved_tools,
        mcp_config_arguments,
        toml_literal,
        load_permitted_transport,
        build_command,
        build_mcp_list_command,
        validate_mcp_inventory,
        load_windows_launcher_config,
        validate_wsl_prompt_file,
        build_wsl_command,
    )
    from launcher_process import (
        HEARTBEAT_INTERVAL_SECONDS,
        LIVE_VALUE_LIMIT,
        SENSITIVE_FIELD_RE,
        SENSITIVE_ASSIGNMENT_RE,
        AUTH_SCHEME_RE,
        OPENAI_KEY_RE,
        URL_CREDENTIAL_RE,
        JSON_SENSITIVE_ASSIGNMENT_RE,
        StreamResult,
        redact_text,
        sanitize_json_value,
        compact_live_value,
        emit_status,
        summarize_event,
        persist_event_line,
        stop_process,
        stream_jsonl_process,
    )
    from launcher_provenance import (
        RUN_ROOTS,
        utc_now,
        sha256_file,
        write_json,
        specialist_run_base,
        create_launcher_run,
        record_invocation,
    )


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


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=(
            "Run one biological-modelling specialist in a separate, read-only "
            "Codex process with an explicitly restricted MCP set."
        )
    )
    result.add_argument("specialist", choices=sorted(SPECIALISTS))
    result.add_argument("--review-kind", choices=("edge", "ode"), default="edge")
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
            review_kind=getattr(args, "review_kind", "edge"),
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
    review_kind = getattr(args, "review_kind", "edge")
    if review_kind == "ode" and (args.specialist != "literature_reviewer" or not args.record_session_id):
        emit_status("ODE literature review requires literature_reviewer and --record-session-id")
        return 2
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
            pubmed_expected=pubmed_transport,
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
        handoff["review_kind"] = review_kind
        final_output = json.dumps(handoff, indent=2, sort_keys=True) + "\n"
        provenance = {
            "schema_version": 1,
            "invocation_id": invocation_id,
            "launcher_run_id": invocation_id,
            "specialist": args.specialist,
            "review_kind": review_kind if args.specialist == "literature_reviewer" else None,
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
                expected_review_kind=review_kind if args.specialist == "literature_reviewer" else None,
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
                review_kind=review_kind,
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
            review_kind=review_kind,
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
        if args.specialist == "literature_reviewer":
            command[-1] += f"\nRequired review_kind={review_kind}; include it in the typed result."
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
                expected_review_kind=review_kind if args.specialist == "literature_reviewer" else None,
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
        "review_kind": review_kind if args.specialist == "literature_reviewer" else None,
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
            review_kind=review_kind,
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
    if sys.version_info < (3, 11):
        print("Python 3.11 or newer is required.", file=sys.stderr)
        return 2
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
