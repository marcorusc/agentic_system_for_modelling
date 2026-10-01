"""Release compatibility must be checked before configuring either client."""
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest import mock

from scripts import setup
from scripts.setup_support import configure_claude, environment
from scripts.setup_support.state import SetupError

ROOT = Path(__file__).resolve().parents[2]


class ReleaseVersionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.prefix = self.root / "environment"
        self.manifest = tomllib.loads((ROOT / "setup/dependencies.toml").read_text())
        self.versions = {"version": self.manifest["version"], "python": [3, 11, 0],
                         "dependencies": dict(self.manifest["dependency_pins"])}

    def fake_run(self, argv, **kwargs):
        if "venv" in argv:
            (self.prefix / "bin").mkdir(parents=True)
            (self.prefix / "bin/python").touch()
        if "-c" in argv:
            self.assertIn("nekomata", argv[-1])
            return mock.Mock(stdout=json.dumps(self.versions))
        return mock.Mock(stdout="")

    def test_installed_pair_and_missing_metadata(self):
        (self.prefix / "bin").mkdir(parents=True)
        (self.prefix / "bin/python").touch()
        for version, expected in (("1.10.1", True), ("1.10.0", False), ("1.11.0", False), (None, False)):
            self.versions["dependencies"] = {"nekomata": version} if version else {}
            with self.subTest(version=version), mock.patch.object(environment, "run", side_effect=self.fake_run):
                report = environment.verify_environment(self.prefix, {**self.manifest, "executables": []})
            self.assertEqual(report["passed"], expected)
            if not expected:
                self.assertIn("Expected nekomata 1.10.1", " ".join(report["errors"]))

    def test_pypi_and_legacy_source_install_pin_neko(self):
        for source in (None, "/fixture/source checkout"):
            self.prefix = self.root / ("pypi" if source is None else "source")
            with self.subTest(source=source), mock.patch.object(environment, "run", side_effect=self.fake_run) as run:
                environment.install(self.prefix, "venv", "python", self.manifest, source)
            command = next(call.args[0] for call in run.call_args_list if "install" in call.args[0])
            self.assertIn("nekomata==1.10.1", command)
            self.assertIn(source or "mcp-biomodelling-servers==2.4.0", command)

    def test_changed_dependency_pin_requires_new_environment(self):
        with mock.patch.object(environment, "run", side_effect=self.fake_run):
            environment.install(self.prefix, "venv", "python", self.manifest)
        changed = {**self.manifest, "dependency_pins": {"nekomata": "1.10.2"}}
        with mock.patch.object(environment, "run") as run:
            with self.assertRaisesRegex(SetupError, "new --env-prefix"):
                environment.install(self.prefix, "venv", "python", changed)
        run.assert_not_called()

    def test_stale_neko_blocks_check_and_reuse_before_configuration_writes(self):
        (self.prefix / "bin").mkdir(parents=True)
        (self.prefix / "bin/python").touch()
        (self.root / "setup").mkdir()
        (self.root / "setup/dependencies.toml").write_text((ROOT / "setup/dependencies.toml").read_text())
        self.versions["dependencies"]["nekomata"] = "1.10.0"
        resolved = {"clients": {"claude": "/fixture/claude"}, "env_prefix": str(self.prefix),
                    "environment_mode": "reuse", "biomass": "disabled", "graphviz_path": None,
                    "pinned_sources": None}
        for flags in (["--check"], ["--environment-mode", "reuse"]):
            with self.subTest(flags=flags), ExitStack() as stack:
                stack.enter_context(mock.patch.object(setup, "plan", return_value=(resolved, [])))
                stack.enter_context(mock.patch.object(configure_claude, "render", return_value={self.root / "config": "new"}))
                stack.enter_context(mock.patch.object(environment, "run", side_effect=self.fake_run))
                install = stack.enter_context(mock.patch.object(environment, "install"))
                write = stack.enter_context(mock.patch.object(setup, "write_config"))
                report = setup.execute(setup.parser().parse_args(flags), self.root)
            self.assertFalse(report["passed"])
            self.assertIn("Expected nekomata 1.10.1", " ".join(report["errors"]))
            install.assert_not_called()
            write.assert_not_called()
            self.assertFalse((self.root / ".setup").exists())


if __name__ == "__main__":
    unittest.main()
