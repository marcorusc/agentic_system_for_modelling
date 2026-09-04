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


if __name__ == "__main__":
    unittest.main()
