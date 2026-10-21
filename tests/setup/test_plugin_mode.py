"""Plugin mode: the marketplace plugin's uvx launch, inline per specialist only."""
from __future__ import annotations

import json
import shutil
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from scripts import check_isolation, setup
from scripts.setup_support import configure_codex, detect, environment
from scripts.setup_support.state import SetupError

ROOT = Path(__file__).resolve().parents[2]
UVX = "/tools/uv bin/uvx"


class PluginModeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "project"
        self.root.mkdir()
        for name in ("setup", ".codex", ".codex-plugin", ".claude/agents", ".claude/skills"):
            shutil.copytree(ROOT / name, self.root / name)
        self.home = Path(temporary.name) / "codex home"
        self.manifest = tomllib.loads((self.root / "setup/dependencies.toml").read_text())
        self.requirement = f'{self.manifest["package"]}=={self.manifest["version"]}'

    def discover(self, name, override=None):
        if name == "uvx":
            return override or UVX
        return None if name == "dot" else override or "/tools/executable"

    def execute(self, flags, **patches):
        args = setup.parser().parse_args(flags)
        with mock.patch.object(detect, "discover", side_effect=self.discover), \
             mock.patch.object(detect, "client_version", return_value="2.0.0"), \
             mock.patch.object(environment, "install") as install, \
             mock.patch.object(environment, "verify_environment") as managed, \
             mock.patch.object(environment, "verify_plugin", return_value=patches.get(
                 "plugin_report", {"passed": True, "errors": [], "warnings": []})) as plugin, \
             mock.patch.object(setup.verify, "verify", return_value={"passed": True, "errors": []}) as check:
            report = setup.execute(args, self.root)
        return report, install, managed, plugin, check

    def test_plugin_mode_writes_the_plugin_launch_without_an_environment(self):
        report, install, managed, plugin, check = self.execute(["--client", "claude", "--environment-mode", "plugin"])
        self.assertTrue(report["passed"], report["errors"])
        install.assert_not_called()
        managed.assert_not_called()
        plugin.assert_called_once()
        self.assertEqual(check.call_args.kwargs["plugin"], {"uvx": UVX, "manifest": self.manifest})
        self.assertIsNone(report["plan"]["env_prefix"])
        text = (self.root / ".claude/agents/network-curator.md").read_text()
        self.assertIn("      command: " + json.dumps(UVX) + "\n", text)
        self.assertIn("      args: " + json.dumps(["--from", self.requirement, "mcp-neko-server"]) + "\n", text)
        self.assertNotIn("CONDA_PREFIX", text.split("\ntools:", 1)[0])
        saved = json.loads((self.root / ".setup/local.json").read_text())
        self.assertEqual((saved["environment_mode"], saved["uv_path"]), ("plugin", UVX))
        self.assertNotIn("env_prefix", saved)
        self.assertEqual(check_isolation.check(self.root)["errors"], [])

    def test_codex_profiles_use_the_same_launch(self):
        outputs = configure_codex.render(self.root, None, self.home, plugin={"uvx": UVX, "manifest": self.manifest})
        profiles = [tomllib.loads(text) for text in outputs.values()]
        launches = [(name, server) for payload in profiles for name, server in payload["mcp_servers"].items()
                    if server.get("enabled") and name != "pubmed"]
        self.assertEqual(sorted(name for name, _ in launches), ["maboss", "neko", "physicell"])
        for name, server in launches:
            self.assertEqual((server["command"], server["args"]), (UVX, ["--from", self.requirement, f"mcp-{name}-server"]))
            self.assertNotIn("CONDA_PREFIX", server["env"])
            self.assertEqual(server["env"]["PATH"].split(":")[0], str(Path(UVX).parent))

    def test_missing_uvx_and_environment_options_are_errors(self):
        args = setup.parser().parse_args(["--client", "claude", "--environment-mode", "plugin", "--non-interactive"])
        with mock.patch.object(detect, "discover", side_effect=lambda name, override=None:
                               None if name == "uvx" else "/tools/executable"), \
             mock.patch.object(detect, "client_version", return_value="2.0.0"):
            _, errors = setup.plan(args, self.root, self.manifest)
        self.assertTrue(any("uvx is missing" in error for error in errors))
        for flags in (["--env-prefix", "/elsewhere"], ["--manager", "venv"], ["--package-source", "/src"]):
            with self.subTest(flags=flags), self.assertRaisesRegex(SetupError, "plugin mode"):
                setup.settings(setup.parser().parse_args(["--environment-mode", "plugin", *flags]), self.root)
        with self.assertRaisesRegex(SetupError, "--uv-path applies only"):
            setup.settings(setup.parser().parse_args(["--uv-path", UVX]), self.root)

    def test_saved_choices_from_another_mode_do_not_carry_over(self):
        (self.root / ".setup").mkdir()
        (self.root / ".setup/local.json").write_text(json.dumps(
            {"client": "claude", "manager": "venv", "env_prefix": "/old/environment"}))
        values = setup.settings(setup.parser().parse_args(["--environment-mode", "plugin"]), self.root)
        self.assertEqual(values, {"client": "claude", "environment_mode": "plugin"})
        (self.root / ".setup/local.json").write_text(json.dumps(
            {"client": "claude", "environment_mode": "plugin", "uv_path": UVX}))
        values = setup.settings(setup.parser().parse_args(["--environment-mode", "managed"]), self.root)
        self.assertEqual(values, {"client": "claude", "environment_mode": "managed"})

    def test_failed_plugin_resolution_writes_no_configuration(self):
        before = (self.root / ".claude/agents/network-curator.md").read_bytes()
        failed = {"passed": False, "errors": ["Expected mcp-biomodelling-servers 2.5.0, found 2.4.0"], "warnings": []}
        report, *_ = self.execute(["--client", "claude", "--environment-mode", "plugin"], plugin_report=failed)
        self.assertFalse(report["passed"])
        self.assertEqual((self.root / ".claude/agents/network-curator.md").read_bytes(), before)

    def test_plugin_verification_reports_dependency_drift_without_failing(self):
        resolved = {"version": self.manifest["version"], "python": [3, 13, 0], "dependencies": {"nekomata": "1.10.9"}}
        with mock.patch.object(environment, "run", return_value=mock.Mock(stdout=json.dumps(resolved))) as run:
            report = environment.verify_plugin(UVX, self.manifest)
        self.assertTrue(report["passed"])
        self.assertIn("nekomata 1.10.9", report["warnings"][0])
        argv = run.call_args.args[0]
        self.assertEqual(argv[:4], [UVX, "--from", self.requirement, "python"])
        resolved["version"] = "2.4.0"
        with mock.patch.object(environment, "run", return_value=mock.Mock(stdout=json.dumps(resolved))):
            self.assertFalse(environment.verify_plugin(UVX, self.manifest)["passed"])

    def test_isolation_guard_rejects_enabled_modelling_plugins_at_every_scope(self):
        user = self.root.parent / "user-settings.json"
        shutil.copy(ROOT / ".claude/settings.json", self.root / ".claude/settings.json")
        cases = {
            self.root / ".claude/settings.json": {"enabledPlugins": {"neko@marcorusc": True, "other@marcorusc": True}},
            self.root / ".claude/settings.local.json": {"enabledPlugins": {"maboss@elsewhere": True, "physicell@marcorusc": False}},
            user: {"enabledPlugins": {"biomass@marcorusc": True}},
        }
        original = (self.root / ".claude/settings.json").read_text()
        for path, data in cases.items():
            existing = json.loads(path.read_text()) if path.exists() else {}
            path.write_text(json.dumps({**existing, **data}))
        errors = check_isolation.check(self.root, user_settings=user)["errors"]
        flagged = sorted(error.split("enabled modelling plugin ", 1)[1].split(" ", 1)[0]
                         for error in errors if "enabled modelling plugin" in error)
        self.assertEqual(flagged, ["biomass@marcorusc", "maboss@elsewhere", "neko@marcorusc"])
        self.assertEqual(check_isolation.check(self.root)["passed"], False)
        (self.root / ".claude/settings.json").write_text(original)
        (self.root / ".claude/settings.local.json").write_text(json.dumps(
            {"permissions": {"allow": ["mcp__plugin_neko_neko__create_network"]}}))
        errors = check_isolation.check(self.root)["errors"]
        self.assertTrue(any("project-wide modelling allow rule" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
