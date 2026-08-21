#!/usr/bin/env python3
"""Regression tests for isolated specialist MCP and workflow-skill access."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODELLING_ENV = Path("/home/marcorusc/miniforge3/envs/mcp_modelling")

AGENTS = {
    "network-curator.md": ("neko", "mcp-neko-server", "neko-workflow"),
    "boolean-dynamics-modeler.md": (
        "maboss",
        "mcp-maboss-server",
        "maboss-workflow",
    ),
    "multicellular-configurator.md": (
        "physicell",
        "mcp-physicell-server",
        "physicell-workflow",
    ),
}

RESOURCE_BRIDGE_NAMES = {
    "ListMcpResources",
    "ReadMcpResource",
    "ListMcpResourcesTool",
    "ReadMcpResourceTool",
}


def agent_text(filename: str) -> str:
    return (ROOT / ".claude" / "agents" / filename).read_text(encoding="utf-8")


def frontmatter(text: str) -> str:
    marker = "---\n"
    if not text.startswith(marker):
        raise AssertionError("agent definition has no opening frontmatter marker")
    parts = text[len(marker) :].split("\n---\n", 1)
    if len(parts) != 2:
        raise AssertionError("agent definition has no closing frontmatter marker")
    return parts[0]


class SpecialistMcpAccessTests(unittest.TestCase):
    def test_agents_define_isolated_inline_servers(self) -> None:
        for filename, (server, executable, _) in AGENTS.items():
            with self.subTest(agent=filename):
                metadata = frontmatter(agent_text(filename))
                command = MODELLING_ENV / "bin" / executable
                self.assertIn(f"mcpServers:\n  - {server}:\n", metadata)
                self.assertIn(f"      command: {command}\n", metadata)
                self.assertIn(f"        CONDA_PREFIX: {MODELLING_ENV}\n", metadata)
                self.assertNotIn(f"mcpServers:\n  - {server}\n", metadata)
                self.assertNotIn("${MCP_MODELLING_ENV}", metadata)
                self.assertTrue(command.is_file(), f"missing executable: {command}")

    def test_agents_preload_matching_workflow_skills(self) -> None:
        for filename, (_, _, skill) in AGENTS.items():
            with self.subTest(agent=filename):
                metadata = frontmatter(agent_text(filename))
                skill_path = ROOT / ".claude" / "skills" / skill / "SKILL.md"
                self.assertIn(f"skills:\n  - {skill}\n", metadata)
                self.assertTrue(skill_path.is_file(), f"missing skill: {skill_path}")
                self.assertIn(
                    f"name: {skill}\n", skill_path.read_text(encoding="utf-8")
                )

    def test_agents_keep_tool_search_and_server_tools(self) -> None:
        for filename, (server, _, _) in AGENTS.items():
            with self.subTest(agent=filename):
                metadata = frontmatter(agent_text(filename))
                self.assertIn("  - ToolSearch\n", metadata)
                self.assertIn(f"  - 'mcp__{server}__*'\n", metadata)

    def test_resource_bridge_dependency_is_removed(self) -> None:
        paths = [
            ROOT / "CLAUDE.md",
            ROOT / "README.md",
            ROOT / "docs" / "agentic-biomodelling-architecture.md",
        ]
        paths.extend(ROOT / ".claude" / "agents" / filename for filename in AGENTS)
        paths.extend(
            ROOT / ".claude" / "skills" / skill / "SKILL.md"
            for _, _, skill in AGENTS.values()
        )

        for path in paths:
            with self.subTest(path=path):
                text = path.read_text(encoding="utf-8")
                for name in RESOURCE_BRIDGE_NAMES:
                    self.assertNotIn(name, text)
                self.assertNotIn("docs://neko/agent_manual", text)
                self.assertNotIn("docs://maboss/agent_manual", text)
                self.assertNotIn("docs://physicell/agent_manual", text)


if __name__ == "__main__":
    unittest.main()
