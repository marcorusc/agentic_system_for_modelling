"""Render isolated profiles while retaining unrelated user settings."""
from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path
from typing import Any

from scripts.codex.launcher_config import SPECIALISTS, MODELLING_SERVERS, toml_literal
from .state import SetupError
from .environment import transport_path


def render(root: Path, prefix: Path, codex_home: Path, *, with_biomass: bool = False) -> dict[Path, str]:
    parent = tomllib.loads((root/".codex/config.toml").read_text())
    for server in MODELLING_SERVERS:
        if parent.get("mcp_servers", {}).get(server, {}).get("enabled") is not False:
            raise SetupError(f"Parent isolation is unsafe: {server} must remain disabled in .codex/config.toml")
    outputs = {}
    for role, (profile, server) in SPECIALISTS.items():
        if role == "ode_modeler" and not with_biomass:
            continue
        target = codex_home/f"{profile}.config.toml"
        if target.is_symlink():
            raise SetupError(f"Refusing symlink profile: {target}")
        source = target if target.exists() else root/".codex/profiles"/f"{profile}.config.toml.example"
        payload = tomllib.loads(source.read_text(encoding="utf-8"))
        servers = payload.setdefault("mcp_servers", {})
        for name, config in servers.items():
            if name not in {server, "pubmed" if server is None else server} and config.get("enabled", True):
                raise SetupError(f"Unexpected enabled MCP in {target.name}: {name}")
        for prohibited in MODELLING_SERVERS:
            if prohibited != server:
                servers.setdefault(prohibited, {"command": f"__disabled_{prohibited}__"})["enabled"] = False
        if server:
            transport = servers.setdefault(server, {})
            transport.pop("url", None)
            transport.update(command=str(prefix/"bin"/f"mcp-{server}-server"), args=[],
                             cwd=str(root), enabled=True, required=True)
            env = transport.setdefault("env", {})
            env.update(CONDA_PREFIX=str(prefix), PATH=transport_path(prefix),
                       PYTHONNOUSERSITE="1")
        if with_biomass and role == "literature_reviewer":
            directive = "ODE review mode: when review_kind=ode, follow docs/ode-workflow.md instead of the edge-only input/output contract. Require the BioMASS session and literal bounded claims; return review_kind=ode, draft ODE reports and no modelling calls."
            if "ODE review mode:" not in payload.get("developer_instructions", ""):
                payload["developer_instructions"] = payload.get("developer_instructions", "") + "\n" + directive
        if server == "biomass":
            env.update(NUMBA_CACHE_DIR=str(root/".setup/cache/biomass-numba"), PYTHONDONTWRITEBYTECODE="1")
        # TOML values are parsed and reserialized; arbitrary unrelated values survive.
        text = "# Generated transport paths; managed by scripts/setup.py\n"
        text += "\n".join(f"{toml_literal(key)} = {toml_literal(value)}" for key, value in payload.items()) + "\n"
        tomllib.loads(text)
        outputs[target] = text
    return outputs


def _cli_json(executable: str, arguments: list[str], root: Path) -> dict[str, Any]:
    from .detect import run

    result = run([executable, *arguments, "--json"], cwd=root)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise SetupError(f"Codex returned malformed JSON for {' '.join(arguments)}") from error
    if not isinstance(payload, dict):
        raise SetupError(f"Codex returned an invalid JSON object for {' '.join(arguments)}")
    return payload


def _objects(payload: dict[str, Any], field: str) -> list[dict[str, Any]]:
    values = payload.get(field)
    if not isinstance(values, list) or not all(isinstance(value, dict) for value in values):
        raise SetupError(f"Codex plugin JSON is missing a valid {field} array")
    return values


def _same_path(value: object, expected: Path) -> bool:
    return isinstance(value, str) and Path(value).expanduser().resolve(strict=False) == expected.resolve(strict=True)


def _plugin_problem(entry: dict[str, Any], *, root: Path, version: str,
                    marketplace: str, plugin_id: str) -> str | None:
    if entry.get("pluginId") != plugin_id or entry.get("marketplaceName") != marketplace:
        return "plugin identity does not match the repository marketplace"
    if entry.get("installed") is not True:
        return "plugin is not installed"
    if entry.get("enabled") is not True:
        return "plugin is not enabled"
    if entry.get("version") != version:
        return f"plugin version is {entry.get('version')!r}, expected {version!r}"
    source = entry.get("source")
    if not isinstance(source, dict) or not _same_path(source.get("path"), root):
        return "plugin source path does not match this repository"
    marketplace_source = entry.get("marketplaceSource")
    if not isinstance(marketplace_source, dict) or not _same_path(
        marketplace_source.get("source"), root
    ):
        return "plugin marketplace source does not match this repository"
    return None


def ensure_plugin(root: Path, executable: str, *, check: bool = False) -> None:
    from .detect import run

    marketplace = "agentic-modelling-local"
    plugin = "agentic-system-for-modelling"
    plugin_id = f"{plugin}@{marketplace}"
    project = root.resolve(strict=True)
    manifest = json.loads((project / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
    version = manifest.get("version") if isinstance(manifest, dict) else None
    if not isinstance(version, str) or not version:
        raise SetupError("Codex plugin manifest has no valid version")

    marketplace_payload = _cli_json(
        executable, ["plugin", "marketplace", "list"], project
    )
    marketplaces = [
        entry for entry in _objects(marketplace_payload, "marketplaces")
        if entry.get("name") == marketplace
    ]
    if len(marketplaces) > 1:
        raise SetupError(f"Codex reports duplicate marketplace entries for {marketplace}")
    if marketplaces and not _same_path(marketplaces[0].get("root"), project):
        raise SetupError(f"Codex marketplace {marketplace} points to a different repository")
    if not marketplaces:
        if check:
            raise SetupError("Codex local plugin marketplace is missing; rerun setup")
        run([executable, "plugin", "marketplace", "add", str(project)], cwd=project)
        marketplace_payload = _cli_json(
            executable, ["plugin", "marketplace", "list"], project
        )
        marketplaces = [
            entry for entry in _objects(marketplace_payload, "marketplaces")
            if entry.get("name") == marketplace
        ]
        if len(marketplaces) != 1 or not _same_path(marketplaces[0].get("root"), project):
            raise SetupError("Codex did not register the expected local marketplace")

    plugin_payload = _cli_json(executable, ["plugin", "list"], project)
    installed = [
        entry for entry in _objects(plugin_payload, "installed")
        if entry.get("pluginId") == plugin_id
    ]
    if len(installed) > 1:
        raise SetupError(f"Codex reports duplicate installed entries for {plugin_id}")
    problem = (
        _plugin_problem(
            installed[0], root=project, version=version,
            marketplace=marketplace, plugin_id=plugin_id,
        )
        if installed else "plugin is not installed"
    )
    if problem is not None:
        if check:
            raise SetupError(f"Codex modelling plugin is stale or unavailable: {problem}; rerun setup")
        run([executable, "plugin", "add", plugin_id], cwd=project, timeout=120)
        plugin_payload = _cli_json(executable, ["plugin", "list"], project)
        installed = [
            entry for entry in _objects(plugin_payload, "installed")
            if entry.get("pluginId") == plugin_id
        ]
        if len(installed) != 1:
            raise SetupError("Codex did not install exactly one expected modelling plugin")
        problem = _plugin_problem(
            installed[0], root=project, version=version,
            marketplace=marketplace, plugin_id=plugin_id,
        )
        if problem is not None:
            raise SetupError(f"Codex modelling plugin verification failed: {problem}")
