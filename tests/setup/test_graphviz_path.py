"""Preserve an explicitly discovered dependency without saving the shell PATH."""
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
from scripts.setup_support import configure_claude, configure_codex, detect, environment, verify


ROOT = Path(__file__).resolve().parents[2]


class GraphvizPathTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.root = self.directory / "project"
        self.root.mkdir()
        for name in ("setup", ".codex", ".codex-plugin", ".claude/agents"):
            shutil.copytree(ROOT / name, self.root / name)
        self.prefix = self.directory / "environment"
        self.home = self.directory / "codex"
        self.graphviz = self.directory / "custom-graphviz/bin/dot"
        self.graphviz.parent.mkdir(parents=True)
        self.graphviz.write_text("#!/bin/sh\nexit 0\n")
        self.graphviz.chmod(0o755)
        self.transient = self.directory / "codex-transient-helper"
        self.transient.mkdir()

    def test_discovered_graphviz_survives_runtime_and_both_generated_clients(self):
        with mock.patch.dict(os.environ, {"PATH": f"{self.transient}:{self.graphviz.parent}:/usr/bin"}):
            found = detect.discover("dot")
            self.assertEqual(found, str(self.graphviz))
            runtime = environment.runtime_env(self.prefix, graphviz_path=found)
            codex = configure_codex.render(self.root, self.prefix, self.home, graphviz_path=found)
            claude = configure_claude.render(self.root, self.prefix, graphviz_path=found)
        self.assertEqual(shutil.which("dot", path=runtime["PATH"]), found)
        self.assertNotIn(str(self.transient), runtime["PATH"])
        for text in codex.values():
            payload = tomllib.loads(text)
            for name, server in payload["mcp_servers"].items():
                if name != "pubmed" and server.get("enabled"):
                    self.assertEqual(shutil.which("dot", path=server["env"]["PATH"]), found)
                    self.assertNotIn(str(self.transient), server["env"]["PATH"])
        for path, text in claude.items():
            if path.stem != "literature-reviewer":
                self.assertIn("PATH: " + json.dumps(runtime["PATH"]), text)
                self.assertNotIn(str(self.transient), text)

    def test_setup_persists_resolved_dot_for_a_later_shell(self):
        original_discover = detect.discover
        def discover(name, override=None):
            if name == "dot":
                return original_discover(name, override)
            return override or "/fixture/tool"
        args = setup.parser().parse_args([
            "--client", "codex", "--manager", "venv", "--env-prefix", str(self.prefix),
            "--codex-home", str(self.home), "--non-interactive",
        ])
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(detect, "discover", side_effect=discover))
            stack.enter_context(mock.patch.object(detect, "client_version",
                side_effect=lambda name, _: "3.11.0" if name == "python" else "0.153.0"))
            stack.enter_context(mock.patch.object(environment, "install"))
            inspect = stack.enter_context(mock.patch.object(environment, "verify_environment", return_value={"passed": True}))
            stack.enter_context(mock.patch.object(configure_codex, "ensure_plugin"))
            check = stack.enter_context(mock.patch.object(verify, "verify", return_value={"passed": True, "errors": []}))
            with mock.patch.dict(os.environ, {"PATH": f"{self.transient}:{self.graphviz.parent}:/usr/bin"}):
                first = setup.execute(args, self.root)
            with mock.patch.dict(os.environ, {"PATH": "/usr/bin:/bin"}):
                second = setup.execute(setup.parser().parse_args(["--non-interactive"]), self.root)
        self.assertTrue(first["passed"])
        self.assertTrue(second["passed"])
        saved = json.loads((self.root / ".setup/local.json").read_text())
        self.assertEqual(saved["graphviz_path"], str(self.graphviz))
        self.assertEqual(second["plan"]["graphviz_path"], str(self.graphviz))
        self.assertEqual(inspect.call_args.kwargs["graphviz_path"], str(self.graphviz))
        self.assertEqual(check.call_args.kwargs["graphviz_path"], str(self.graphviz))
        self.assertTrue(all(not item["changed"] for item in second["writes"]))

    def test_stable_dot_alias_is_retained_when_underlying_binary_has_another_name(self):
        binary = self.directory / "custom-graphviz/libexec/graphviz-engine"
        binary.parent.mkdir(parents=True)
        binary.write_text("#!/bin/sh\nexit 0\n")
        binary.chmod(0o755)
        self.graphviz.unlink()
        self.graphviz.symlink_to(binary)
        found = detect.discover("dot", str(self.graphviz))
        self.assertEqual(found, str(self.graphviz))
        path = environment.runtime_env(self.prefix, graphviz_path=found)["PATH"]
        self.assertEqual(shutil.which("dot", path=path), str(self.graphviz))

    def test_chosen_dot_symlink_entrypoint_is_preserved_during_planning(self):
        link = self.directory / "graphviz-entrypoint/bin/dot"
        link.parent.mkdir(parents=True)
        link.symlink_to(self.graphviz)
        args = setup.parser().parse_args([
            "--client", "claude", "--environment-mode", "reuse", "--graphviz-path", str(link),
        ])
        original_discover = detect.discover
        def discover(name, override=None):
            return original_discover(name, override) if name == "dot" else "/fixture/tool"
        manifest = tomllib.loads((self.root / "setup/dependencies.toml").read_text())
        with mock.patch.object(detect, "discover", side_effect=discover), \
             mock.patch.object(detect, "client_version", return_value="2.0.0"):
            plan, errors = setup.plan(args, self.root, manifest)
        self.assertFalse(errors)
        self.assertEqual(plan["graphviz_path"], str(link))
        path = environment.transport_path(self.prefix, graphviz_path=plan["graphviz_path"])
        self.assertNotIn(str(self.transient), path)
        self.assertEqual(shutil.which("dot", path=path), str(link))


if __name__ == "__main__":
    unittest.main()
