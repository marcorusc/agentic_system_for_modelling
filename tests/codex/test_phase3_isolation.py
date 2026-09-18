"""Phase 3 transport and inventory boundaries using filesystem-only fixtures."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.codex import launcher_config as config
from scripts.codex import launcher_provenance as provenance


EXPECTED_ROLES = {
    "network_curator": ("biomodel-network-curator", "neko"),
    "literature_reviewer": ("biomodel-literature-reviewer", None),
    "boolean_dynamics_modeler": ("biomodel-boolean-dynamics-modeler", "maboss"),
    "multicellular_configurator": ("biomodel-multicellular-configurator", "physicell"),
    "ode_modeler": ("biomodel-ode-modeler", "biomass"),
}


def overrides(command):
    return [command[i + 1] for i, value in enumerate(command[:-1]) if value == "-c"]


class Phase3IsolationTests(unittest.TestCase):
    def test_every_role_uses_the_same_restricted_inventory_and_execution_config(self):
        self.assertEqual(config.SPECIALISTS, EXPECTED_ROLES)
        self.assertEqual(set(config.MODELLING_SERVERS), {"neko", "maboss", "physicell", "biomass"})
        for role, (profile, permitted) in EXPECTED_ROLES.items():
            with self.subTest(role=role):
                preflight = config.build_mcp_list_command("codex", role)
                execution = config.build_command("codex", role, "bounded task")
                self.assertEqual(overrides(preflight), overrides(execution))
                self.assertIn("features.apps=false", overrides(execution))
                self.assertIn(
                    'mcp_servers.specialist_dispatcher={"command"="__disabled_specialist_dispatcher__","enabled"=false}',
                    overrides(execution),
                )
                disabled_biomass = 'mcp_servers.biomass={"command"="__disabled_biomass__","enabled"=false}'
                if permitted != "biomass":
                    self.assertIn(disabled_biomass, overrides(execution))
                else:
                    self.assertNotIn(disabled_biomass, overrides(execution))
                for server in config.MODELLING_SERVERS:
                    state = "true" if server == permitted else "false"
                    self.assertIn(f"mcp_servers.{server}.enabled={state}", overrides(execution))
                self.assertEqual(execution[execution.index("--profile") + 1], profile)
                self.assertIn("--ephemeral", execution)
                self.assertIn("--strict-config", execution)
                self.assertEqual(execution[execution.index("--sandbox") + 1], "read-only")
                self.assertNotIn("resume", execution)

    def test_each_role_accepts_only_its_exact_server_and_rejects_aliases(self):
        for role, (_, permitted) in EXPECTED_ROLES.items():
            allowed = permitted or "pubmed"
            safe = [{"name": name, "enabled": name == allowed}
                    for name in (*config.MODELLING_SERVERS, "pubmed", "specialist_dispatcher")]
            with self.subTest(role=role):
                configured = config.validate_mcp_inventory(safe, role)
                self.assertTrue(configured[allowed])
                for extra in (
                    "biomass_alias", "ode_dynamics_modeler", "unknown_connector",
                    "codex_apps", "specialist_dispatcher",
                    *(name for name in config.MODELLING_SERVERS if name != permitted),
                ):
                    unsafe = [row for row in safe if row["name"] != extra]
                    unsafe.append({"name": extra, "enabled": True})
                    with self.subTest(extra=extra), self.assertRaisesRegex(ValueError, "prohibited"):
                        config.validate_mcp_inventory(unsafe, role)
                if permitted:
                    with self.assertRaisesRegex(ValueError, "permitted"):
                        config.validate_mcp_inventory([], role)

    def test_ode_requires_canonical_role_and_unambiguous_inventory(self):
        for role in ("ode_dynamics_modeler", "biomass", "unknown"):
            with self.subTest(role=role), self.assertRaises((ValueError, KeyError)):
                config.build_command("codex", role, "inspect")
            with self.subTest(role=role), self.assertRaises((ValueError, KeyError)):
                config.validate_mcp_inventory([{"name": "biomass", "enabled": True}], role)
        invalid = [
            {}, ["biomass"], [{"name": "biomass", "enabled": "true"}],
            [{"name": "biomass", "enabled": True}, {"name": "biomass", "enabled": False}],
        ]
        for inventory in invalid:
            with self.subTest(inventory=inventory), self.assertRaises(ValueError):
                config.validate_mcp_inventory(inventory, "ode_modeler")

    def test_complete_profile_transport_is_role_scoped_and_identical_in_both_commands(self):
        with tempfile.TemporaryDirectory() as temporary:
            profile = Path(temporary) / "profile.toml"
            profile.write_text("\n".join(
                f'[mcp_servers.{name}]\ncommand = "/fixture/{name}"\nargs = ["--fixture"]\n'
                f'[mcp_servers.{name}.env]\nFIXTURE = "{name}-transport"\n'
                for name in (*config.MODELLING_SERVERS, "pubmed", "specialist_dispatcher")
            ))
            for role, (_, permitted) in EXPECTED_ROLES.items():
                with self.subTest(role=role):
                    server = permitted or "pubmed"
                    transport = config.load_permitted_transport(profile, role)
                    self.assertEqual(len(transport), 2)
                    self.assertTrue(transport[1].startswith(f"mcp_servers.{server}="))
                    self.assertIn(f'"command"="/fixture/{server}"', transport[1])
                    self.assertIn(f'"FIXTURE"="{server}-transport"', transport[1])
                    kwargs = {"transport_arguments": transport, "pubmed_transport": permitted is None}
                    preflight = config.build_mcp_list_command("codex", role, **kwargs)
                    execution = config.build_command("codex", role, "inspect", **kwargs)
                    self.assertEqual(overrides(preflight), overrides(execution))
                    self.assertEqual(overrides(execution)[0], transport[1])

    def test_ode_cannot_load_a_substitute_transport(self):
        for contents in (
            '[mcp_servers.neko]\ncommand="fixture"\n',
            '[mcp_servers.biomass]\nargs=[]\n',
            '[mcp_servers.biomass_alias]\ncommand="fixture"\n',
        ):
            with self.subTest(contents=contents), tempfile.TemporaryDirectory() as temporary:
                profile = Path(temporary) / "profile.toml"
                profile.write_text(contents)
                with self.assertRaisesRegex(ValueError, "biomass transport"):
                    config.load_permitted_transport(profile, "ode_modeler")

    def test_ode_approval_is_exact_and_destructive_tools_remain_disabled(self):
        command = config.build_command("codex", "ode_modeler", "inspect", approved_tools=["inspect_session"])
        self.assertIn('mcp_servers.biomass.tools.inspect_session.approval_mode="approve"', command)
        self.assertIn('mcp_servers.biomass.disabled_tools=["delete_session","clean_generated_files","close_session"]', command)
        self.assertFalse(any(".tools." in value and "mcp_servers.biomass." not in value for value in command))
        for tool in ("delete_session", "clean_generated_files", "close_session", "*", "biomass.inspect_session"):
            with self.subTest(tool=tool), self.assertRaises(ValueError):
                config.build_command("codex", "ode_modeler", "inspect", approved_tools=[tool])
        with self.assertRaisesRegex(ValueError, "literature_reviewer"):
            config.build_command("codex", "ode_modeler", "inspect", allow_web_search=True)

    def test_command_declares_canonical_ode_contract_and_exact_review_mode(self):
        task = "Review this exact claim; $(false) `false`"
        command = config.build_command("codex", "ode_modeler", task)
        for text in ("specialist=ode_modeler", "stage=biomass_ode", "schema_version=1", "ode.contract_version=2"):
            self.assertIn(text, command[-1])
        for mode in (None, "edge", "ode"):
            with self.subTest(mode=mode):
                command = config.build_command("codex", "literature_reviewer", task, review_kind=mode)
                self.assertIn(f"review_kind={mode or 'edge'} exactly", command[-1])
                self.assertTrue(command[-1].endswith("Task:\n" + task))
                self.assertEqual(command[-1].count(task), 1)
                self.assertNotIn("sh", command)
                self.assertNotIn("bash", command)

    def test_review_mode_rejects_invalid_values_and_nonliterature_roles(self):
        for value in ("", "ODE", "unknown", False, [], {}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                config.normalize_review_kind("literature_reviewer", value)
        for role in set(EXPECTED_ROLES) - {"literature_reviewer"}:
            self.assertIsNone(config.normalize_review_kind(role, None))
            for mode in ("edge", "ode"):
                with self.subTest(role=role, mode=mode), self.assertRaises(ValueError):
                    config.build_command("codex", role, "inspect", review_kind=mode)

    def test_windows_bridge_preserves_explicit_mode_and_session_without_shell(self):
        settings = {
            "wsl_executable": "wsl.exe", "distribution": "fixture",
            "project_path": "/fixture/project", "python_executable": "python3",
            "codex_executable": "/fixture/codex",
        }
        kwargs = dict(prompt=None, prompt_file=".codex-tasks/review.txt", allow_web_search=True,
                      record_session_id="biomass-session-1")
        for mode in (None, "edge", "ode"):
            with self.subTest(mode=mode):
                command = config.build_wsl_command(settings, "literature_reviewer", review_kind=mode, **kwargs)
                self.assertEqual(command.count("--review-kind"), 1)
                self.assertEqual(command[command.index("--review-kind") + 1], mode or "edge")
                self.assertEqual(command[command.index("--record-session-id") + 1], "biomass-session-1")
                self.assertIn("--allow-web-search", command)
                self.assertNotIn("sh", command)
                self.assertNotIn("bash", command)
        kwargs.update(allow_web_search=False)
        command = config.build_wsl_command(settings, "ode_modeler", **kwargs)
        self.assertNotIn("--review-kind", command)
        with self.assertRaisesRegex(ValueError, "record_session_id"):
            config.build_wsl_command(settings, "literature_reviewer", review_kind="ode",
                                     **dict(kwargs, record_session_id=None))
        with self.assertRaisesRegex(ValueError, "literature_reviewer"):
            config.build_wsl_command(settings, "ode_modeler", review_kind="ode", **kwargs)


class Phase3ProvenanceTests(unittest.TestCase):
    def test_each_mode_moves_all_launcher_artifacts_to_its_session_root(self):
        cases = [
            ("network_curator", None, "network-curator"),
            ("boolean_dynamics_modeler", None, "boolean-dynamics-modeler"),
            ("multicellular_configurator", None, "multicellular-configurator"),
            ("ode_modeler", None, "ode-modeler"),
            ("literature_reviewer", None, "network-curator"),
            ("literature_reviewer", "edge", "network-curator"),
            ("literature_reviewer", "ode", "ode-modeler"),
        ]
        for role, mode, directory in cases:
            with self.subTest(role=role, mode=mode), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                base = root / "runs" / directory
                self.assertEqual(provenance.specialist_run_base(root, role, mode), base)
                launcher = provenance.create_launcher_run(project_root=root, specialist=role,
                    prompt="bounded task", launcher_run_id="launcher-1", review_kind=mode)
                self.assertEqual(launcher, base / "_launcher-runs/launcher-1")
                (launcher / "events.jsonl").write_text('{"type":"turn.completed"}\n')
                metadata = {"specialist": role, "review_kind": mode}
                handoff = {"specialist": role, "session_id": "session-1", "status": "blocked"}
                target = provenance.record_invocation(project_root=root, specialist=role,
                    prompt="bounded task", final_output=json.dumps(handoff), handoff=handoff,
                    expected_session_id="session-1", provenance=metadata, invocation_id="launcher-1",
                    launcher_dir=launcher, review_kind=mode)
                self.assertEqual(target, base / "session-1/specialist-invocations/launcher-1")
                self.assertFalse(launcher.exists())
                self.assertEqual((target / "task.txt").read_text(), "bounded task\n")
                self.assertTrue((target / "events.jsonl").is_file())
                self.assertEqual(json.loads((target / "provenance.json").read_text()), metadata)
                self.assertEqual(json.loads((target / "handoff.json").read_text()), handoff)

    def test_review_mode_cannot_move_launcher_artifacts_between_roots(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            launcher = provenance.create_launcher_run(project_root=root, specialist="literature_reviewer",
                prompt="claim review", launcher_run_id="launcher-1", review_kind="ode")
            with self.assertRaisesRegex(ValueError, "outside the launcher run root"):
                provenance.record_invocation(project_root=root, specialist="literature_reviewer",
                    prompt="claim review", final_output="{}", handoff=None, expected_session_id="session-1",
                    provenance={}, invocation_id="launcher-1", launcher_dir=launcher, review_kind="edge")
            self.assertTrue(launcher.is_dir())
            self.assertFalse((root / "runs/network-curator").exists())

    def test_ode_run_root_rejects_symlink_escape_and_unknown_role_or_mode(self):
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as outside:
            root = Path(temporary)
            (root / "runs").mkdir()
            (root / "runs/ode-modeler").symlink_to(outside, target_is_directory=True)
            for role, mode in (("ode_modeler", None), ("literature_reviewer", "ode")):
                with self.subTest(role=role), self.assertRaisesRegex(ValueError, "outside the project"):
                    provenance.create_launcher_run(project_root=root, specialist=role,
                        prompt="bounded task", launcher_run_id="launcher-1", review_kind=mode)
            for role, mode in (("ode_dynamics_modeler", None), ("ode_modeler", "edge"),
                               ("literature_reviewer", "unknown")):
                with self.subTest(role=role, mode=mode), self.assertRaises(ValueError):
                    provenance.specialist_run_base(root, role, mode)
            self.assertEqual(list(Path(outside).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
