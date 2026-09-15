from __future__ import annotations

import json
import re
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CODEX_TREES = (
    ROOT / ".agents",
    ROOT / ".codex",
    ROOT / ".codex-plugin",
    ROOT / "skills",
    ROOT / "scripts/codex",
)


def source_files():
    for tree in CODEX_TREES:
        for path in tree.rglob("*"):
            ignored_local = (
                path == ROOT / ".codex/launcher.local.json"
                or (path.parent == ROOT / ".codex/agents" and path.suffix == ".toml")
            )
            if (
                path.is_file()
                and "__pycache__" not in path.parts
                and not ignored_local
            ):
                yield path


class StaticConfigurationTests(unittest.TestCase):
    def test_every_compatibility_agent_is_valid_toml(self) -> None:
        agents = sorted((ROOT / ".codex/agents").glob("*.toml.example"))
        self.assertEqual(len(agents), 5)
        for path in agents:
            with self.subTest(path=path.name):
                payload = tomllib.loads(path.read_text(encoding="utf-8"))
                self.assertIsInstance(payload.get("name"), str)
                self.assertIsInstance(payload.get("description"), str)
                self.assertIsInstance(payload.get("developer_instructions"), str)

    def test_marketplace_and_plugin_manifests_are_local_and_valid(self) -> None:
        marketplace = json.loads(
            (ROOT / ".agents/plugins/marketplace.json").read_text(encoding="utf-8")
        )
        manifest = json.loads(
            (ROOT / ".codex-plugin/plugin.json").read_text(encoding="utf-8")
        )
        entry = marketplace["plugins"][0]
        self.assertEqual(entry["name"], manifest["name"])
        self.assertEqual(entry["source"], {"source": "local", "path": "./"})
        self.assertNotIn("mcpServers", manifest)
        self.assertNotIn("hooks", manifest)

    def test_codex_sources_have_no_claude_interpolation_or_personal_paths(self) -> None:
        personal_path = re.compile(r"(?:/home/|[A-Za-z]:\\Users\\)[^<\s`]+")
        for path in source_files():
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertNotIn("${CLAUDE_PROJECT_DIR}", text)
                self.assertIsNone(personal_path.search(text))
                if path.suffix in {".toml", ".json"} or path.name.endswith(".toml.example"):
                    self.assertNotIn("PreToolUse", text)

    def test_no_local_launcher_configuration_is_committed_as_source(self) -> None:
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".codex/launcher.local.json", ignore)
        self.assertIn(".codex/agents/*.toml", ignore)
        self.assertIn(".codex-tasks/", ignore)
        self.assertIn(".codex-task-*.txt", ignore)
        example = json.loads(
            (ROOT / ".codex/launcher.example.json").read_text(encoding="utf-8")
        )
        self.assertIn("SET_IN_IGNORED_LOCAL_CONFIG", example["distribution"])
        self.assertNotIn("token", json.dumps(example).lower())


class GovernanceConfigurationTests(unittest.TestCase):
    def test_orchestrator_owns_transitions_and_shared_state(self) -> None:
        policy = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        skill = (ROOT / "skills/biomodelling-orchestrator/SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("only writer of shared sources of truth", policy)
        self.assertIn("controls every stage transition", policy)
        self.assertIn("Request researcher approval at every gate", skill)

    def test_parameter_invention_and_conclusive_handoffs_require_approval(self) -> None:
        policy = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("Never invent a biological or numerical parameter", policy)
        self.assertRegex(
            policy,
            r"explicitly\s+approved by the researcher before use",
        )
        self.assertIn("producing the conclusive BNET/NeKo-to-MaBoSS handoff", policy)
        self.assertIn("producing the conclusive MaBoSS-to-PhysiCell handoff", policy)

    def test_lifecycle_mutations_require_explicit_intent_and_fresh_confirmation(self) -> None:
        restart = (ROOT / "skills/model-restart/SKILL.md").read_text(encoding="utf-8")
        restore = (ROOT / "skills/model-restore/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("only when the user explicitly requests a restart", restart)
        self.assertIn("Stop for a new explicit confirmation", restart)
        self.assertIn("only when the user explicitly requests restoration", restore)
        self.assertIn("Stop for a new explicit confirmation", restore)

    def test_fresh_sessions_and_durable_reconstruction_are_required(self) -> None:
        policy = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("Create a fresh specialist session", policy)
        self.assertIn("resolve the relevant active session from its registry rather than chat context", policy)
        self.assertIn("reconstruct runtime state from approved handoffs", policy)

    def test_checkpoint_cleans_only_verified_task_prompts(self) -> None:
        skill = (ROOT / "skills/checkpoint-model/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("scripts/codex/cleanup_tasks.py", skill)
        self.assertIn("Preserve and report every `unmatched` prompt", skill)


if __name__ == "__main__":
    unittest.main()
