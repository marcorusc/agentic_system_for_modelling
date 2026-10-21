#!/usr/bin/env python3
"""Regression tests for isolated specialist MCP and workflow-skill access."""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

AGENTS = {
    "ode-modeler.md": ("biomass", "mcp-biomass-server", "biomass-workflow"),
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
    def check_transport(self, metadata: str, server: str, executable: str) -> None:
        self.assertIn(f"mcpServers:\n  - {server}-agent:\n", metadata)
        block = metadata.split("mcpServers:\n", 1)[1].split("\ntools:", 1)[0]
        self.assertEqual(re.findall(r"^  - ([\w-]+):$", block, re.MULTILINE), [server + "-agent"])
        def value(key: str):
            matches = re.findall(rf"^ +{key}: (.+)$", block, re.MULTILINE)
            self.assertLessEqual(len(matches), 1)
            return json.loads(matches[0]) if matches else None
        command = value("command")
        arguments = value("args")
        if arguments is not None:
            # Marketplace plugin launch, pinned to the tested release; tracked
            # defaults use a bare uvx and setup writes an absolute one.
            manifest = tomllib.loads((ROOT / "setup/dependencies.toml").read_text())
            self.assertEqual(Path(command).name, "uvx")
            self.assertEqual(arguments, ["--from", f"{manifest['package']}=={manifest['version']}", executable])
            self.assertIsNone(value("CONDA_PREFIX"))
            if Path(command).is_absolute():
                self.assertEqual(value("PATH").split(":")[0], str(Path(command).parent))
        else:
            prefix = Path(value("CONDA_PREFIX"))
            self.assertTrue(prefix.is_absolute())
            self.assertEqual(command, str(prefix / "bin" / executable))
            self.assertEqual(value("PATH").split(":")[0], str(prefix / "bin"))
        self.assertNotIn("${MCP_MODELLING_ENV}", metadata)

    def test_agents_define_isolated_inline_servers(self) -> None:
        for filename, (server, executable, _) in AGENTS.items():
            with self.subTest(agent=filename):
                self.check_transport(frontmatter(agent_text(filename)), server, executable)

    def test_generated_transports_support_other_environment_paths(self) -> None:
        from scripts.setup_support import configure_claude
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copytree(ROOT / ".claude/agents", root / ".claude/agents")
            rendered = configure_claude.render(root, root / "another environment", with_biomass=True)
            for filename, (server, executable, _) in AGENTS.items():
                self.check_transport(frontmatter(rendered[root / ".claude/agents" / filename]), server, executable)

    def test_generated_plugin_transports_pin_the_released_launch(self) -> None:
        import tomllib as toml
        from scripts.setup_support import configure_claude
        manifest = toml.loads((ROOT / "setup/dependencies.toml").read_text())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copytree(ROOT / ".claude/agents", root / ".claude/agents")
            plugin = {"uvx": "/opt/uv tools/bin/uvx", "manifest": manifest}
            rendered = configure_claude.render(root, None, with_biomass=True, plugin=plugin)
            for filename, (server, executable, _) in AGENTS.items():
                self.check_transport(frontmatter(rendered[root / ".claude/agents" / filename]), server, executable)
            hook = rendered[root / ".claude/agents/literature-reviewer.md"]
            self.assertIn('          command: "python3"\n', hook)
            for path, text in rendered.items():
                path.write_text(text)
            self.assertEqual(configure_claude.render(root, None, with_biomass=True, plugin=plugin), rendered)

    def test_required_validation_reviewers_exist_and_are_read_only(self) -> None:
        workflow = (ROOT / ".claude/skills/validate-stage/SKILL.md").read_text()
        for role in ("scientific-reviewer", "reproducibility-auditor"):
            self.assertIn(f"`{role}`", workflow)
            text = agent_text(role + ".md")
            metadata = frontmatter(text)
            allowed = metadata.split("\ntools:\n", 1)[1].split("\ndisallowedTools:", 1)[0]
            self.assertEqual(allowed.splitlines(), ["  - Read", "  - Grep", "  - Glob"])
            self.assertIn("  - 'mcp__*'", metadata)
            self.assertNotIn("mcpServers:", metadata)
            self.assertIn("does\nnot authorize a stage transition", text)

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
                self.assertIn(f"  - 'mcp__{server}-agent__*'\n", metadata)

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
