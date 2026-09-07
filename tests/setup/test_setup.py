from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from scripts import setup
from scripts.setup_support import configure_claude, configure_codex, detect, environment
from scripts.setup_support.state import SetupError, write_config

ROOT = Path(__file__).resolve().parents[2]


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/"project with spaces"
        self.root.mkdir()
        for name in ("setup", ".codex", ".codex-plugin", ".claude/agents"):
            shutil.copytree(ROOT/name, self.root/name)
        self.prefix = self.root/".setup/environment"
        self.home = Path(self.temp.name)/"codex home"
        self.manifest = tomllib.loads((self.root/"setup/dependencies.toml").read_text())

    def test_codex_profiles_preserve_unrelated_settings_and_disabled_parent(self):
        outputs = configure_codex.render(self.root, self.prefix, self.home)
        self.assertEqual(len(outputs), 4)
        target = self.home/"biomodel-network-curator.config.toml"
        payload = tomllib.loads(outputs[target])
        self.assertEqual(payload["mcp_servers"]["neko"]["command"], str(self.prefix/"bin/mcp-neko-server"))
        self.assertFalse(payload["mcp_servers"]["maboss"]["enabled"])
        self.home.mkdir()
        target.write_text(outputs[target] + '\ncustom_setting = "retain"\n')
        self.assertEqual(tomllib.loads(configure_codex.render(self.root, self.prefix, self.home)[target])["custom_setting"], "retain")

    def test_codex_rejects_unrelated_enabled_server(self):
        self.home.mkdir()
        profile = self.home/"biomodel-network-curator.config.toml"
        profile.write_text('[mcp_servers.alias]\ncommand="unwanted"\nenabled=true\n')
        with self.assertRaisesRegex(SetupError, "Unexpected"):
            configure_codex.render(self.root, self.prefix, self.home)

    def plugin_entry(self, **changes):
        manifest = json.loads((self.root/'.codex-plugin/plugin.json').read_text())
        entry = {
            'pluginId': 'agentic-system-for-modelling@agentic-modelling-local',
            'name': 'agentic-system-for-modelling',
            'marketplaceName': 'agentic-modelling-local',
            'version': manifest['version'],
            'installed': True,
            'enabled': True,
            'source': {'source': 'local', 'path': str(self.root)},
            'marketplaceSource': {'sourceType': 'local', 'source': str(self.root)},
        }
        entry.update(changes)
        return entry

    def marketplace_payload(self, root=None):
        return json.dumps({'marketplaces': [{
            'name': 'agentic-modelling-local',
            'root': str(root or self.root),
        }]})

    def test_plugin_install_uses_structured_state_and_verifies_the_result(self):
        responses = [
            mock.Mock(stdout=self.marketplace_payload()),
            mock.Mock(stdout=json.dumps({'installed': []})),
            mock.Mock(stdout='installed'),
            mock.Mock(stdout=json.dumps({'installed': [self.plugin_entry()]})),
        ]
        with mock.patch.object(detect, 'run', side_effect=responses) as run:
            configure_codex.ensure_plugin(self.root, '/tools/codex')
        self.assertEqual(run.call_args_list[2].args[0], [
            '/tools/codex', 'plugin', 'add',
            'agentic-system-for-modelling@agentic-modelling-local',
        ])
        self.assertIn('--json', run.call_args_list[1].args[0])

    def test_plugin_registers_missing_marketplace_and_verifies_the_result(self):
        responses = [
            mock.Mock(stdout=json.dumps({'marketplaces': []})),
            mock.Mock(stdout='registered'),
            mock.Mock(stdout=self.marketplace_payload()),
            mock.Mock(stdout=json.dumps({'installed': [self.plugin_entry()]})),
        ]
        with mock.patch.object(detect, 'run', side_effect=responses) as run:
            configure_codex.ensure_plugin(self.root, '/tools/codex')
        self.assertEqual(run.call_args_list[1].args[0], [
            '/tools/codex', 'plugin', 'marketplace', 'add', str(self.root),
        ])
        self.assertIn('--json', run.call_args_list[2].args[0])

    def test_plugin_check_rejects_missing_stale_or_disabled_installations(self):
        cases = (
            [],
            [self.plugin_entry(version='older')],
            [self.plugin_entry(enabled=False)],
        )
        for installed in cases:
            with self.subTest(installed=installed), mock.patch.object(
                detect, 'run', side_effect=[
                    mock.Mock(stdout=self.marketplace_payload()),
                    mock.Mock(stdout=json.dumps({'installed': installed})),
                ]
            ):
                with self.assertRaisesRegex(SetupError, 'stale or unavailable'):
                    configure_codex.ensure_plugin(
                        self.root, '/tools/codex', check=True
                    )

    def test_plugin_rejects_marketplace_name_bound_to_another_root(self):
        with mock.patch.object(detect, 'run', return_value=mock.Mock(
            stdout=self.marketplace_payload(self.root/'other')
        )) as run:
            with self.assertRaisesRegex(SetupError, 'different repository'):
                configure_codex.ensure_plugin(self.root, '/tools/codex')
        run.assert_called_once()

    def test_claude_only_changes_transports_and_hook(self):
        outputs = configure_claude.render(self.root, self.prefix)
        self.assertEqual(len(outputs), 4)
        for path, text in outputs.items():
            if path.stem != "literature-reviewer":
                old = path.read_text()
                self.assertEqual(old.split('---\n', 2)[2], text.split('---\n', 2)[2])
                self.assertIn('permissionMode: acceptEdits', text)
                self.assertIn(str(self.prefix), text)
        for path, text in outputs.items():
            path.write_text(text)
        self.assertEqual(configure_claude.render(self.root, self.prefix), outputs)

    def test_backups_idempotency_and_symlinks(self):
        target = self.root/"settings.json"
        target.write_text('old')
        first = write_config(target, 'new', self.root/"backups")
        self.assertEqual(Path(first['backup']).read_text(), 'old')
        self.assertFalse(write_config(target, 'new', self.root/"backups")['changed'])
        alias = self.root/"alias"
        alias.symlink_to(target)
        with self.assertRaises(SetupError):
            write_config(alias, 'bad', self.root/"backups")
        self.assertEqual(target.read_text(), 'new')

    def test_explicit_invalid_executable_does_not_fall_back(self):
        with self.assertRaisesRegex(SetupError, "Invalid executable"):
            detect.discover("python", str(self.root/"missing"))

    def test_external_environment_is_never_modified(self):
        self.prefix.mkdir(parents=True)
        with mock.patch.object(environment, 'run') as run:
            with self.assertRaisesRegex(SetupError, "not setup-managed"):
                environment.install(self.prefix, "venv", "python", self.manifest)
        run.assert_not_called()

    def test_venv_install_is_argument_safe_and_resumable(self):
        def command(argv, **kwargs):
            if "venv" in argv:
                (self.prefix/'bin').mkdir(parents=True, exist_ok=True)
                (self.prefix/'bin/python').touch()
            return mock.Mock(stdout='mcp-biomodelling-servers==2.3.0\n')
        with mock.patch.object(environment, 'run', side_effect=command) as run:
            environment.install(self.prefix, "venv", "python", self.manifest)
            self.assertIn(str(self.prefix), run.call_args_list[0].args[0])
            calls = run.call_count
            environment.install(self.prefix, "venv", "python", self.manifest)
            self.assertEqual(run.call_count, calls)
        self.assertTrue((self.prefix/'resolved-requirements.txt').is_file())

    def test_dry_run_creates_no_files_and_missing_requirements_are_aggregated(self):
        args = setup.parser().parse_args(['--client', 'both', '--dry-run', '--non-interactive'])
        with mock.patch.object(detect, 'discover', return_value=None):
            report = setup.execute(args, self.root)
        self.assertFalse(report['passed'])
        self.assertGreaterEqual(len(report['errors']), 3)
        self.assertFalse((self.root/'.setup').exists())

    def test_successful_plan_never_installs_or_writes(self):
        args = setup.parser().parse_args(['--client', 'codex', '--manager', 'venv', '--dry-run',
                                        '--codex-home', str(self.home)])
        with mock.patch.object(detect, 'discover', return_value='/tools/executable'), \
             mock.patch.object(detect, 'client_version', return_value='0.153.0'), \
             mock.patch.object(environment, 'install') as install:
            report = setup.execute(args, self.root)
        self.assertTrue(report['passed'])
        self.assertEqual(len(report['configuration_files']), 4)
        self.assertFalse(self.home.exists())
        install.assert_not_called()

    def test_check_does_not_repair_missing_configurations(self):
        args = setup.parser().parse_args(['--client', 'claude', '--manager', 'venv', '--check'])
        with mock.patch.object(detect, 'discover', return_value='/tools/executable'), \
             mock.patch.object(detect, 'client_version', return_value='2.0.0'), \
             mock.patch.object(environment, 'verify_environment', return_value={'passed':True}), \
             mock.patch.object(setup, 'write_config') as write:
            report = setup.execute(args, self.root)
        self.assertFalse(report['passed'])
        self.assertTrue(any('stale' in error for error in report['errors']))
        write.assert_not_called()

    def test_unknown_input_keys_fail(self):
        file = self.root/'input.json'
        file.write_text('{"typo": "value"}')
        args = setup.parser().parse_args(['--config', str(file)])
        with self.assertRaisesRegex(SetupError, "Unknown"):
            setup.settings(args, self.root)

    def test_codex_home_is_respected_by_launcher(self):
        from scripts.codex.launcher_config import profile_path
        with mock.patch.dict(os.environ, {'CODEX_HOME':str(self.home)}):
            self.assertEqual(profile_path('example'), self.home/'example.config.toml')

    def test_failed_install_does_not_change_client_configuration(self):
        path = self.root/'.claude/agents/network-curator.md'
        before = path.read_bytes()
        args = setup.parser().parse_args(['--client', 'claude', '--manager', 'venv'])
        with mock.patch.object(detect, 'discover', return_value='/tools/executable'), \
             mock.patch.object(detect, 'client_version', return_value='2.0.0'), \
             mock.patch.object(environment, 'install', side_effect=SetupError('installation failed')):
            with self.assertRaisesRegex(SetupError, 'installation failed'):
                setup.execute(args, self.root)
        self.assertEqual(path.read_bytes(), before)

    def test_successful_setup_saves_paths_hashes_and_report(self):
        args = setup.parser().parse_args(['--client', 'claude', '--manager', 'venv'])
        with mock.patch.object(detect, 'discover', return_value='/tools/executable'), \
             mock.patch.object(detect, 'client_version', return_value='2.0.0'), \
             mock.patch.object(environment, 'install'), \
             mock.patch.object(environment, 'verify_environment', return_value={'passed': True}), \
             mock.patch.object(setup.verify, 'verify', return_value={'passed': True, 'errors': []}):
            report = setup.execute(args, self.root)
        self.assertTrue(report['passed'])
        self.assertEqual(len(report['writes']), 4)
        self.assertTrue(all(entry['backup'] for entry in report['writes']))
        saved = json.loads((self.root/'.setup/local.json').read_text())
        self.assertEqual(saved['claude_path'], '/tools/executable')
        self.assertTrue((self.root/'.setup/generated-files.json').is_file())
        self.assertTrue((self.root/'.setup/report.json').is_file())

    def test_setup_override_paths_are_used_by_launcher(self):
        from scripts.codex import launcher_config
        state = self.root/'.setup/local.json'
        state.parent.mkdir()
        exe = self.root/'codex'
        exe.write_text('fixture')
        state.write_text(json.dumps({'codex_path': str(exe), 'codex_home': str(self.home)}))
        with mock.patch.object(launcher_config, 'PROJECT_ROOT', self.root):
            self.assertEqual(launcher_config.resolve_codex_executable(None), str(exe))

    def test_install_failure_can_resume_using_owned_prefix(self):
        with mock.patch.object(environment, 'run', side_effect=SetupError('failed')):
            with self.assertRaises(SetupError):
                environment.install(self.prefix, 'conda', 'conda', self.manifest)
        marker = self.prefix.parent/('.' + self.prefix.name + '.biomodelling-setup.json')
        self.assertTrue(marker.is_file())
        self.assertFalse((self.prefix/'.setup-installed').exists())

    def test_mcp_probe_only_lists_tools(self):
        source = (ROOT/'scripts/setup_support/probe_mcp.py').read_text()
        self.assertNotIn('session.call_tool(', source)
        self.assertIn('session.initialize()', source)
        self.assertIn('session.list_tools(', source)

    def test_missing_explicit_configuration_is_an_error(self):
        args = setup.parser().parse_args(['--config', str(self.root/'absent.json')])
        with self.assertRaisesRegex(SetupError, 'missing'):
            setup.settings(args, self.root)

    def test_diagnostic_timeout_stops_a_process(self):
        with self.assertRaisesRegex(SetupError, 'TimeoutExpired'):
            detect.run([sys.executable, '-c', 'import time; time.sleep(30)'], timeout=0.05)

    def test_failed_command_diagnostics_redact_credentials(self):
        with self.assertRaises(SetupError) as raised:
            detect.run([sys.executable, '-c',
                        'import sys; print("TOKEN=do-not-expose", file=sys.stderr); sys.exit(1)'])
        self.assertNotIn('do-not-expose', str(raised.exception))
        self.assertIn('REDACTED', str(raised.exception))

    def test_conda_installs_native_dependencies_in_the_selected_prefix(self):
        def command(argv, **kwargs):
            if 'create' in argv:
                (self.prefix/'bin').mkdir(parents=True)
                (self.prefix/'bin/python').touch()
            return mock.Mock(stdout='mcp-biomodelling-servers==2.3.0\n')
        with mock.patch.object(environment, 'run', side_effect=command) as run:
            environment.install(self.prefix, 'conda', '/tools/conda', self.manifest)
        first = run.call_args_list[0].args[0]
        self.assertIn('graphviz', first)
        self.assertIn('conda-forge', first)
        self.assertIn(str(self.prefix), first)

    def test_changing_manager_does_not_reuse_the_old_manager_executable(self):
        state = self.root/'.setup/local.json'
        state.parent.mkdir()
        state.write_text(json.dumps({'manager': 'conda', 'manager_path': '/old/conda'}))
        args = setup.parser().parse_args(['--manager', 'venv'])
        self.assertNotIn('manager_path', setup.settings(args, self.root))


if __name__ == '__main__':
    unittest.main()
