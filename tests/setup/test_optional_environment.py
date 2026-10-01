"""Optional ODE setup boundaries; subprocesses and inventories are fixtures."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import tomllib
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

from scripts import setup
from scripts.setup_support import configure_codex, detect, environment, verify
from scripts.setup_support.state import SetupError


ROOT = Path(__file__).resolve().parents[2]


class OptionalEnvironmentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.root = self.directory / "project"
        self.root.mkdir()
        for name in ("setup", ".codex", ".codex-plugin", ".claude/agents"):
            shutil.copytree(ROOT / name, self.root / name)
        self.prefix = self.directory / "existing environment"
        self.prefix.mkdir()
        (self.prefix / "untouched.txt").write_text("original")
        self.home = self.directory / "codex"
        self.manifest = tomllib.loads((self.root / "setup/dependencies.toml").read_text())

    def test_reuse_plan_needs_no_environment_manager_or_global_graphviz(self):
        args = setup.parser().parse_args([
            "--client", "claude", "--environment-mode", "reuse",
            "--env-prefix", str(self.prefix), "--dry-run", "--with-biomass",
        ])
        def discover(name, override=None):
            self.assertIn(name, {"git", "claude", "dot"})
            return None if name == "dot" else "/fixture/" + name
        with mock.patch.object(detect, "discover", side_effect=discover), \
             mock.patch.object(detect, "client_version", return_value="2.0.0"):
            report = setup.execute(args, self.root)
        self.assertTrue(report["passed"])
        self.assertIsNone(report["plan"]["manager_path"])
        self.assertEqual(report["plan"]["environment_mode"], "reuse")
        self.assertFalse((self.root / ".setup").exists())
        self.assertEqual(list(self.prefix.iterdir()), [self.prefix / "untouched.txt"])

    def test_reuse_rejects_install_sources_and_invalid_settings(self):
        args = setup.parser().parse_args([
            "--environment-mode", "reuse", "--package-source", "/fixture/source",
        ])
        with self.assertRaisesRegex(SetupError, "reuse mode cannot install"):
            setup.settings(args, self.root)
        for changes in ({"environment_mode": "unknown"}, {"biomass": True}, {"biomass": "unknown"}):
            config_file = self.directory / "input.json"
            config_file.write_text(json.dumps(changes))
            args = setup.parser().parse_args(["--config", str(config_file)])
            with self.subTest(changes=changes), self.assertRaises(SetupError):
                setup.settings(args, self.root)

    def test_default_dependency_requirements_stay_unchanged_and_ode_is_explicit(self):
        baseline = json.loads(json.dumps(self.manifest))
        for enabled in (False, True):
            args = setup.parser().parse_args([
                "--client", "claude", "--environment-mode", "reuse", "--env-prefix", str(self.prefix),
                *(["--with-biomass"] if enabled else []),
            ])
            # Separate runs must not inherit a saved optional selection.
            with ExitStack() as stack:
                stack.enter_context(mock.patch.object(detect, "discover", return_value="/fixture/tool"))
                stack.enter_context(mock.patch.object(detect, "client_version", return_value="2.0.0"))
                stack.enter_context(mock.patch.object(environment, "install"))
                inspect = stack.enter_context(mock.patch.object(environment, "verify_environment",
                    return_value={"passed": False, "errors": ["fixture stop before writes"]}))
                probe = stack.enter_context(mock.patch.object(verify, "probe_servers"))
                report = setup.execute(args, self.root)
            self.assertFalse(report["passed"])
            probe.assert_not_called()
            manifest = inspect.call_args.args[1]
            self.assertEqual(manifest["version"], baseline["version"])
            self.assertEqual("mcp-biomass-server" in manifest["executables"], enabled)
            self.assertEqual("biomass" in manifest["imports"], enabled)
            if not enabled:
                self.assertEqual(manifest, baseline)
        self.assertEqual(tomllib.loads((self.root / "setup/dependencies.toml").read_text()), baseline)

    def test_saved_reuse_selection_remains_read_only_on_next_run(self):
        args = setup.parser().parse_args([
            "--client", "claude", "--environment-mode", "reuse", "--env-prefix", str(self.prefix),
            "--with-biomass",
        ])
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(detect, "discover", return_value="/fixture/tool"))
            stack.enter_context(mock.patch.object(detect, "client_version", return_value="2.0.0"))
            install = stack.enter_context(mock.patch.object(environment, "install"))
            stack.enter_context(mock.patch.object(environment, "verify_environment", return_value={"passed": True}))
            stack.enter_context(mock.patch.object(verify, "probe_servers", return_value={"passed": True}))
            stack.enter_context(mock.patch.object(verify, "verify", return_value={"passed": True, "errors": []}))
            first = setup.execute(args, self.root)
            second = setup.execute(setup.parser().parse_args(["--non-interactive"]), self.root)
        self.assertTrue(first["passed"])
        self.assertTrue(second["passed"])
        install.assert_not_called()
        self.assertEqual(second["plan"]["environment_mode"], "reuse")
        self.assertEqual(second["plan"]["biomass"], "enabled")
        self.assertIsNone(second["plan"]["manager_path"])
        self.assertEqual(list(self.prefix.iterdir()), [self.prefix / "untouched.txt"])

    def test_optional_missing_capability_prevents_plugin_and_all_config_writes(self):
        args = setup.parser().parse_args([
            "--client", "codex", "--environment-mode", "reuse", "--env-prefix", str(self.prefix),
            "--codex-home", str(self.home), "--with-biomass",
        ])
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(detect, "discover", return_value="/fixture/tool"))
            stack.enter_context(mock.patch.object(detect, "client_version", return_value="0.153.0"))
            stack.enter_context(mock.patch.object(environment, "verify_environment", return_value={"passed": True}))
            stack.enter_context(mock.patch.object(verify, "probe_servers",
                return_value={"passed": False, "errors": ["biomass: missing build_reactions"]}))
            write = stack.enter_context(mock.patch.object(setup, "write_config"))
            install_plugin = stack.enter_context(mock.patch.object(configure_codex, "ensure_plugin"))
            report = setup.execute(args, self.root)
        self.assertFalse(report["passed"])
        write.assert_not_called()
        install_plugin.assert_not_called()
        self.assertFalse(self.home.exists())
        self.assertFalse((self.root / ".setup").exists())

    def test_installed_profiles_get_idempotent_scoped_contract_guidance(self):
        self.home.mkdir()
        for role in ("literature_reviewer", "ode_modeler"):
            profile, server = configure_codex.SPECIALISTS[role]
            source = self.root / ".codex/profiles" / (profile + ".config.toml.example")
            payload = tomllib.loads(source.read_text())
            payload["developer_instructions"] = "Preserve this researcher guidance."
            payload["custom_setting"] = "retained"
            text = "\n".join(f"{configure_codex.toml_literal(k)}={configure_codex.toml_literal(v)}"
                             for k, v in payload.items())
            (self.home / (profile + ".config.toml")).write_text(text)
        outputs = configure_codex.render(self.root, self.prefix, self.home, with_biomass=True)
        for path, text in outputs.items():
            path.write_text(text)
        self.assertEqual(configure_codex.render(self.root, self.prefix, self.home, with_biomass=True), outputs)
        for role in ("literature_reviewer", "ode_modeler"):
            profile, _ = configure_codex.SPECIALISTS[role]
            payload = tomllib.loads(outputs[self.home / (profile + ".config.toml")])
            self.assertEqual(payload["custom_setting"], "retained")
            self.assertEqual(payload["developer_instructions"].count(configure_codex.ODE_PROFILE_GUIDANCE[role]), 1)
            self.assertIn("Preserve this researcher guidance.", payload["developer_instructions"])
            self.assertFalse(payload["features"]["apps"])
            self.assertFalse(payload["mcp_servers"]["specialist_dispatcher"]["enabled"])

    def test_default_profiles_disable_biomass_without_optional_executable(self):
        outputs = configure_codex.render(self.root, self.prefix, self.home)
        self.assertEqual(len(outputs), 4)
        for text in outputs.values():
            payload = tomllib.loads(text)
            self.assertFalse(payload["mcp_servers"]["biomass"]["enabled"])
            self.assertFalse(payload["features"]["apps"])
            self.assertFalse(payload["mcp_servers"]["specialist_dispatcher"]["enabled"])

    def test_enabled_biomass_parent_or_cross_domain_profile_is_rejected(self):
        parent = self.root / ".codex/config.toml"
        payload = tomllib.loads(parent.read_text())
        payload["mcp_servers"]["biomass"]["enabled"] = True
        parent.write_text("\n".join(f"{configure_codex.toml_literal(k)}={configure_codex.toml_literal(v)}"
                                    for k, v in payload.items()))
        with self.assertRaisesRegex(SetupError, "biomass must remain disabled"):
            configure_codex.render(self.root, self.prefix, self.home)

    def test_capability_probe_is_optional_and_uses_temporary_cache(self):
        def run(argv, **kwargs):
            server = Path(argv[-1]).name.removeprefix("mcp-").removesuffix("-server")
            self.assertNotEqual(server, "biomass")
            self.assertEqual(Path(kwargs["env"]["NUMBA_CACHE_DIR"]).parent, kwargs["cwd"])
            self.assertEqual(kwargs["env"]["PYTHONDONTWRITEBYTECODE"], "1")
            self.assertNotIn("PYTHONPATH", kwargs["env"])
            return mock.Mock(stdout=json.dumps({"tools": sorted(verify.SIGNATURES[server])}))
        with mock.patch.object(verify, "run", side_effect=run), \
             mock.patch.dict(os.environ, {"PYTHONPATH": "/untrusted"}):
            report = verify.probe_servers(self.prefix)
        self.assertTrue(report["passed"])
        self.assertEqual(set(report["mcp"]), {"neko", "maboss", "physicell"})

    def test_capability_inventory_rejects_invalid_shapes_duplicates_and_cross_domain_tools(self):
        invalid = [None, {}, {"tools": "build_reactions"}, {"tools": [None]},
                   {"tools": []}, {"tools": ["build_reactions", "build_reactions"]},
                   {"tools": ["build_reactions", "get_maboss_nodes"]}]
        for payload in invalid:
            with self.subTest(payload=payload), mock.patch.object(verify, "run",
                return_value=mock.Mock(stdout=json.dumps(payload))):
                report = verify.probe_servers(self.prefix, with_biomass=True)
            self.assertFalse(report["passed"])
            self.assertEqual(len(report["errors"]), 4)

    def test_biomass_capability_check_requires_session_creation(self):
        def run(argv, **kwargs):
            server = Path(argv[-1]).name.removeprefix("mcp-").removesuffix("-server")
            names = verify.SIGNATURES[server]
            if server == "neko":
                names = names | {"export_biomass_handoff"}
            if server == "biomass":
                names = names - {"create_session"}
            return mock.Mock(stdout=json.dumps({"tools": sorted(names)}))
        with mock.patch.object(verify, "run", side_effect=run):
            report = verify.probe_servers(self.prefix, with_biomass=True)
        self.assertFalse(report["passed"])
        self.assertEqual(report["errors"], ["biomass: missing required tools: create_session"])

    def test_capabilities_reject_complete_inventories_with_cross_domain_tools(self):
        for injected in ("build_reactions", "run_simulation"):
            def run(argv, **kwargs):
                server = Path(argv[-1]).name.removeprefix("mcp-").removesuffix("-server")
                names = verify.SIGNATURES[server]
                if server == "neko":
                    names = names | {injected, "export_biomass_handoff"}
                return mock.Mock(stdout=json.dumps({"tools": sorted(names)}))
            with self.subTest(injected=injected), mock.patch.object(verify, "run", side_effect=run):
                report = verify.probe_servers(self.prefix, with_biomass=True)
            self.assertFalse(report["passed"])
            self.assertEqual(report["errors"], ["neko: cross-domain modelling tools are exposed"])

    def test_setup_verification_requires_safe_literature_inventory_but_allows_no_backend(self):
        capabilities = {"passed": True, "errors": [], "mcp": {}}
        for safe in (False, True):
            literature = {"passed": safe, "pubmed": False, "servers": []}
            if not safe:
                literature["error"] = "prohibited MCP servers are enabled: biomass"
            with self.subTest(safe=safe), ExitStack() as stack:
                probe = stack.enter_context(mock.patch.object(verify, "probe_servers"))
                stack.enter_context(mock.patch.object(verify.check_environment, "specialist_inventory",
                    return_value={"passed": True}))
                stack.enter_context(mock.patch.object(verify.check_environment, "orchestrator_inventory",
                    return_value={"passed": True}))
                check_literature = stack.enter_context(mock.patch.object(verify.check_environment,
                    "literature_inventory", return_value=literature))
                report = verify.verify(self.root, self.prefix, {"codex": "fixture"},
                    with_biomass=True, capability_report=capabilities)
            self.assertEqual(report["passed"], safe)
            self.assertTrue(report["literature_isolation"]["degraded"])
            self.assertEqual(report["literature_isolation"]["passed"], safe)
            check_literature.assert_called_once_with("fixture", self.root)
            probe.assert_not_called()
            self.assertEqual(capabilities["errors"], [])

    def test_setup_starts_each_selected_server_once_and_still_checks_client_inventory(self):
        for enabled in (False, True):
            calls = []
            def run(argv, **kwargs):
                calls.append(argv)
                if argv[-2:] == ["mcp", "list"]:
                    return mock.Mock(stdout="fixture Claude inventory")
                server = Path(argv[-1]).name.removeprefix("mcp-").removesuffix("-server")
                names = verify.SIGNATURES[server]
                if enabled and server == "neko":
                    names = names | {"export_biomass_handoff"}
                return mock.Mock(stdout=json.dumps({"tools": sorted(names)}))
            args = setup.parser().parse_args([
                "--client", "claude", "--environment-mode", "reuse", "--env-prefix", str(self.prefix),
                *(["--with-biomass"] if enabled else []),
            ])
            with self.subTest(enabled=enabled), ExitStack() as stack:
                stack.enter_context(mock.patch.object(detect, "discover", return_value="/fixture/claude"))
                stack.enter_context(mock.patch.object(detect, "client_version", return_value="2.0.0"))
                stack.enter_context(mock.patch.object(environment, "verify_environment", return_value={"passed": True}))
                stack.enter_context(mock.patch.object(verify, "run", side_effect=run))
                report = setup.execute(args, self.root)
            self.assertTrue(report["passed"])
            selected = {"neko", "maboss", "physicell"} | ({"biomass"} if enabled else set())
            self.assertEqual(len(calls), len(selected) + 1)
            self.assertEqual(set(report["verification"]["mcp"]), selected)
            self.assertEqual(calls[-1], ["/fixture/claude", "mcp", "list"])
            if enabled:
                self.assertEqual(report["capabilities"]["mcp"], report["verification"]["mcp"])

    def test_external_environment_python_version_and_imports_are_checked_without_install(self):
        (self.prefix / "bin").mkdir()
        (self.prefix / "bin/python").touch()
        manifest = {**self.manifest, "executables": []}
        for version, expected in (([3, 10, 9], False), ([3, 11, 0], True)):
            def run(argv, **kwargs):
                self.assertNotIn("install", argv)
                if "-c" in argv:
                    self.assertIn("-I", argv)
                    self.assertIn("-B", argv)
                    self.assertEqual(Path(kwargs["env"]["NUMBA_CACHE_DIR"]).parent, kwargs["cwd"])
                    return mock.Mock(stdout=json.dumps({"version": manifest["version"], "python": version, "dependencies": manifest["dependency_pins"]}))
                return mock.Mock(stdout="")
            with self.subTest(version=version), mock.patch.object(environment, "run", side_effect=run):
                report = environment.verify_environment(self.prefix, manifest)
            self.assertEqual(report["passed"], expected)


if __name__ == "__main__":
    unittest.main()
