#!/usr/bin/env python3
"""Launch one specialist Codex process with enforced MCP isolation."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
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


try:
    from scripts.codex.specialist_runtime import executor
    from scripts.codex.specialist_runtime.models import SpecialistInvocationRequest
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.codex.specialist_runtime import executor
    from scripts.codex.specialist_runtime.models import SpecialistInvocationRequest

parse_handoff = executor.parse_handoff
unavailable_literature_handoff = executor.unavailable_literature_handoff


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
    try:
        prompt_source = resolve_prompt_file(args.prompt_file) if args.prompt_file else None
        request = SpecialistInvocationRequest(
            specialist=args.specialist,
            task=load_prompt(args.prompt, args.prompt_file),
            record_session_id=args.record_session_id,
            approved_tools=tuple(getattr(args, "approve_tool", [])),
            allow_web_search=args.allow_web_search,
            provenance_transport=args.provenance_transport,
        )
    except (OSError, ValueError) as exc:
        emit_status(f"preflight failed: {exc}")
        return 2
    try:
        result = executor.execute(request, codex_executable=args.codex_executable)
    except (OSError, ValueError) as exc:
        emit_status(f"specialist preparation failed: {exc}")
        return 3
    if result.artifact_dir is not None:
        output = result.artifact_dir / "specialist-output.txt"
        if output.is_file():
            sys.stdout.write(output.read_text(encoding="utf-8"))
            sys.stdout.flush()
        if (result.artifact_dir / "provenance.json").is_file():
            cleanup_recorded_prompt(prompt_source, result.artifact_dir)
    return result.return_code


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
