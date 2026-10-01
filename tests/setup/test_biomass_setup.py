from __future__ import annotations
import hashlib
import json
import os
import shutil
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from scripts import setup
from scripts.setup_support import configure_codex, configure_claude, detect, environment, verify

ROOT = Path(__file__).resolve().parents[2]


class BioMASSSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/'project'; self.root.mkdir()
        for name in ('setup', '.codex', '.codex-plugin', '.claude/agents'):
            shutil.copytree(ROOT/name, self.root/name)
        self.prefix = Path(self.temp.name)/'existing-environment'; self.prefix.mkdir()
        (self.prefix/'untouched.txt').write_text('external environment')

    def test_reuse_does_not_install_or_own_environment_and_is_idempotent(self):
        args = setup.parser().parse_args(['--client', 'claude', '--environment-mode', 'reuse',
                                          '--env-prefix', str(self.prefix), '--with-biomass'])
        with mock.patch.object(detect, 'discover', return_value='/tools/executable'), \
             mock.patch.object(detect, 'client_version', return_value='2.0.0'), \
             mock.patch.object(environment, 'install') as install, \
             mock.patch.object(environment, 'verify_environment', return_value={'passed': True}), \
             mock.patch.object(verify, 'probe_servers', return_value={'passed': True}), \
             mock.patch.object(verify, 'verify', return_value={'passed': True, 'errors': []}):
            first = setup.execute(args, self.root)
            contents = {p: p.read_bytes() for p in (self.root/'.claude/agents').iterdir()}
            second = setup.execute(args, self.root)
            self.assertTrue(first['passed']); self.assertTrue(second['passed'])
            install.assert_not_called()
            self.assertEqual(contents, {p: p.read_bytes() for p in contents})
        self.assertEqual([p.name for p in self.prefix.iterdir()], ['untouched.txt'])
        self.assertFalse((self.prefix.parent/('.'+self.prefix.name+'.biomodelling-setup.json')).exists())

    def test_generated_transport_paths_survive_a_new_ide_session(self):
        home = Path(self.temp.name)/'codex'
        with mock.patch.dict(os.environ, {'PATH': '/tmp/codex-session-one:/usr/bin'}):
            codex = configure_codex.render(self.root, self.prefix, home, with_biomass=True)
            claude = configure_claude.render(self.root, self.prefix, with_biomass=True)
        with mock.patch.dict(os.environ, {'PATH': '/tmp/different-ide-session:/bin'}):
            self.assertEqual(codex, configure_codex.render(self.root, self.prefix, home, with_biomass=True))
            self.assertEqual(claude, configure_claude.render(self.root, self.prefix, with_biomass=True))

    def test_ode_profile_is_optional_and_excludes_every_other_server(self):
        home = Path(self.temp.name)/'codex'
        self.assertEqual(len(configure_codex.render(self.root, self.prefix, home)), 4)
        outputs = configure_codex.render(self.root, self.prefix, home, with_biomass=True)
        self.assertEqual(len(outputs), 5)
        ode = tomllib.loads(outputs[home/'biomodel-ode-modeler.config.toml'])
        self.assertEqual({name for name, c in ode['mcp_servers'].items() if c.get('enabled', True)}, {'biomass'})
        self.assertIn('close_session', ode['mcp_servers']['biomass']['disabled_tools'])
        claude = configure_claude.render(self.root, self.prefix, with_biomass=True)
        self.assertEqual(len(claude), 5)
        ode_agent = claude[self.root/'.claude/agents/ode-modeler.md']
        self.assertIn('command: ' + json.dumps(str(self.prefix/'bin/mcp-biomass-server')), ode_agent)
        self.assertIn('CONDA_PREFIX: ' + json.dumps(str(self.prefix)), ode_agent)
        self.assertIn('PATH: ' + json.dumps(environment.transport_path(self.prefix)), ode_agent)
        self.assertNotIn('__configure_biomass_', ode_agent)

    def test_real_pinned_legacy_profile_migrates_only_known_export_rule(self):
        # Exact source profile from 1e8f9a43c4fc249e43d94c71316fc798ee7ad01d.
        # Keep this fixture static so installed/released trees need no Git history.
        source = (ROOT/'tests/setup/fixtures/legacy-ode-modeler.config.toml').read_bytes()
        self.assertEqual(hashlib.sha256(source).hexdigest(),
                         '52d75b8c05bcb40d7fe0b919773e2aaba50fc1599e5501e8993238ad3fe640ad')
        original = tomllib.loads(source.decode())
        home = Path(self.temp.name)/'codex'; home.mkdir()
        target = home/'biomodel-ode-modeler.config.toml'; target.write_bytes(source)
        outputs = configure_codex.render(self.root, self.prefix, home, with_biomass=True)
        migrated = tomllib.loads(outputs[target])
        expected = original['developer_instructions'].replace(
            configure_codex.LEGACY_ODE_EXPORT_RULE, configure_codex.ODE_EXPORT_RULE)
        expected += '\n' + configure_codex.ODE_PROFILE_GUIDANCE['ode_modeler']
        self.assertEqual(migrated['developer_instructions'], expected)
        self.assertNotIn(configure_codex.LEGACY_ODE_EXPORT_RULE, expected)
        self.assertEqual(target.read_bytes(), source)  # Rendering cannot install profiles.
        self.assertEqual(migrated['sandbox_mode'], original['sandbox_mode'])
        self.assertEqual(migrated['approval_policy'], original['approval_policy'])
        self.assertFalse(migrated['features']['apps'])
        self.assertFalse(migrated['mcp_servers']['specialist_dispatcher']['enabled'])
        self.assertEqual({key for key, value in migrated['mcp_servers'].items()
                          if value.get('enabled', True)}, {'biomass'})
        for path, content in outputs.items():
            path.write_text(content)
        self.assertEqual(configure_codex.render(self.root, self.prefix, home, with_biomass=True), outputs)

    def test_new_profiles_are_idempotent_and_scope_modes_and_parent_capture(self):
        home = Path(self.temp.name)/'codex'; home.mkdir()
        base = configure_codex.render(self.root, self.prefix, home)
        outputs = configure_codex.render(self.root, self.prefix, home, with_biomass=True)
        for path, content in outputs.items():
            path.write_text(content)
        self.assertEqual(configure_codex.render(self.root, self.prefix, home, with_biomass=True), outputs)
        for role in ('network_curator', 'boolean_dynamics_modeler', 'multicellular_configurator'):
            profile, _ = configure_codex.SPECIALISTS[role]
            target = home/(profile + '.config.toml')
            self.assertEqual(outputs[target], base[target])
        for role in ('literature_reviewer', 'ode_modeler'):
            profile, _ = configure_codex.SPECIALISTS[role]
            instructions = tomllib.loads(outputs[home/(profile + '.config.toml')])['developer_instructions']
            self.assertEqual(instructions.count(configure_codex.ODE_PROFILE_GUIDANCE[role]), 1)
        ode = tomllib.loads(outputs[home/'biomodel-ode-modeler.config.toml'])['developer_instructions']
        for required in ('metadata-only needs_approval', 'ode.export_status=pending',
                         'artifacts=[]', 'simulation_paths=[]', 'separate validated provisional',
                         'do not force a bootstrap return', 'Preserve the original specialist result'):
            self.assertIn(required, ode)
        literature = tomllib.loads(outputs[home/'biomodel-literature-reviewer.config.toml'])['developer_instructions']
        self.assertIn('review_kind=edge (default) preserves existing edge-review rules', literature)
        self.assertIn('Only when the invocation explicitly sets review_kind=ode', literature)
        self.assertIn('instead of edge-specific input, report and lineage requirements', literature)

    def test_legacy_migration_preserves_custom_settings_and_instructions(self):
        payload = tomllib.loads((ROOT/'tests/setup/fixtures/legacy-ode-modeler.config.toml').read_text())
        custom_policy = '\nResearcher policy: keep the existing receptor mapping and report uncertainty.'
        payload['developer_instructions'] += custom_policy
        payload['model_reasoning_effort'] = 'high'
        payload['custom_setting'] = {'keep': ['one', 'two'], 'enabled': False}
        payload['mcp_servers']['biomass']['env'] = {'CUSTOM_BIOMASS_SETTING': 'retained'}
        payload['mcp_servers']['biomass']['disabled_tools'].append('run_simulation')
        home = Path(self.temp.name)/'codex'; home.mkdir()
        target = home/'biomodel-ode-modeler.config.toml'
        original = '\n'.join(f'{configure_codex.toml_literal(k)}={configure_codex.toml_literal(v)}'
                             for k, v in payload.items())
        target.write_text(original)
        outputs = configure_codex.render(self.root, self.prefix, home, with_biomass=True)
        migrated = tomllib.loads(outputs[target])
        self.assertIn(custom_policy, migrated['developer_instructions'])
        self.assertEqual(migrated['custom_setting'], payload['custom_setting'])
        self.assertEqual(migrated['model_reasoning_effort'], 'high')
        self.assertEqual(migrated['mcp_servers']['biomass']['env']['CUSTOM_BIOMASS_SETTING'], 'retained')
        self.assertIn('run_simulation', migrated['mcp_servers']['biomass']['disabled_tools'])
        self.assertEqual(target.read_text(), original)

    def test_unfamiliar_export_restrictions_fail_without_overwriting_profile(self):
        from scripts.setup_support.state import SetupError
        home = Path(self.temp.name)/'codex'; home.mkdir()
        target = home/'biomodel-ode-modeler.config.toml'
        source = (ROOT/'tests/setup/fixtures/legacy-ode-modeler.config.toml').read_text()
        for restriction in (
            configure_codex.LEGACY_ODE_EXPORT_RULE.replace('call only', 'call only ever'),
            'Export_model_bundle may only be called after final approval.',
            'Never preserve provisional candidates.',
        ):
            with self.subTest(restriction=restriction):
                original = source.replace(configure_codex.LEGACY_ODE_EXPORT_RULE, restriction)
                target.write_text(original)
                with self.assertRaisesRegex(SetupError, 'Unrecognized ODE export restriction.*biomodel-ode-modeler'):
                    configure_codex.render(self.root, self.prefix, home, with_biomass=True)
                self.assertEqual(target.read_text(), original)

    def test_previous_setup_owned_guidance_is_updated_without_duplicate_directives(self):
        home = Path(self.temp.name)/'codex'; home.mkdir()
        for role in ('literature_reviewer', 'ode_modeler'):
            profile, _ = configure_codex.SPECIALISTS[role]
            source = self.root/'.codex/profiles'/(profile + '.config.toml.example')
            payload = tomllib.loads(source.read_text())
            payload['developer_instructions'] = ('Keep my custom policy.\n' +
                configure_codex._PREVIOUS_ODE_PROFILE_GUIDANCE[role])
            target = home/(profile + '.config.toml')
            target.write_text('\n'.join(f'{configure_codex.toml_literal(k)}={configure_codex.toml_literal(v)}'
                                         for k, v in payload.items()))
        outputs = configure_codex.render(self.root, self.prefix, home, with_biomass=True)
        for role in ('literature_reviewer', 'ode_modeler'):
            profile, _ = configure_codex.SPECIALISTS[role]
            instructions = tomllib.loads(outputs[home/(profile + '.config.toml')])['developer_instructions']
            self.assertEqual(instructions, 'Keep my custom policy.\n' + configure_codex.ODE_PROFILE_GUIDANCE[role])

    def test_missing_capabilities_prevent_configuration_changes(self):
        args = setup.parser().parse_args(['--client', 'claude', '--environment-mode', 'reuse', '--with-biomass'])
        with mock.patch.object(detect, 'discover', return_value='/tools/executable'), \
             mock.patch.object(detect, 'client_version', return_value='2.0.0'), \
             mock.patch.object(environment, 'verify_environment', return_value={'passed': True}), \
             mock.patch.object(verify, 'probe_servers', return_value={'passed': False, 'errors': ['missing build_reactions']}), \
             mock.patch.object(setup, 'write_config') as write:
            result = setup.execute(args, self.root)
            self.assertFalse(result['passed']); write.assert_not_called()

    def test_capability_checks_allow_shared_simulation_name_and_require_ode_exporter(self):
        def probe(argv, **kwargs):
            server = Path(argv[-1]).name.removeprefix('mcp-').removesuffix('-server')
            tools = verify.SIGNATURES[server] | ({'export_biomass_handoff'} if server == 'neko' else set())
            return mock.Mock(stdout=json.dumps({'tools': list(tools)}))
        with mock.patch.object(verify, 'run', side_effect=probe):
            self.assertTrue(verify.probe_servers(self.prefix, with_biomass=True)['passed'])
        def missing(argv, **kwargs):
            result = probe(argv, **kwargs)
            result.stdout = result.stdout.replace('export_biomass_handoff', 'old_export')
            return result
        with mock.patch.object(verify, 'run', side_effect=missing):
            self.assertFalse(verify.probe_servers(self.prefix, with_biomass=True)['passed'])


if __name__ == '__main__': unittest.main()
