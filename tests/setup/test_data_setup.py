from __future__ import annotations
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import setup
from scripts.data import environment as data_env
from scripts.setup_support import detect, environment, verify

ROOT = Path(__file__).resolve().parents[2]
IMPORT_PROBE = "import pydeseq2, gseapy, anndata, decoupler, sklearn, statsmodels, pint, uncertainties, gget, seaborn, matplotlib"


class DataSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/'project'; self.root.mkdir()
        (self.root/'setup').mkdir()
        for name in ('data-requirements.txt', 'data-requirements.lock', 'data-requirements-cellprofiler.txt'):
            shutil.copy(ROOT/'setup'/name, self.root/'setup'/name)

    def test_parser_accepts_data_flags(self):
        args = setup.parser().parse_args(['--with-data'])
        self.assertTrue(args.with_data); self.assertFalse(args.with_cellprofiler)
        self.assertFalse(setup.parser().parse_args([]).with_data)

    def test_cellprofiler_implies_data(self):
        args = setup.parser().parse_args(['--with-cellprofiler'])
        self.assertTrue(args.with_cellprofiler); self.assertTrue(args.with_data)

    def test_ensure_runs_expected_commands(self):
        with mock.patch('subprocess.run') as run:
            result = data_env.ensure(self.root, '/bin/uv', check=False, with_cellprofiler=False)
        py = str(self.root/'.venv-data/bin/python')
        self.assertEqual([c.args[0] for c in run.call_args_list], [
            ['/bin/uv', 'venv', str(self.root/'.venv-data'), '--python', '3.12'],
            ['/bin/uv', 'pip', 'sync', '--python', py, str(self.root/'setup/data-requirements.lock')],
            [py, '-E', '-s', '-c', IMPORT_PROBE]])
        self.assertTrue(all(c.kwargs.get('check') for c in run.call_args_list))
        self.assertTrue(result['passed']); self.assertEqual(result['lock_sha256'], data_env.lock_sha256(self.root))
        self.assertEqual(data_env.data_python(self.root), self.root/'.venv-data/bin/python')

    def test_cellprofiler_uses_python_from_requirements_comment(self):
        with mock.patch('subprocess.run') as run:
            result = data_env.ensure(self.root, '/bin/uv', check=False, with_cellprofiler=True)
        cp = self.root/'.venv-cellprofiler'
        argv = [c.args[0] for c in run.call_args_list][3:]
        self.assertEqual(argv, [
            ['/bin/uv', 'venv', str(cp), '--python', '3.9'],
            ['/bin/uv', 'pip', 'install', '--python', str(cp/'bin/python'), '-r',
             str(self.root/'setup/data-requirements-cellprofiler.txt')],
            [str(cp/'bin/cellprofiler'), '--version']])
        self.assertTrue(result['passed'])

    def _touch(self, env):
        python = self.root/env/'bin/python'; python.parent.mkdir(parents=True); python.touch()

    def test_existing_env_skips_venv_creation(self):
        self._touch('.venv-data')
        with mock.patch('subprocess.run') as run:
            result = data_env.ensure(self.root, '/bin/uv', check=False, with_cellprofiler=False)
        py = str(self.root/'.venv-data/bin/python')
        self.assertEqual([c.args[0] for c in run.call_args_list], [
            ['/bin/uv', 'pip', 'sync', '--python', py, str(self.root/'setup/data-requirements.lock')],
            [py, '-E', '-s', '-c', IMPORT_PROBE]])
        self.assertTrue(result['passed'])

    def test_existing_cellprofiler_env_skips_venv_creation(self):
        self._touch('.venv-data'); self._touch('.venv-cellprofiler')
        with mock.patch('subprocess.run') as run:
            data_env.ensure(self.root, '/bin/uv', check=False, with_cellprofiler=True)
        cp = self.root/'.venv-cellprofiler'
        argv = [c.args[0] for c in run.call_args_list]
        self.assertFalse(any(a[1:2] == ['venv'] for a in argv))
        self.assertEqual(argv[-2:], [
            ['/bin/uv', 'pip', 'install', '--python', str(cp/'bin/python'), '-r',
             str(self.root/'setup/data-requirements-cellprofiler.txt')],
            [str(cp/'bin/cellprofiler'), '--version']])

    def test_check_mode_runs_no_install(self):
        with mock.patch('subprocess.run') as run:
            result = data_env.ensure(self.root, '/bin/uv', check=True, with_cellprofiler=False)
        self.assertEqual([c.args[0][1:] for c in run.call_args_list], [['-E', '-s', '-c', IMPORT_PROBE]])
        self.assertTrue(result['passed'])

    def test_failed_command_is_reported(self):
        import subprocess
        with mock.patch('subprocess.run', side_effect=subprocess.CalledProcessError(1, ['uv'])):
            result = data_env.ensure(self.root, '/bin/uv', check=False, with_cellprofiler=False)
        self.assertFalse(result['passed']); self.assertTrue(result['errors'])

    def _execute(self, uv_path, which):
        args = setup.parser().parse_args(['--client', 'claude', '--environment-mode', 'reuse',
                                          '--env-prefix', self.temp.name, '--with-data'])
        for name in ('.codex', '.codex-plugin', '.claude/agents', '.claude/skills'):
            if not (self.root/name).exists():
                shutil.copytree(ROOT/name, self.root/name)
        shutil.copy(ROOT/'setup/dependencies.toml', self.root/'setup/dependencies.toml')
        with mock.patch.object(detect, 'discover', return_value='/tools/executable'), \
             mock.patch.object(detect, 'client_version', return_value='2.0.0'), \
             mock.patch.object(environment, 'verify_environment', return_value={'passed': True}), \
             mock.patch.object(verify, 'verify', return_value={'passed': True, 'errors': []}), \
             mock.patch('shutil.which', return_value=which), \
             mock.patch.object(data_env, 'ensure') as ensure:
            ensure.return_value = {'passed': True, 'errors': [], 'python': None, 'lock_sha256': 'x', 'cellprofiler': None}
            if uv_path:
                args.uv_path = uv_path
            return setup.execute(args, self.root), ensure

    def test_missing_uv_is_error(self):
        report, ensure = self._execute(None, None)
        self.assertFalse(report['passed'])
        self.assertTrue(any('uv is required for --with-data' in e for e in report['errors']))
        ensure.assert_not_called()

    def test_uv_from_which_is_used(self):
        report, ensure = self._execute(None, '/usr/bin/uv')
        self.assertTrue(report['passed'], report['errors'])
        self.assertEqual(ensure.call_args.args[1], '/usr/bin/uv')
        self.assertIn('data_environment', report)

    def test_gitignore_has_data_dirs(self):
        lines = (ROOT/'.gitignore').read_text().splitlines()
        for entry in ('.venv-data/', '.venv-cellprofiler/', 'data-cache/'):
            self.assertIn(entry, lines)


if __name__ == '__main__':
    unittest.main()
