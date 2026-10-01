"""Read-only process diagnostics, with explicit readiness limits."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from scripts.codex import check_environment
from .detect import run
from .environment import runtime_env
from .state import SetupError

# Shared names (run_simulation, create_session, etc.) do not establish identity.
SIGNATURES = {
    "neko": {"create_network", "export_neko_handoff"},
    "maboss": {"get_maboss_nodes", "run_simulation"},
    "physicell": {"export_xml_configuration"},
    "biomass": {"create_session", "build_reactions", "inspect_reactions", "configure_model", "generate_model",
                "import_neko_handoff", "import_text", "import_text_file", "set_evidence",
                "validate_model", "run_simulation", "export_model_bundle"},
}
UNIQUE_TOOLS = {"neko": "create_network", "maboss": "get_maboss_nodes",
                "physicell": "export_xml_configuration", "biomass": "build_reactions"}


def probe_servers(prefix: Path, *, with_biomass: bool = False,
                  graphviz_path: str | None = None) -> dict:
    errors, inventories = [], {}
    root = Path(__file__).resolve().parents[2]
    servers = ("neko", "maboss", "physicell") + (("biomass",) if with_biomass else ())
    for server in servers:
        print(f"Checking {server} MCP startup and tool inventory…", file=sys.stderr, flush=True)
        try:
            with tempfile.TemporaryDirectory(prefix="biomodelling-probe-") as temporary:
                result = run([str(prefix/"bin/python"), str(root/"scripts/setup_support/probe_mcp.py"),
                              str(prefix/"bin"/f"mcp-{server}-server")],
                             cwd=Path(temporary), env={**runtime_env(prefix, graphviz_path=graphviz_path),
                                 "NUMBA_CACHE_DIR": str(Path(temporary)/"numba-cache")}, timeout=90)
            data = json.loads(result.stdout)
            names = data.get("tools") if isinstance(data, dict) else None
            if (not isinstance(names, list) or not names
                    or any(not isinstance(name, str) or not name for name in names)
                    or len(names) != len(set(names))):
                raise SetupError(f"{server}: invalid tools/list inventory")
            tools = set(names)
            required = SIGNATURES[server]
            if with_biomass and server == "neko":
                required = required | {"export_biomass_handoff"}
            if required - tools:
                raise SetupError(f"{server}: missing required tools: {', '.join(sorted(required - tools))}")
            prohibited = {v for k, v in UNIQUE_TOOLS.items() if k != server}
            # Simulation is shared by the Boolean and ODE servers only.
            if server not in {"maboss", "biomass"}:
                prohibited.add("run_simulation")
            if prohibited & tools:
                raise SetupError(f"{server}: cross-domain modelling tools are exposed")
            inventories[server] = {"passed": True, "tool_count": len(tools),
                                   "required_capabilities": sorted(required)}
        except (SetupError, ValueError, KeyError, TypeError) as error:
            errors.append(str(error))
            inventories[server] = {"passed": False}
    return {"passed": not errors, "errors": errors, "mcp": inventories}


def verify(root: Path, prefix: Path, clients: dict, *, with_biomass: bool = False,
           capability_report: dict | None = None, graphviz_path: str | None = None) -> dict:
    # Setup may already have checked capabilities before writing configuration.
    # Independent callers still perform their own complete startup check.
    probes = capability_report if capability_report is not None else probe_servers(prefix, with_biomass=with_biomass, graphviz_path=graphviz_path)
    errors = list(probes["errors"])
    specialist_results = {}
    parent = None
    literature = None
    if "codex" in clients:
        roles = check_environment.MODEL_SPECIALISTS + (("ode_modeler",) if with_biomass else ())
        for role in roles:
            result = check_environment.specialist_inventory(clients["codex"], role, root)
            specialist_results[role] = result
            if not result["passed"]:
                errors.append(f"{role}: {result.get('error', 'unsafe inventory')}")
        literature = check_environment.literature_inventory(clients["codex"], root)
        literature = {**literature, "degraded": not bool(literature.get("pubmed"))}
        if not literature["passed"]:
            errors.append(f"literature_reviewer: {literature.get('error', 'unsafe inventory')}")
        parent = check_environment.orchestrator_inventory(clients["codex"], root)
        if not parent["passed"]:
            errors.append("Codex parent configuration has enabled modelling MCPs")
    if "claude" in clients:
        try:
            run([clients["claude"], "mcp", "list"], cwd=root, timeout=60)
        except SetupError as error:
            errors.append(str(error))
    return {"passed": not errors, "errors": errors, "mcp": probes["mcp"],
            "specialists": specialist_results, "orchestrator_isolation": parent,
            "literature_isolation": literature,
            "authentication": "not_verified", "scientific_readiness": "not_verified",
            "limitations": ["Restart the selected client after configuration changes.",
                            "Desktop parent tool isolation requires external enforcement.",
                            "Literature requires configured PubMed or explicitly authorized Codex web search.",
                            "Claude inline isolation requires a client-level inspection; CLI server listing alone cannot prove it.",
                            "Claude independent reviewers require client-level execution verification."]}
