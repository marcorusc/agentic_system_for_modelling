"""Specialist launcher config helpers."""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path, PurePosixPath
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]


MINIMUM_CODEX_VERSION = (0, 153, 0)


def require_supported_python() -> None:
    if sys.version_info < (3, 11):
        raise ValueError("Python 3.11 or newer is required")


MODELLING_SERVERS = ("neko", "maboss", "physicell", "biomass")


PUBMED_TOOLS = (
    "search_articles",
    "get_article_metadata",
    "convert_article_ids",
    "get_full_text_article",
    "find_related_articles",
)


SPECIALISTS = {
    "ode_modeler": ("biomodel-ode-modeler", "biomass"),
    "network_curator": ("biomodel-network-curator", "neko"),
    "literature_reviewer": ("biomodel-literature-reviewer", None),
    "boolean_dynamics_modeler": ("biomodel-boolean-dynamics-modeler", "maboss"),
    "multicellular_configurator": ("biomodel-multicellular-configurator", "physicell"),
}


SESSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


MCP_TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


PERMANENTLY_DISABLED_TOOLS = {"delete_session", "clean_generated_files", "close_session"}


WINDOWS_CONFIG_FIELDS = {
    "wsl_executable",
    "distribution",
    "project_path",
    "python_executable",
    "codex_executable",
}


def parse_version(output: str) -> tuple[int, int, int]:
    match = re.search(r"\b(\d+)\.(\d+)\.(\d+)\b", output)
    if match is None:
        raise ValueError("unable to parse Codex version")
    return tuple(int(part) for part in match.groups())


def profile_path(profile: str) -> Path:
    home = os.environ.get("CODEX_HOME") or setup_paths().get("codex_home") or str(Path.home() / ".codex")
    return Path(home).expanduser() / f"{profile}.config.toml"


def setup_paths() -> dict[str, str]:
    """Read only the launcher's two optional installer-managed path overrides."""
    path = PROJECT_ROOT / ".setup/local.json"
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Invalid installer settings in .setup/local.json")
    result = {}
    for key in ("codex_path", "codex_home"):
        if key in value:
            if not isinstance(value[key], str) or not value[key]:
                raise ValueError(f"Invalid installer setting: {key}")
            result[key] = value[key]
    return result


def validate_session_id(session_id: str) -> str:
    if SESSION_ID_RE.fullmatch(session_id) is None:
        raise ValueError(
            "session ID must contain only letters, digits, dot, dash, or underscore"
        )
    return session_id


def normalize_review_kind(specialist: str, review_kind: str | None) -> str | None:
    """Keep evidence modes explicit without applying one to modelling roles."""
    if not isinstance(specialist, str) or specialist not in SPECIALISTS:
        raise ValueError("unknown specialist")
    if specialist != "literature_reviewer":
        if review_kind is not None:
            raise ValueError("review_kind is valid only for literature_reviewer")
        return None
    if review_kind is None:
        return "edge"
    if not isinstance(review_kind, str) or review_kind not in {"edge", "ode"}:
        raise ValueError("unknown literature review kind")
    return review_kind


def resolve_codex_executable(candidate: str | None) -> str:
    raw = candidate or setup_paths().get("codex_path") or shutil.which("codex")
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
    allow_web_search: bool = False,
) -> list[str]:
    _, permitted_server = SPECIALISTS[specialist]
    if not isinstance(allow_web_search, bool):
        raise ValueError("allow_web_search must be a boolean")
    if allow_web_search and specialist != "literature_reviewer":
        raise ValueError("--allow-web-search is valid only for literature_reviewer")
    web_search = "live" if allow_web_search and not pubmed_transport else "disabled"
    # Specialists must not inherit the root's dispatcher and delegate recursively.
    arguments: list[str] = [
        # Built-in connector tools are not listed by `codex mcp list`.
        "-c", "features.apps=false",
        # Cached web search can be enabled by default even without --search.
        # Set the same explicit boundary for preflight and child execution.
        "-c", f'web_search="{web_search}"',
        "-c", 'mcp_servers.specialist_dispatcher={"command"="__disabled_specialist_dispatcher__","enabled"=false}',
    ]
    if permitted_server != "biomass":
        # Existing installations may not define optional BioMASS. A complete
        # disabled transport keeps their config valid without requiring setup.
        arguments.extend([
            "-c",
            'mcp_servers.biomass={"command"="__disabled_biomass__","enabled"=false}',
        ])
    for server in MODELLING_SERVERS:
        enabled = "true" if server == permitted_server else "false"
        arguments.extend(["-c", f"mcp_servers.{server}.enabled={enabled}"])
    if permitted_server is not None:
        arguments.extend(["-c", f"mcp_servers.{permitted_server}.required=true"])
        disabled_tools = ["delete_session", "clean_generated_files"]
        if permitted_server == "biomass":
            disabled_tools.append("close_session")
        arguments.extend([
            "-c",
            f"mcp_servers.{permitted_server}.disabled_tools="
            + json.dumps(disabled_tools, separators=(",", ":")),
        ])
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
    else:
        # Do not inherit an unrestricted global PubMed transport when the
        # specialist profile has no approved literature backend.
        arguments.extend([
            "-c",
            'mcp_servers.pubmed={"command"="__disabled_pubmed__","enabled"=false}',
        ])
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
    require_supported_python()
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
    review_kind: str | None = None,
) -> list[str]:
    review_kind = normalize_review_kind(specialist, review_kind)
    profile, _ = SPECIALISTS[specialist]
    if allow_web_search and specialist != "literature_reviewer":
        raise ValueError("--allow-web-search is valid only for literature_reviewer")

    command = [codex]
    if allow_web_search and not pubmed_transport:
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
            allow_web_search=allow_web_search,
        )
    )
    contract_guidance = ""
    if specialist == "ode_modeler":
        contract_guidance = (
            " Follow docs/ode-contract.md: use specialist=ode_modeler, "
            "stage=biomass_ode, schema_version=1 and ode.contract_version=2. "
            "Preserve provisional versus conclusive export authority; an artifact "
            "capture does not authorize simulation or scientific acceptance."
        )
    elif specialist == "literature_reviewer":
        contract_guidance = f" Return review_kind={review_kind} exactly."
        if review_kind == "ode":
            contract_guidance += (
                " Follow the ODE claim evidence contract in docs/ode-contract.md. "
                "Review only the bounded mechanism, kinetic-law or quantity claims "
                "in this task and use its BioMASS session for evidence provenance."
            )
    command.append(
        f"Act as {specialist}. Follow the active AGENTS.md and your profile's "
        f"developer instructions. Return exactly one JSON typed specialist handoff."
        f" Follow docs/handoff-validation.md: completed results require existing "
        f"hashed stage artifacts. If reports or manifests are still drafts, return "
        f"needs_approval with outstanding work in decisions_required and null "
        f"recommended_next_stage; never claim unwritten files are completed."
        f"{contract_guidance}\n\nTask:\n{prompt}"
    )
    return command


def build_mcp_list_command(
    codex: str,
    specialist: str,
    transport_arguments: list[str] | None = None,
    approved_tools: list[str] | None = None,
    pubmed_transport: bool = False,
    allow_web_search: bool = False,
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
            allow_web_search=allow_web_search,
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
    allowed = {permitted_server} if permitted_server else {"pubmed"}
    unexpected = sorted(name for name, enabled in configured.items() if enabled and name not in allowed)
    if unexpected:
        raise ValueError(f"prohibited MCP servers are enabled: {', '.join(unexpected)}")
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
    review_kind: str | None = None,
) -> list[str]:
    review_kind = normalize_review_kind(specialist, review_kind)
    if review_kind == "ode" and record_session_id is None:
        raise ValueError("ODE literature review requires record_session_id")
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
    if review_kind is not None:
        command.extend(["--review-kind", review_kind])
    if allow_web_search:
        command.append("--allow-web-search")
    if record_session_id is not None:
        command.extend(["--record-session-id", validate_session_id(record_session_id)])
    for tool in validate_approved_tools(specialist, approved_tools):
        command.extend(["--approve-tool", tool])
    return command
