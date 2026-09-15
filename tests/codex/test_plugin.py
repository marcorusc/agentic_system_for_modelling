from __future__ import annotations

import json
import re
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_SKILLS = {
    "biomass-workflow",
    "biomodelling-orchestrator",
    "checkpoint-model",
    "maboss-workflow",
    "model-archive",
    "model-list",
    "model-restart",
    "model-restore",
    "neko-workflow",
    "physicell-workflow",
    "review-literature-evidence",
    "validate-stage",
}
SPECIALIST_SKILLS = {
    "neko-workflow",
    "maboss-workflow",
    "physicell-workflow",
    "review-literature-evidence",
}


def read_frontmatter(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
    if match is None:
        raise AssertionError(f"missing YAML frontmatter: {path}")
    payload: dict[str, object] = {}
    for line in match.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith((" ", "\t")) or ":" not in line:
            raise AssertionError(f"unsupported skill frontmatter line: {path}: {line}")
        key, value = line.split(":", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        payload[key.strip()] = value
    return payload


class PluginTests(unittest.TestCase):
    def test_manifest_is_discoverable_and_contains_skills_only(self) -> None:
        manifest = json.loads(
            (ROOT / ".codex-plugin/plugin.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["name"], "agentic-system-for-modelling")
        self.assertEqual(manifest["skills"], "./skills/")
        self.assertNotIn("mcpServers", manifest)
        self.assertNotIn("apps", manifest)
        self.assertNotIn("hooks", manifest)

    def test_all_expected_skills_are_discoverable(self) -> None:
        discovered = {
            path.parent.name for path in (ROOT / "skills").glob("*/SKILL.md")
        }
        self.assertEqual(discovered, EXPECTED_SKILLS)
        for name in discovered:
            frontmatter = read_frontmatter(ROOT / "skills" / name / "SKILL.md")
            self.assertEqual(frontmatter.get("name"), name)
            self.assertIsInstance(frontmatter.get("description"), str)
            self.assertTrue(str(frontmatter["description"]).strip())

    def test_specialist_skills_route_only_through_launcher(self) -> None:
        entrypoint = "scripts/codex/run_specialist.py"
        for name in SPECIALIST_SKILLS:
            text = (ROOT / "skills" / name / "SKILL.md").read_text(
                encoding="utf-8"
            )
            self.assertIn(entrypoint, text)
            self.assertNotIn("mcp__", text)
            self.assertNotIn("spawn_agent", text)

    def test_orchestrator_project_config_disables_modelling_servers(self) -> None:
        config = tomllib.loads((ROOT / ".codex/config.toml").read_text())
        servers = config["mcp_servers"]
        for name in ("neko", "maboss", "physicell"):
            self.assertFalse(servers[name]["enabled"])
            self.assertTrue(servers[name]["command"].startswith("__orchestrator_disabled_"))

    def test_same_process_agents_are_compatibility_only(self) -> None:
        active = list((ROOT / ".codex/agents").glob("*.toml"))
        self.assertEqual(active, [])
        examples = list((ROOT / ".codex/agents").glob("*.toml.example"))
        self.assertEqual(len(examples), 5)
        for path in examples:
            self.assertIn(
                "INACTIVE COMPATIBILITY EXAMPLE",
                path.read_text(encoding="utf-8"),
            )

    def test_tracked_phase3_files_have_no_personal_machine_values(self) -> None:
        paths = [ROOT / ".codex-plugin", ROOT / "skills", ROOT / "scripts/codex"]
        files = [
            path
            for root in paths
            for path in root.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        ]
        forbidden = ("/home/", "CONDA_PREFIX", "miniforge", "Ubuntu-", "api_key")
        for path in files:
            text = path.read_text(encoding="utf-8")
            for value in forbidden:
                self.assertNotIn(value, text, f"{value!r} found in {path}")


if __name__ == "__main__":
    unittest.main()
