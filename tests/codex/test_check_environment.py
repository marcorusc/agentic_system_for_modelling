from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.codex import check_environment as environment


class EnvironmentCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="codex-preflight-")
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_required_paths_include_reset_templates(self) -> None:
        (self.root / ".model").mkdir()
        (self.root / ".model/config.json").write_text(
            '{"reset_files":{"MODEL_SPEC.md":"templates/MODEL_SPEC.md"}}',
            encoding="utf-8",
        )
        required, missing = environment.required_paths(self.root)
        self.assertIn("templates/MODEL_SPEC.md", required)
        self.assertIn("templates/MODEL_SPEC.md", missing)

    def test_inventory_output_retains_names_only(self) -> None:
        payload = '[{"name":"neko","enabled":true,"command":"/secret/path","env":{"TOKEN":"secret"}}]'
        completed = mock.Mock(returncode=0, stdout=payload, stderr="")
        with mock.patch.object(environment, "_run", return_value=completed):
            inventory, error = environment._inventory(["codex"], self.root)
        self.assertIsNone(error)
        self.assertEqual(inventory, [{"name": "neko", "enabled": True}])
        self.assertNotIn("secret", str(inventory))

    def test_success_requires_all_modelling_specialists_but_not_pubmed(self) -> None:
        with (
            mock.patch.object(environment, "current_branch", return_value="codex-compatible"),
            mock.patch.object(environment, "required_paths", return_value=(["AGENTS.md"], [])),
            mock.patch.object(environment, "codex_version", return_value=("0.153.0", True)),
            mock.patch.object(environment, "orchestrator_inventory", return_value={"passed": True, "servers": []}),
            mock.patch.object(environment, "specialist_inventory", return_value={"passed": True, "servers": []}),
            mock.patch.object(environment, "literature_inventory", return_value={"passed": True, "pubmed": False, "servers": []}),
            mock.patch.object(environment, "lifecycle_check", return_value={"passed": True}),
        ):
            report = environment.check_environment(
                project_root=self.root,
                codex="codex",
                expected_branch="codex-compatible",
                allow_web_search=False,
            )
        self.assertTrue(report["passed"])
        self.assertTrue(report["literature"]["degraded"])
        self.assertEqual(report["literature"]["backend"], "unavailable")

    def test_explicit_web_search_is_reported_as_the_fallback(self) -> None:
        with (
            mock.patch.object(environment, "current_branch", return_value="codex-compatible"),
            mock.patch.object(environment, "required_paths", return_value=([], [])),
            mock.patch.object(environment, "codex_version", return_value=("0.153.0", True)),
            mock.patch.object(environment, "orchestrator_inventory", return_value={"passed": True}),
            mock.patch.object(environment, "specialist_inventory", return_value={"passed": True}),
            mock.patch.object(environment, "literature_inventory", return_value={"passed": True, "pubmed": False}),
            mock.patch.object(environment, "lifecycle_check", return_value={"passed": True}),
        ):
            report = environment.check_environment(
                project_root=self.root,
                codex="codex",
                expected_branch="codex-compatible",
                allow_web_search=True,
            )
        self.assertEqual(report["literature"]["backend"], "web_search")

    def test_missing_modelling_server_fails_preflight(self) -> None:
        def specialist_result(_codex, specialist, _root):
            return {"passed": specialist != "network_curator"}

        with (
            mock.patch.object(environment, "current_branch", return_value="codex-compatible"),
            mock.patch.object(environment, "required_paths", return_value=([], [])),
            mock.patch.object(environment, "codex_version", return_value=("0.153.0", True)),
            mock.patch.object(environment, "orchestrator_inventory", return_value={"passed": True}),
            mock.patch.object(environment, "specialist_inventory", side_effect=specialist_result),
            mock.patch.object(environment, "literature_inventory", return_value={"passed": True, "pubmed": False}),
            mock.patch.object(environment, "lifecycle_check", return_value={"passed": True}),
        ):
            report = environment.check_environment(
                project_root=self.root,
                codex="codex",
                expected_branch="codex-compatible",
                allow_web_search=False,
            )
        self.assertFalse(report["passed"])

    def test_parent_with_modelling_access_fails_preflight(self) -> None:
        with (
            mock.patch.object(environment, "current_branch", return_value="codex-compatible"),
            mock.patch.object(environment, "required_paths", return_value=([], [])),
            mock.patch.object(environment, "codex_version", return_value=("0.153.0", True)),
            mock.patch.object(environment, "orchestrator_inventory", return_value={"passed": False}),
            mock.patch.object(environment, "specialist_inventory", return_value={"passed": True}),
            mock.patch.object(environment, "literature_inventory", return_value={"passed": True, "pubmed": False}),
            mock.patch.object(environment, "lifecycle_check", return_value={"passed": True}),
        ):
            report = environment.check_environment(
                project_root=self.root,
                codex="codex",
                expected_branch="codex-compatible",
                allow_web_search=False,
            )
        self.assertFalse(report["passed"])


    def test_biomass_inventory_is_checked_only_when_explicitly_selected(self) -> None:
        for enabled in (False, True):
            for ode_passed in (False, True):
                def specialist_result(_codex, specialist, _root):
                    return {"passed": specialist != "ode_modeler" or ode_passed}
                with (
                    self.subTest(enabled=enabled, ode_passed=ode_passed),
                    mock.patch.object(environment, "current_branch", return_value="fixture"),
                    mock.patch.object(environment, "required_paths", return_value=([], [])),
                    mock.patch.object(environment, "codex_version", return_value=("0.153.0", True)),
                    mock.patch.object(environment, "orchestrator_inventory", return_value={"passed": True}),
                    mock.patch.object(environment, "specialist_inventory", side_effect=specialist_result) as inventory,
                    mock.patch.object(environment, "literature_inventory", return_value={"passed": True, "pubmed": False}),
                    mock.patch.object(environment, "lifecycle_check", return_value={"passed": True}),
                ):
                    report = environment.check_environment(project_root=self.root, codex="fixture",
                        expected_branch="fixture", allow_web_search=False, with_biomass=enabled)
                expected = set(environment.MODEL_SPECIALISTS) | ({"ode_modeler"} if enabled else set())
                self.assertEqual(set(report["specialists"]), expected)
                self.assertEqual({call.args[1] for call in inventory.call_args_list}, expected)
                self.assertEqual(report["passed"], not enabled or ode_passed)

    def test_parent_biomass_is_prohibited_even_when_ode_is_not_selected(self) -> None:
        with mock.patch.object(environment, "_inventory", return_value=([
            {"name": "biomass", "enabled": True},
            {"name": "specialist_dispatcher", "enabled": True},
        ], None)):
            report = environment.orchestrator_inventory("fixture", self.root)
        self.assertFalse(report["passed"])
        self.assertEqual(report["enabled_modelling_servers"], ["biomass"])

    def test_unsafe_literature_biomass_inventory_fails_overall_readiness(self) -> None:
        profile = self.root / "literature.config.toml"
        profile.write_text('[mcp_servers.pubmed]\ncommand="fixture-pubmed"\n')
        with mock.patch.object(environment.run_specialist, "profile_path", return_value=profile), \
             mock.patch.object(environment, "_inventory", return_value=([
                 {"name": "pubmed", "enabled": True}, {"name": "biomass", "enabled": True},
             ], None)):
            unsafe = environment.literature_inventory("fixture", self.root)
        self.assertFalse(unsafe["passed"])
        self.assertIn("biomass", unsafe["error"])
        with (
            mock.patch.object(environment, "current_branch", return_value="fixture"),
            mock.patch.object(environment, "required_paths", return_value=([], [])),
            mock.patch.object(environment, "codex_version", return_value=("0.153.0", True)),
            mock.patch.object(environment, "orchestrator_inventory", return_value={"passed": True}),
            mock.patch.object(environment, "specialist_inventory", return_value={"passed": True}),
            mock.patch.object(environment, "literature_inventory", return_value=unsafe),
            mock.patch.object(environment, "lifecycle_check", return_value={"passed": True}),
        ):
            report = environment.check_environment(project_root=self.root, codex="fixture",
                expected_branch="fixture", allow_web_search=True, with_biomass=True)
        self.assertFalse(report["passed"])
        self.assertFalse(report["literature"]["passed"])

    def test_optional_cli_flag_defaults_off_and_is_forwarded(self) -> None:
        self.assertFalse(environment.parse_args([]).with_biomass)
        with mock.patch.object(environment.run_specialist, "resolve_codex_executable", return_value="fixture"), \
             mock.patch.object(environment, "check_environment", return_value={"passed": True}) as check, \
             mock.patch("builtins.print"):
            self.assertEqual(environment.main(["--with-biomass"]), 0)
        self.assertTrue(check.call_args.kwargs["with_biomass"])


if __name__ == "__main__":
    unittest.main()
