#!/usr/bin/env python3
"""Run non-mutating local prerequisites and MCP-inventory checks."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

try:
    from scripts.codex import run_specialist
except ModuleNotFoundError:  # Direct execution adds scripts/codex, not repo root.
    import run_specialist


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODEL_SPECIALISTS = (
    "network_curator",
    "boolean_dynamics_modeler",
    "multicellular_configurator",
)
REQUIRED_FILES = (
    "AGENTS.md",
    "README.md",
    "MODEL_SPEC.md",
    "DATA_DICTIONARY.md",
    "ASSUMPTIONS.md",
    "DECISIONS.md",
    "CURRENT_STATE.md",
    "VALIDATION_PLAN.md",
    "docs/agentic-biomodelling-architecture.md",
    ".model/config.json",
    ".codex-plugin/plugin.json",
    ".claude/scripts/model_lifecycle.py",
    "scripts/codex/run_specialist.py",
    "scripts/codex/cleanup_tasks.py",
    "scripts/codex/validate_handoff.py",
    "scripts/codex/write_literature_report.py",
)


def _run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def current_branch(project_root: Path) -> str | None:
    result = _run(["git", "branch", "--show-current"], cwd=project_root)
    if result.returncode != 0:
        return None
    branch = result.stdout.strip()
    return branch or None


def required_paths(project_root: Path) -> tuple[list[str], list[str]]:
    required = list(REQUIRED_FILES)
    config_path = project_root / ".model/config.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        reset_files = config.get("reset_files", {})
        if isinstance(reset_files, dict):
            required.extend(
                value for value in reset_files.values() if isinstance(value, str)
            )
    except (OSError, UnicodeError, json.JSONDecodeError):
        pass
    required = sorted(set(required))
    missing = [relative for relative in required if not (project_root / relative).is_file()]
    return required, missing


def codex_version(codex: str, project_root: Path) -> tuple[str | None, bool]:
    result = _run([codex, "--version"], cwd=project_root)
    if result.returncode != 0:
        return None, False
    try:
        version = run_specialist.parse_version(result.stdout + result.stderr)
    except ValueError:
        return None, False
    rendered = ".".join(str(part) for part in version)
    return rendered, version >= run_specialist.MINIMUM_CODEX_VERSION


def _inventory(command: list[str], project_root: Path) -> tuple[list[dict[str, Any]] | None, str | None]:
    result = _run(command, cwd=project_root)
    if result.returncode != 0:
        return None, f"Codex MCP inventory command exited {result.returncode}"
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None, "Codex MCP inventory was not valid JSON"
    if not isinstance(payload, list):
        return None, "Codex MCP inventory was not a list"
    # The returned public report intentionally retains only server names and
    # enabled flags. Commands, arguments, environment variables, and URLs are
    # neither returned nor printed.
    minimal: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            return None, "Codex MCP inventory contained an invalid entry"
        name, enabled = item.get("name"), item.get("enabled")
        if not isinstance(name, str) or not isinstance(enabled, bool):
            return None, "Codex MCP inventory entry lacked name/enabled"
        minimal.append({"name": name, "enabled": enabled})
    return minimal, None


def orchestrator_inventory(codex: str, project_root: Path) -> dict[str, Any]:
    inventory, error = _inventory([codex, "mcp", "list", "--json"], project_root)
    if inventory is None:
        return {"passed": False, "servers": [], "error": error}
    enabled = {item["name"] for item in inventory if item["enabled"]}
    prohibited = sorted(enabled.intersection(run_specialist.MODELLING_SERVERS))
    return {
        "passed": not prohibited,
        "servers": sorted(item["name"] for item in inventory),
        "enabled_modelling_servers": prohibited,
    }


def specialist_inventory(codex: str, specialist: str, project_root: Path) -> dict[str, Any]:
    profile, permitted = run_specialist.SPECIALISTS[specialist]
    local_profile = run_specialist.profile_path(profile)
    if not local_profile.is_file():
        return {
            "passed": False,
            "permitted_server": permitted,
            "servers": [],
            "error": f"missing user-local profile {local_profile.name}",
        }
    try:
        transport = run_specialist.load_permitted_transport(local_profile, specialist)
        command = run_specialist.build_mcp_list_command(codex, specialist, transport)
    except (OSError, ValueError):
        return {
            "passed": False,
            "permitted_server": permitted,
            "servers": [],
            "error": "user-local profile is incomplete or invalid",
        }
    inventory, error = _inventory(command, project_root)
    if inventory is None:
        return {
            "passed": False,
            "permitted_server": permitted,
            "servers": [],
            "error": error,
        }
    try:
        configured = run_specialist.validate_mcp_inventory(inventory, specialist)
    except ValueError as problem:
        return {
            "passed": False,
            "permitted_server": permitted,
            "servers": sorted(item["name"] for item in inventory),
            "error": str(problem),
        }
    return {
        "passed": True,
        "permitted_server": permitted,
        "servers": sorted(item["name"] for item in inventory),
        "enabled_modelling_servers": sorted(
            name
            for name in run_specialist.MODELLING_SERVERS
            if configured.get(name, False)
        ),
    }


def literature_inventory(codex: str, project_root: Path) -> dict[str, Any]:
    profile, _ = run_specialist.SPECIALISTS["literature_reviewer"]
    local_profile = run_specialist.profile_path(profile)
    if not local_profile.is_file():
        return {
            "passed": False,
            "pubmed": False,
            "servers": [],
            "error": f"missing user-local profile {local_profile.name}",
        }
    try:
        transport = run_specialist.load_permitted_transport(
            local_profile, "literature_reviewer"
        )
    except (OSError, ValueError):
        return {
            "passed": False,
            "pubmed": False,
            "servers": [],
            "error": "user-local literature profile is invalid",
        }
    pubmed_transport = bool(transport)
    command = run_specialist.build_mcp_list_command(
        codex,
        "literature_reviewer",
        transport,
        pubmed_transport=pubmed_transport,
    )
    inventory, error = _inventory(command, project_root)
    if inventory is None:
        return {"passed": False, "pubmed": False, "servers": [], "error": error}
    try:
        run_specialist.validate_mcp_inventory(
            inventory,
            "literature_reviewer",
            pubmed_expected=True if pubmed_transport else None,
        )
    except ValueError as problem:
        return {
            "passed": False,
            "pubmed": False,
            "servers": sorted(item["name"] for item in inventory),
            "error": str(problem),
        }
    pubmed = any(item["name"] == "pubmed" and item["enabled"] for item in inventory)
    return {
        "passed": True,
        "pubmed": pubmed,
        "servers": sorted(item["name"] for item in inventory),
    }


def lifecycle_check(project_root: Path) -> dict[str, Any]:
    script = project_root / ".claude/scripts/model_lifecycle.py"
    result = _run([sys.executable, str(script), "--help"], cwd=project_root)
    return {
        "passed": result.returncode == 0,
        "script": ".claude/scripts/model_lifecycle.py",
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "dependencies": "standard-library",
    }


def check_environment(
    *,
    project_root: Path,
    codex: str,
    expected_branch: str,
    allow_web_search: bool,
) -> dict[str, Any]:
    branch = current_branch(project_root)
    required, missing = required_paths(project_root)
    version, version_passed = codex_version(codex, project_root)
    parent = orchestrator_inventory(codex, project_root) if version_passed else {
        "passed": False,
        "servers": [],
        "error": "Codex version check failed",
    }
    specialists = {
        specialist: specialist_inventory(codex, specialist, project_root)
        for specialist in MODEL_SPECIALISTS
    } if version_passed else {
        specialist: {"passed": False, "servers": [], "error": "Codex version check failed"}
        for specialist in MODEL_SPECIALISTS
    }
    literature = literature_inventory(codex, project_root) if version_passed else {
        "passed": False,
        "pubmed": False,
        "servers": [],
        "error": "Codex version check failed",
    }
    backend = "pubmed" if literature.get("pubmed") else (
        "web_search" if allow_web_search else "unavailable"
    )
    lifecycle = lifecycle_check(project_root)
    required_passed = not missing
    branch_passed = branch == expected_branch
    passed = all(
        (
            branch_passed,
            required_passed,
            version_passed,
            bool(parent.get("passed")),
            all(bool(item.get("passed")) for item in specialists.values()),
            lifecycle["passed"],
        )
    )
    return {
        "schema_version": 1,
        "passed": passed,
        "branch": {"current": branch, "expected": expected_branch, "passed": branch_passed},
        "required_files": {"passed": required_passed, "checked": required, "missing": missing},
        "codex": {
            "version": version,
            "minimum_version": ".".join(map(str, run_specialist.MINIMUM_CODEX_VERSION)),
            "passed": version_passed,
        },
        "orchestrator_isolation": parent,
        "specialists": specialists,
        "literature": {
            **literature,
            "backend": backend,
            "degraded": not bool(literature.get("pubmed")),
            "web_search_explicitly_enabled": allow_web_search,
        },
        "lifecycle": lifecycle,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-branch", default="codex-compatible")
    parser.add_argument("--allow-web-search", action="store_true")
    parser.add_argument("--codex-executable", help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    try:
        codex = run_specialist.resolve_codex_executable(arguments.codex_executable)
        report = check_environment(
            project_root=PROJECT_ROOT,
            codex=codex,
            expected_branch=arguments.expected_branch,
            allow_web_search=arguments.allow_web_search,
        )
    except (OSError, ValueError) as error:
        print(json.dumps({"schema_version": 1, "passed": False, "error": str(error)}))
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
