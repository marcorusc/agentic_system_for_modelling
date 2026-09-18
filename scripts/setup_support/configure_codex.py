"""Render isolated profiles while retaining unrelated user settings."""
from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

from scripts.codex.launcher_config import SPECIALISTS, MODELLING_SERVERS, toml_literal
from .state import SetupError
from .environment import transport_path


# Base setup remains independent of the optional ODE environment.
SETUP_SPECIALISTS = (
    "network_curator", "literature_reviewer",
    "boolean_dynamics_modeler", "multicellular_configurator",
)


# Exact policy shipped at 1e8f9a43c4fc249e43d94c71316fc798ee7ad01d. Migrate
# this sentence only; never replace an installed profile's full instruction text.
LEGACY_ODE_EXPORT_RULE = (
    "Export_model_bundle is conclusive: call only when this invocation explicitly "
    "records researcher approval of the reviewed revision and requests final export."
)
ODE_EXPORT_RULE = (
    "For ODE contract version 2, export_model_bundle may preserve an already "
    "authorized provisional candidate. Conclusive export requires researcher "
    "approval of the exact reviewed revision and an explicit final-export request."
)

# Replace our previously appended guidance as a unit so reruns do not accumulate
# obsolete or conflicting setup-owned directives. Unrelated instructions survive.
_PREVIOUS_ODE_PROFILE_GUIDANCE = {
    "literature_reviewer": (
        "ODE review mode: review_kind=edge (default) preserves edge review. With "
        "review_kind=ode, require the full BioMASS session ID and at most 13 literal "
        "coherent claims; follow docs/ode-contract.md for immutable claim reports "
        "and return review_kind=ode. Never call a modelling MCP or delegate."
    ),
    "ode_modeler": (
        "ODE contract version 2: follow skills/biomass-workflow/SKILL.md and "
        "docs/ode-contract.md: schema_version=1, stage=biomass_ode, "
        "ode.contract_version=2. Preserve provisional candidates within an already "
        "authorized workflow with workflow_authorization; this grants no simulation "
        "or scientific acceptance. Conclusive export requires exact-revision "
        "export_approval."
    ),
}
ODE_PROFILE_GUIDANCE = {
    "literature_reviewer": (
        "ODE review mode: review_kind=edge (default) preserves existing edge-review "
        "rules. Only when the invocation explicitly sets review_kind=ode, apply "
        "the claim-review contract in docs/ode-contract.md instead of edge-specific "
        "input, report and lineage requirements. Require the full BioMASS "
        "record_session_id and at most 13 literal coherent claims with stable IDs; "
        "return review_kind=ode and immutable report drafts for "
        "evidence/reports/{biomass_session_id}/ode/{claim_id}.md. Preserve all tool "
        "isolation and search-authorization rules in both modes: never call a "
        "modelling MCP, app connectors or the dispatcher, and never delegate. "
        "Return blocked if an authorized evidence backend is unavailable."
    ),
    "ode_modeler": (
        "ODE contract version 2 (ode_modeler only): follow "
        "skills/biomass-workflow/SKILL.md and docs/ode-contract.md: "
        "schema_version=1, stage=biomass_ode, ode.contract_version=2. Use only "
        "BioMASS; never call another modelling MCP, literature-search tools, "
        "app connectors or the dispatcher, and never delegate. An already "
        "authorized whole-model drafting workflow may prepare proposed assumptions "
        "for consolidated review and preserve a server-side candidate bundle; it "
        "does not accept those assumptions, authorize simulation or advance a "
        "scientific stage. Conclusive export requires exact-revision researcher "
        "approval, export_approval and an explicit export request. A new-session "
        "invocation may finish the complete authorized workflow before returning "
        "its ID; do not force a bootstrap return merely to bind the existing "
        "preservation authority to that ID. Before verified project capture, "
        "return a metadata-only needs_approval result with ode.export_status=pending, "
        "artifacts=[], simulation_paths=[], recommended_next_stage=null, and no "
        "revision_path, bundle_path, workflow_authorization or export_approval "
        "claim. Return the actual server revision/version, server_artifacts "
        "inventory/hashes, actions and draft report; identify pending parent "
        "recording separately from scientific decisions. Because needs_approval "
        "requires nonempty decisions_required, list technical parent recording "
        "there with the prefix Technical parent recording only; this requests no "
        "renewed researcher approval. List actual scientific decisions separately. "
        "The parent records the "
        "existing workflow authority against the returned full session ID, captures "
        "and verifies the inventory, and creates a separate validated provisional "
        "completion with matching manifest/report, project paths/hashes and "
        "workflow_authorization. Preserve the original specialist result. Do not "
        "request another scientific approval merely to preserve this candidate. "
        "Treat server-assumed mechanisms as proposed unless a researcher decision "
        "accepts them; small-subsystem examples do not impose repeated approval "
        "gates within authorized whole-model drafting."
    ),
}

# Clarify the existing null-session validator case without changing its schema.
# Retain the exact previous setup-owned directive for idempotent migration.
_ODE_GUIDANCE_BEFORE_PRESESSION = ODE_PROFILE_GUIDANCE["ode_modeler"]
_ODE_PRESESSION_GUIDANCE = (
    "For a pre-session blocked or failed result with session_id=null and "
    "derived_from_session_id=null, when no scientific input, revision or artifacts "
    "exist, omit the entire ode object. Do not fabricate ODE provenance or return "
    "a partial ode object."
)
ODE_PROFILE_GUIDANCE["ode_modeler"] = _ODE_GUIDANCE_BEFORE_PRESESSION.replace(
    "schema_version=1, stage=biomass_ode, ode.contract_version=2.",
    "schema_version=1, stage=biomass_ode. For scientific ODE results, include "
    "complete ode metadata with ode.contract_version=2. " + _ODE_PRESESSION_GUIDANCE,
).replace(
    "Before verified project capture, return a metadata-only needs_approval result",
    "For a scientific ODE result awaiting verified project capture, return a "
    "metadata-only needs_approval result",
)


# Recognize only direct blanket restrictions, not arbitrary custom scientific
# policies. A near-match to the known rule must be reviewed, not silently relaxed.
_CUSTOM_ODE_EXPORT_RESTRICTION = re.compile(
    r"\bexport_model_bundle\s+is\s+(?:always\s+)?conclusive\b"
    r"|\bexport_model_bundle\s+(?:(?:may|must|can|should)\s+)?"
    r"(?:be\s+(?:called|used)\s+)?(?:only|never)\b"
    r"|\b(?:never|do\s+not)\s+(?:preserve|save|export)\s+(?:any\s+)?provisional\b",
    re.IGNORECASE,
)


def _ode_instructions(role: str, instructions: str, target: Path) -> str:
    if not isinstance(instructions, str):
        raise SetupError(f"Expected text developer_instructions in {target.name}")
    if role == "ode_modeler":
        instructions = instructions.replace(LEGACY_ODE_EXPORT_RULE, ODE_EXPORT_RULE)
        if _CUSTOM_ODE_EXPORT_RESTRICTION.search(instructions):
            raise SetupError(
                f"Unrecognized ODE export restriction in {target.name}; review its "
                "custom developer_instructions against docs/ode-contract.md. "
                "Setup has not overwritten the profile."
            )
    directive = ODE_PROFILE_GUIDANCE[role]
    if role == "ode_modeler":
        instructions = instructions.replace(_ODE_GUIDANCE_BEFORE_PRESESSION, directive)
        # Correct only the exact envelope/capture wording shipped in our template.
        instructions = instructions.replace(
            "and ode.contract_version=2 with the provenance required by docs/ode-contract.md.",
            "and the common envelope fields required by docs/ode-contract.md. For scientific "
            "ODE results, include complete ode metadata with ode.contract_version=2. "
            + _ODE_PRESESSION_GUIDANCE,
        ).replace(
            "Before parent capture, return a metadata-only needs_approval handoff",
            "For a scientific ODE result awaiting parent capture, return a metadata-only needs_approval handoff",
        )
    instructions = instructions.replace(_PREVIOUS_ODE_PROFILE_GUIDANCE[role], directive)
    if directive not in instructions:
        instructions += "\n" + directive
    return instructions


def render(root: Path, prefix: Path, codex_home: Path, *, with_biomass: bool = False,
           graphviz_path: str | None = None) -> dict[Path, str]:
    parent = tomllib.loads((root/".codex/config.toml").read_text())
    for server in MODELLING_SERVERS:
        if parent.get("mcp_servers", {}).get(server, {}).get("enabled") is not False:
            raise SetupError(f"Parent isolation is unsafe: {server} must remain disabled in .codex/config.toml")
    outputs = {}
    roles = SETUP_SPECIALISTS + (("ode_modeler",) if with_biomass else ())
    for role in roles:
        profile, server = SPECIALISTS[role]
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
        payload.setdefault("features", {})["apps"] = False
        servers.setdefault("specialist_dispatcher", {"command": "__disabled_specialist_dispatcher__"})["enabled"] = False
        if server:
            transport = servers.setdefault(server, {})
            transport.pop("url", None)
            transport.update(command=str(prefix/"bin"/f"mcp-{server}-server"), args=[],
                             cwd=str(root), enabled=True, required=True)
            env = transport.setdefault("env", {})
            env.update(CONDA_PREFIX=str(prefix), PATH=transport_path(prefix, graphviz_path=graphviz_path),
                       PYTHONNOUSERSITE="1")
        if server == "biomass":
            env.update(NUMBA_CACHE_DIR=str(root/".setup/cache/biomass-numba"), PYTHONDONTWRITEBYTECODE="1")
            disabled = transport.setdefault("disabled_tools", [])
            for tool in ("delete_session", "clean_generated_files", "close_session"):
                if tool not in disabled:
                    disabled.append(tool)
        if with_biomass and role in ODE_PROFILE_GUIDANCE:
            payload["developer_instructions"] = _ode_instructions(
                role, payload.get("developer_instructions", ""), target
            )
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
