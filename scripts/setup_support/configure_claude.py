"""Update only the supported inline YAML transport shape; retain agent policies."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .state import SetupError


ROLES = {"network-curator": "neko", "boolean-dynamics-modeler": "maboss",
         "multicellular-configurator": "physicell"}


def render(root: Path, prefix: Path) -> dict[Path, str]:
    outputs = {}
    for role, server in ROLES.items():
        path = root/".claude/agents"/f"{role}.md"
        text = path.read_text(encoding="utf-8")
        parts = text.split("---\n", 2)
        if len(parts) != 3 or parts[0]:
            raise SetupError(f"Unsupported agent frontmatter: {path.name}")
        header = parts[1]
        start = f"mcpServers:\n  - {server}:\n"
        if header.count(start) != 1:
            raise SetupError(f"Unsupported MCP transport shape: {path.name}")
        begin = header.index(start) + len(start)
        end_match = re.search(r"^\S", header[begin:], re.MULTILINE)
        end = begin + end_match.start() if end_match else len(header)
        block = header[begin:end]
        if re.search(r"^  - ", block, re.MULTILINE):
            raise SetupError(f"Unexpected additional inline MCP server in {path.name}")
        values = {
            "command": str(prefix/"bin"/f"mcp-{server}-server"),
            "CONDA_PREFIX": str(prefix),
            "PATH": str(prefix/"bin") + os.pathsep + os.environ.get("PATH", ""),
        }
        for key, value in values.items():
            indent = "      " if key == "command" else "        "
            pattern = rf"^{indent}{key}: .+$"
            if len(re.findall(pattern, block, re.MULTILINE)) != 1:
                raise SetupError(f"Unsupported {key} field in {path.name}; restore the standard transport layout")
            block = re.sub(pattern, lambda _: indent + key + ": " + json.dumps(value), block, flags=re.MULTILINE)
        outputs[path] = "---\n" + header[:begin] + block + header[end:] + "---\n" + parts[2]
    hook = root/".claude/agents/literature-reviewer.md"
    text = hook.read_text(encoding="utf-8")
    pattern = r"^(          command: ).+$"
    if len(re.findall(pattern, text, re.MULTILINE)) != 1:
        raise SetupError("Unsupported literature hook command; expected one Python hook")
    outputs[hook] = re.sub(pattern, lambda m: m[1] + json.dumps(str(prefix/"bin/python")), text, flags=re.MULTILINE)
    return outputs
