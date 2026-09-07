"""Read-only process diagnostics, with explicit readiness limits."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from scripts.codex import check_environment
from .detect import run
from .environment import runtime_env
from .state import SetupError


def verify(root: Path, prefix: Path, clients: dict) -> dict:
    errors = []
    inventories = {}
    for server, expected in (("neko", "create_network"), ("maboss", "run_simulation"),
                             ("physicell", "export_xml_configuration")):
        try:
            with tempfile.TemporaryDirectory(prefix="biomodelling-probe-") as temporary:
                result = run([str(prefix/"bin/python"), str(root/"scripts/setup_support/probe_mcp.py"),
                              str(prefix/"bin"/f"mcp-{server}-server")],
                             cwd=Path(temporary), env=runtime_env(prefix), timeout=90)
            data = json.loads(result.stdout)
            prohibited = {"create_network", "run_simulation", "export_xml_configuration"} - {expected}
            if prohibited.intersection(data["tools"]):
                raise SetupError(f"{server}: cross-domain modelling tools are exposed")
            if expected not in data["tools"]:
                raise SetupError(f"{server}: missing required tool {expected}")
            inventories[server] = {"passed": True, "tool_count": len(data["tools"])}
        except (SetupError, ValueError, KeyError) as error:
            errors.append(str(error))
            inventories[server] = {"passed": False}
    if "codex" in clients:
        for role in check_environment.MODEL_SPECIALISTS:
            result = check_environment.specialist_inventory(clients["codex"], role, root)
            if not result["passed"]:
                errors.append(f"{role}: {result.get('error', 'unsafe inventory')}")
        parent = check_environment.orchestrator_inventory(clients["codex"], root)
        if not parent["passed"]:
            errors.append("Codex parent configuration has enabled modelling MCPs")
    if "claude" in clients:
        try:
            run([clients["claude"], "mcp", "list"], cwd=root, timeout=60)
        except SetupError as error:
            errors.append(str(error))
    return {"passed": not errors, "errors": errors, "mcp": inventories,
            "authentication": "not_verified", "scientific_readiness": "not_verified",
            "limitations": ["Restart the selected client after configuration changes.",
                            "Desktop parent tool isolation requires external enforcement.",
                            "Literature requires configured PubMed or explicitly authorized Codex web search.",
                            "Claude inline isolation requires a client-level inspection; CLI server listing alone cannot prove it."]}
