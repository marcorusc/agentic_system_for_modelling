from __future__ import annotations
import json
import os
import signal
import sys
import time
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

    @unittest.skipUnless(os.name == 'posix', 'POSIX process groups')
    def test_timeout_cannot_hang_on_inherited_pipe(self):
        from scripts.setup_support.state import SetupError
        pidfile = Path(self.temp.name)/'test-child.pid'
        program = ("import subprocess,sys,time; from pathlib import Path; "
                   "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(15)'],start_new_session=True); "
                   f"Path({str(pidfile)!r}).write_text(str(child.pid)); time.sleep(15)")
        start = time.monotonic()
        try:
            with self.assertRaises(SetupError):
                detect.run([sys.executable, '-c', program], timeout=0.2)
            self.assertLess(time.monotonic() - start, 5)
        finally:
            if pidfile.exists():
                try: os.kill(int(pidfile.read_text()), signal.SIGKILL)
                except ProcessLookupError: pass

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
        self.assertEqual(len(configure_claude.render(self.root, self.prefix, with_biomass=True)), 5)

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
