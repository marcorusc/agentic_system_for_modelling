"""Update only the supported inline YAML transport shape; retain agent policies."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .state import SetupError
from .environment import server_transport


ROLES = {"network-curator": "neko", "boolean-dynamics-modeler": "maboss",
         "multicellular-configurator": "physicell"}


def render(root: Path, prefix: Path | None, *, with_biomass: bool = False,
           graphviz_path: str | None = None, plugin: dict | None = None) -> dict[Path, str]:
    """Render isolated inline transports: a managed/reused environment, or the
    marketplace plugin launch (``plugin={"uvx": path, "manifest": manifest}``)."""
    outputs = {}
    roles = {**ROLES, **({"ode-modeler": "biomass"} if with_biomass else {})}
    for role, server in roles.items():
        path = root/".claude/agents"/f"{role}.md"
        text = path.read_text(encoding="utf-8")
        parts = text.split("---\n", 2)
        if len(parts) != 3 or parts[0]:
            raise SetupError(f"Unsupported agent frontmatter: {path.name}")
        header = parts[1]
        start = f"mcpServers:\n  - {server}-agent:\n"
        if header.count(start) != 1:
            raise SetupError(f"Unsupported MCP transport shape: {path.name}")
        begin = header.index(start) + len(start)
        end_match = re.search(r"^\S", header[begin:], re.MULTILINE)
        end = begin + end_match.start() if end_match else len(header)
        block = header[begin:end]
        if re.search(r"^  - ", block, re.MULTILINE):
            raise SetupError(f"Unexpected additional inline MCP server in {path.name}")
        if not re.fullmatch(r"(?:      \S.*\n|        \S.*\n)+", block) or block.count("      command: ") != 1:
            raise SetupError(f"Unsupported command field in {path.name}; restore the standard transport layout")
        command, args, env = server_transport(server, prefix=prefix, plugin=plugin, graphviz_path=graphviz_path)
        if server == "biomass":
            env.update({"NUMBA_CACHE_DIR": str(root/".setup/cache/biomass-numba"), "PYTHONDONTWRITEBYTECODE": "1"})
        block = "      type: stdio\n" + "      command: " + json.dumps(command) + "\n"
        if args:
            block += "      args: " + json.dumps(args) + "\n"
        block += "      env:\n" + "".join(f"        {key}: {json.dumps(value)}\n" for key, value in env.items())
        outputs[path] = "---\n" + header[:begin] + block + header[end:] + "---\n" + parts[2]
    hook = root/".claude/agents/literature-reviewer.md"
    text = hook.read_text(encoding="utf-8")
    pattern = r"^(          command: ).+$"
    if len(re.findall(pattern, text, re.MULTILINE)) != 1:
        raise SetupError("Unsupported literature hook command; expected one Python hook")
    # The guard is standard-library only; plugin mode keeps the portable interpreter.
    interpreter = "python3" if plugin else str(prefix/"bin/python")
    outputs[hook] = re.sub(pattern, lambda m: m[1] + json.dumps(interpreter), text, flags=re.MULTILINE)
    return outputs
