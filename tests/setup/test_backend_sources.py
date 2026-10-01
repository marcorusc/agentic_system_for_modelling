"""Pinned source setup tests: temporary Git repos and fake package installation."""
from contextlib import ExitStack
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest import mock

from scripts import setup
from scripts.setup_support import backend_sources as sources, environment
from scripts.setup_support import inspect_backend_install
from scripts.setup_support.state import SetupError


class BackendSourcesTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.manifest = {"package": "mcp-biomodelling-servers", "version": "2.4.0", "index_url": "https://pypi.org/simple", "dependency_pins": {"nekomata": "1.10.1"}}
        self.entries = []
        for name, version in (("nekomata", "1.10.1"), ("mcp-biomodelling-servers", "2.4.0")):
            repo = self.root / name
            repo.mkdir()
            metadata = '[tool.poetry]' if name == 'nekomata' else '[project]'
            (repo / 'pyproject.toml').write_text(f'{metadata}\nname="{name}"\nversion="{version}"\n')
            (repo / '.gitignore').write_text('ignored.py\n')
            self.git(repo, 'init', '-q')
            self.git(repo, 'add', '.')
            self.git(repo, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture')
            self.entries.append({'name': name, 'version': version, 'path': str(repo), 'commit': self.git(repo, 'rev-parse', 'HEAD').strip()})
        self.entries.sort(key=lambda e: e['name'])
        self.lock = self.root / 'sources.json'
        self.write_lock()
        self.prefix = self.root / 'environment'

    def git(self, repo, *args):
        return subprocess.check_output(['git', '-C', str(repo), *args], text=True)

    def write_lock(self):
        self.lock.write_text(json.dumps({'schema_version': 1, 'packages': self.entries}))

    def test_exact_sources_and_relative_paths(self):
        relative = [{**e, 'path': Path(e['path']).name} for e in self.entries]
        self.lock.write_text(json.dumps({'schema_version': 1, 'packages': relative}))
        self.assertEqual(sources.load(self.lock, self.manifest), self.entries)

    def test_wrong_revision_dirty_and_untracked_sources_fail(self):
        repo = Path(self.entries[0]['path'])
        for kind in ('revision', 'tracked', 'untracked'):
            with self.subTest(kind=kind):
                entries = [dict(e) for e in self.entries]
                if kind == 'revision': entries[0]['commit'] = '0' * 40
                elif kind == 'tracked': (repo / 'pyproject.toml').write_text('changed')
                else: (repo / 'new.py').write_text('uncommitted')
                with self.assertRaises(SetupError): sources.validate_sources(entries)
                if kind == 'tracked':
                    (repo / 'pyproject.toml').write_text(self.git(repo, 'show', 'HEAD:pyproject.toml'))
                if kind == 'untracked': (repo / 'new.py').unlink()

    def test_manifest_rejects_duplicate_missing_and_nonexact_pins(self):
        invalid = [self.entries[:1], [self.entries[0], self.entries[0]],
                   [{**self.entries[0], 'commit': 'main'}, self.entries[1]],
                   [{**self.entries[0], 'version': 'wrong'}, self.entries[1]]]
        for entries in invalid:
            self.lock.write_text(json.dumps({'schema_version': 1, 'packages': entries}))
            with self.subTest(entries=entries), self.assertRaises(SetupError): sources.load(self.lock, self.manifest)

    def test_stale_neko_source_rejected_before_install(self):
        entries = [{**entry, 'version': '1.10.0'} if entry['name'] == 'nekomata'
                   else entry for entry in self.entries]
        self.lock.write_text(json.dumps({'schema_version': 1, 'packages': entries}))
        with self.assertRaisesRegex(SetupError, 'nekomata version must match'):
            sources.load(self.lock, self.manifest)
        with mock.patch.object(environment, 'run') as run:
            with self.assertRaisesRegex(SetupError, 'nekomata version must match'):
                environment.install(self.prefix, 'venv', 'python', self.manifest, backend_sources=entries)
        run.assert_not_called()
        self.assertFalse(self.prefix.exists())

    def test_snapshot_contains_only_committed_content_and_cleans_up(self):
        for entry in self.entries: (Path(entry['path']) / 'ignored.py').write_text('not a build input')
        with sources.snapshots(self.entries) as paths:
            for entry in self.entries:
                path = paths[entry['name']]
                self.assertEqual((path / 'pyproject.toml').read_bytes(), (Path(entry['path']) / 'pyproject.toml').read_bytes())
                self.assertFalse((path / 'ignored.py').exists())
                self.assertFalse((path / '.git').exists())
        self.assertFalse(path.exists())

    def test_archive_rejects_links_and_traversal(self):
        for number, name in enumerate(('../escape', '/absolute', 'link')):
            archive = self.root / f'{number}.tar'
            with tarfile.open(archive, 'w') as stream:
                member = tarfile.TarInfo(name)
                if name == 'link': member.type, member.linkname = tarfile.SYMTYPE, '/etc/passwd'
                else: member.size = 1
                stream.addfile(member, io.BytesIO(b'x'))
            with self.assertRaisesRegex(SetupError, 'unsafe'): sources.unpack(archive, self.root / f'unpack{number}')

    def installed(self, paths):
        return {e['name']: {'version': e['version'], 'direct_url': {'url': paths[e['name']].as_uri(), 'dir_info': {}},
                           'files': {'lib/backend.py': 'a' * 64}} for e in self.entries}

    def test_receipt_checks_origin_revision_and_installed_bytes(self):
        with sources.snapshots(self.entries) as paths:
            installed = self.installed(paths)
            with mock.patch.object(sources, 'inspect_installed', return_value=installed):
                sources.write_receipt(self.prefix, self.entries, paths)
                self.assertTrue(sources.verify_receipt(self.prefix, self.entries)['passed'])
                changed = [{**self.entries[0], 'commit': 'a' * 40}, self.entries[1]]
                self.assertFalse(sources.verify_receipt(self.prefix, changed)['passed'])
                installed[self.entries[0]['name']]['files']['lib/backend.py'] = 'b' * 64
                self.assertFalse(sources.verify_receipt(self.prefix, self.entries)['passed'])

    def test_wrong_origin_or_editable_install_cannot_create_receipt(self):
        with sources.snapshots(self.entries) as paths:
            for field, value in (('url', 'https://example.invalid/backend'), ('dir_info', {'editable': True})):
                installed = self.installed(paths)
                installed[self.entries[0]['name']]['direct_url'][field] = value
                with mock.patch.object(sources, 'inspect_installed', return_value=installed), self.assertRaises(SetupError):
                    sources.write_receipt(self.prefix, self.entries, paths)
                self.assertFalse((self.prefix / sources.RECEIPT).exists())

    def test_both_backends_installed_together_from_snapshots_and_reused(self):
        def run(argv, **kwargs):
            if 'venv' in argv:
                (self.prefix / 'bin').mkdir(parents=True)
                (self.prefix / 'bin/python').touch()
            if 'install' in argv:
                self.assertIn('nekomata==1.10.1', argv)
                selected = [Path(p) for p in argv[-2:]]
                self.assertEqual({p.name for p in selected}, sources.NAMES)
                self.assertTrue(all((p/'pyproject.toml').is_file() for p in selected))
                self.assertFalse(any(str(p) in {e['path'] for e in self.entries} for p in selected))
            return mock.Mock(stdout='fixture freeze\n')
        with mock.patch.object(environment, 'run', side_effect=run) as commands, mock.patch.object(sources, 'write_receipt') as receipt:
            environment.install(self.prefix, 'venv', 'python', self.manifest, backend_sources=self.entries)
            count = commands.call_count
            environment.install(self.prefix, 'venv', 'python', self.manifest, backend_sources=self.entries)
            self.assertEqual(commands.call_count, count)
            receipt.assert_called_once()
        self.assertTrue((self.prefix / '.setup-installed').exists())

    def test_check_and_reuse_verify_before_writes(self):
        for flag in ('--check', '--environment-mode'):
            args = setup.parser().parse_args([flag] if flag == '--check' else [flag, 'reuse'])
            resolved = {'client': 'both', 'clients': {'codex':'codex','claude':'claude'}, 'env_prefix': str(self.prefix),
                        'manager':'venv', 'manager_path':'python', 'biomass':'disabled', 'graphviz_path':None,
                        'codex_home':str(self.root/'codex'), 'environment_mode':'reuse', 'pinned_sources':self.entries}
            (self.root/'setup').mkdir(exist_ok=True)
            (self.root/'setup/dependencies.toml').write_text('package="mcp-biomodelling-servers"\nversion="2.4.0"\n')
            with ExitStack() as stack:
                stack.enter_context(mock.patch.object(setup, 'plan', return_value=(resolved, [])))
                for module in (setup.configure_codex, setup.configure_claude): stack.enter_context(mock.patch.object(module,'render',return_value={}))
                install = stack.enter_context(mock.patch.object(environment, 'install'))
                stack.enter_context(mock.patch.object(environment, 'verify_environment', return_value={'passed': True}))
                stack.enter_context(mock.patch.object(sources, 'verify_receipt', return_value={'passed':False,'errors':['drift']}))
                write = stack.enter_context(mock.patch.object(setup, 'write_config'))
                report = setup.execute(args, self.root)
                self.assertFalse(report['passed']); self.assertIn('drift', report['errors'])
                install.assert_not_called(); write.assert_not_called()

    def test_distribution_inspection_reads_bytes_without_imports(self):
        package = self.root / 'lib/backend.py';package.parent.mkdir();package.write_text('raise RuntimeError("must not import")')
        dist = mock.Mock(files=['lib/backend.py'],version='1')
        dist.locate_file.side_effect = lambda entry: self.root/entry
        dist.read_text.return_value='{}'
        with mock.patch.object(inspect_backend_install.sys,'prefix',str(self.root)), mock.patch.object(inspect_backend_install.metadata,'distribution',return_value=dist):
            original=inspect_backend_install.inspect()
            package.write_text('changed')
            self.assertNotEqual(inspect_backend_install.inspect(),original)
            package.unlink();package.symlink_to(self.lock)
            with self.assertRaises(ValueError): inspect_backend_install.inspect()


if __name__ == '__main__': unittest.main()
