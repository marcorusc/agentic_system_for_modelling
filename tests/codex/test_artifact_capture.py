from __future__ import annotations

import copy
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import signal
import tempfile
import unittest
from unittest import mock

from scripts.codex import artifact_capture
from scripts.codex import record_neko_ode_handoff as neko_recorder
from scripts.codex import record_ode_artifacts as ode_recorder


def _record(kind: str, arguments: dict) -> dict:
    if kind == 'ode':
        return ode_recorder.record(**arguments)
    return neko_recorder.record_neko(**arguments)


def _worker(kind, arguments, result_queue, barrier=None, ready=None, interrupt_write=False):
    """Run a real separate recorder process at a controlled publication boundary."""
    publish = artifact_capture.publish_capture

    def synchronized_publish(stage, target):
        if barrier is not None:
            barrier.wait(timeout=15)
        publish(stage, target)

    def partial_copy(source, destination):
        destination.write(b'partial copy')
        destination.flush()
        ready.set()
        signal.pause()

    write_text = Path.write_text

    def partial_write(path, data, *args, **kwargs):
        if path.name == 'import.handoff.json':
            write_text(path, '{', *args, **kwargs)
            ready.set()
            signal.pause()
        return write_text(path, data, *args, **kwargs)

    try:
        with mock.patch.object(artifact_capture, 'publish_capture', synchronized_publish):
            if interrupt_write:
                if kind == 'ode':
                    with mock.patch.object(ode_recorder.shutil, 'copyfileobj', partial_copy):
                        result = _record(kind, arguments)
                else:
                    with mock.patch.object(Path, 'write_text', partial_write):
                        result = _record(kind, arguments)
            else:
                result = _record(kind, arguments)
        result_queue.put(('ok', result))
    except Exception as error:
        result_queue.put((type(error).__name__, str(error)))


@unittest.skipUnless(os.name == 'posix', 'capture publication uses POSIX flock')
class ArtifactCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='artifact-capture-tests-')
        self.root = Path(self.temporary.name)
        self.project = self.root / 'project'
        self.project.mkdir()
        self.ode_server = self.root / 'biomass'
        self.ode_source = self.ode_server / 'artifacts/ode-session'
        (self.ode_source / 'revisions/rev_example').mkdir(parents=True)
        self.model = self.ode_source / 'revisions/rev_example/model.txt'
        self.model.write_bytes(b'provisional model\n')
        self.snapshot = self.ode_source / 'snapshot.json'
        self.snapshot.write_bytes(b'{"status": "proposed"}\n')
        self.entries = [
            {'session_id': 'ode-session', 'path': str(path),
             'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
            for path in (self.model, self.snapshot)
        ]
        self.neko_server = self.root / 'neko'
        self.neko_source = self.neko_server / 'artifacts/neko-session'
        self.neko_source.mkdir(parents=True)
        self.network = self.neko_source / 'network.json'
        self.network.write_bytes(b'{"nodes": ["A", "B"], "edges": [["A", "+", "B"]]}\n')
        self.manifest = self.neko_source / 'export.handoff.json'
        self.original_manifest = {
            'handoff_type': 'neko-to-biomass',
            'source': {'server': 'NeKo', 'session_id': 'neko-session'},
            'network_file': {'server': 'NeKo', 'session_id': 'neko-session',
                             'role': 'neko_ode_network', 'path': str(self.network),
                             'sha256': hashlib.sha256(self.network.read_bytes()).hexdigest()},
            'annotations': ['Preserve original bytes and unrelated fields.'],
        }
        self.manifest.write_text(json.dumps(self.original_manifest, indent=1) + '\n\n', encoding='utf-8')
        self.original_bytes = {path: path.read_bytes() for path in
                               (self.model, self.snapshot, self.network, self.manifest)}

    def tearDown(self):
        self.temporary.cleanup()

    def arguments(self, kind, capture_id='capture-1'):
        if kind == 'ode':
            return dict(project=self.project, server_root=self.ode_server,
                        session_id='ode-session', capture_id=capture_id,
                        entries=self.entries)
        return dict(project=self.project, server_root=self.neko_server,
                    manifest_path=self.manifest, capture_id=capture_id)

    def target(self, kind, capture_id='capture-1'):
        base = ('runs/ode-modeler/ode-session/captures' if kind == 'ode' else
                'runs/network-curator/neko-session/ode-handoffs')
        return self.project / base / capture_id

    def assert_sources_unchanged(self):
        for path, expected in self.original_bytes.items():
            self.assertEqual(path.read_bytes(), expected)

    def assert_complete(self, kind, target):
        expected = ({'capture.json', 'snapshot.json', 'revisions/rev_example/model.txt'}
                    if kind == 'ode' else
                    {'original.handoff.json', 'network.json', 'import.handoff.json', 'relocation.json'})
        self.assertEqual({path.relative_to(target).as_posix() for path in target.rglob('*')
                          if path.is_file()}, expected)
        if kind == 'ode':
            metadata = json.loads((target / 'capture.json').read_text())
            for entry in metadata['artifacts']:
                self.assertEqual(hashlib.sha256((self.project / entry['path']).read_bytes()).hexdigest(),
                                 entry['sha256'])
        else:
            self.assertEqual((target / 'original.handoff.json').read_bytes(),
                             self.original_bytes[self.manifest])
            self.assertEqual((target / 'network.json').read_bytes(), self.original_bytes[self.network])
            imported = json.loads((target / 'import.handoff.json').read_text())
            expected_manifest = copy.deepcopy(self.original_manifest)
            expected_manifest['network_file']['path'] = str(target / 'network.json')
            self.assertEqual(imported, expected_manifest)
            relocation = json.loads((target / 'relocation.json').read_text())
            for field, name in [('original_manifest_sha256', 'original.handoff.json'),
                                ('import_manifest_sha256', 'import.handoff.json'),
                                ('network_sha256', 'network.json')]:
                self.assertEqual(relocation[field], hashlib.sha256((target / name).read_bytes()).hexdigest())

    def assert_no_capture(self, kind):
        target = self.target(kind)
        self.assertFalse(os.path.lexists(target))
        self.assertEqual(list(target.parent.glob(f'.{target.name}.staging-*')), [])
        self.assert_sources_unchanged()

    def test_complete_captures_preserve_originals_and_record_final_paths_and_hashes(self):
        for kind in ('ode', 'neko'):
            with self.subTest(kind=kind):
                result = _record(kind, self.arguments(kind))
                self.assert_complete(kind, self.target(kind))
                for entry in result['artifacts']:
                    file = self.project / entry['path']
                    self.assertTrue(file.is_relative_to(self.target(kind)))
                    self.assertEqual(hashlib.sha256(file.read_bytes()).hexdigest(), entry['sha256'])
                self.assert_sources_unchanged()

    def test_final_metadata_write_failure_leaves_no_capture_and_can_retry(self):
        write_text = Path.write_text
        for kind, filename in [('ode', 'capture.json'), ('neko', 'relocation.json')]:
            with self.subTest(kind=kind):
                def fail(path, data, *args, **kwargs):
                    if path.name == filename:
                        raise OSError('injected metadata write failure')
                    return write_text(path, data, *args, **kwargs)
                with mock.patch.object(Path, 'write_text', fail):
                    with self.assertRaisesRegex(OSError, 'injected'):
                        _record(kind, self.arguments(kind))
                self.assert_no_capture(kind)
                _record(kind, self.arguments(kind))
                self.assert_complete(kind, self.target(kind))

    def test_rename_failure_never_exposes_partial_capture(self):
        for kind in ('ode', 'neko'):
            with self.subTest(kind=kind):
                def fail(stage, target):
                    self.assertFalse(target.exists())
                    if kind == 'ode':
                        metadata = json.loads((stage / 'capture.json').read_text())
                        for entry in metadata['artifacts']:
                            staged_file = stage / (self.project / entry['path']).relative_to(target)
                            self.assertEqual(hashlib.sha256(staged_file.read_bytes()).hexdigest(), entry['sha256'])
                    else:
                        self.assertEqual(len(list(stage.iterdir())), 4)
                    raise OSError('injected rename failure')
                with mock.patch.object(artifact_capture.os, 'rename', fail):
                    with self.assertRaisesRegex(OSError, 'injected'):
                        _record(kind, self.arguments(kind))
                self.assert_no_capture(kind)

    def test_interruption_after_rename_leaves_a_complete_immutable_capture(self):
        rename = os.rename
        for kind in ('ode', 'neko'):
            with self.subTest(kind=kind):
                def interrupted(stage, target):
                    rename(stage, target)
                    raise KeyboardInterrupt('injected post-publication interruption')
                with mock.patch.object(artifact_capture.os, 'rename', interrupted):
                    with self.assertRaises(KeyboardInterrupt):
                        _record(kind, self.arguments(kind))
                self.assert_complete(kind, self.target(kind))
                with self.assertRaisesRegex(ValueError, 'already exists'):
                    _record(kind, self.arguments(kind))
                self.assert_sources_unchanged()

    def test_partial_ode_copy_and_copy_hash_mismatch_leave_no_capture(self):
        def broken(source, destination):
            destination.write(b'partial')
            raise OSError('injected copy failure')
        with mock.patch.object(ode_recorder.shutil, 'copyfileobj', broken):
            with self.assertRaisesRegex(OSError, 'injected'):
                _record('ode', self.arguments('ode'))
        self.assert_no_capture('ode')
        def corrupt(source, destination):
            destination.write(b'corrupted')
        with mock.patch.object(ode_recorder.shutil, 'copyfileobj', corrupt):
            with self.assertRaisesRegex(ValueError, 'changed while copying'):
                _record('ode', self.arguments('ode'))
        self.assert_no_capture('ode')

    def test_neko_changed_source_read_is_rejected(self):
        read_bytes = Path.read_bytes
        for file, replacement in [(self.network, b'corrupted'), (self.manifest, b'{}')]:
            with self.subTest(file=file.name):
                def changed(path):
                    return replacement if path == file else read_bytes(path)
                with mock.patch.object(Path, 'read_bytes', changed):
                    with self.assertRaisesRegex(ValueError, 'changed while copying'):
                        _record('neko', self.arguments('neko'))
                self.assert_no_capture('neko')

    def test_neko_corrupted_staged_bytes_are_rejected_before_publication(self):
        write_bytes = Path.write_bytes
        for filename in ('network.json', 'original.handoff.json'):
            with self.subTest(filename=filename):
                def corrupt(path, data):
                    if path.name == filename and '.staging-' in str(path):
                        data = b'corrupted staged bytes'
                    return write_bytes(path, data)
                with mock.patch.object(Path, 'write_bytes', corrupt):
                    with self.assertRaisesRegex(ValueError, 'changed while recording'):
                        _record('neko', self.arguments('neko'))
                self.assert_no_capture('neko')

    def test_neko_wrong_network_ownership_or_hash_is_rejected(self):
        for field, value in [('session_id', 'other-session'), ('server', 'Other'),
                             ('role', 'other-role'), ('sha256', '0' * 64),
                             ('path', str(self.model))]:
            with self.subTest(field=field):
                changed = copy.deepcopy(self.original_manifest)
                changed['network_file'][field] = value
                self.manifest.write_text(json.dumps(changed), encoding='utf-8')
                with self.assertRaises(ValueError):
                    _record('neko', self.arguments('neko'))
                self.manifest.write_bytes(self.original_bytes[self.manifest])
                self.assert_no_capture('neko')

    def test_existing_files_and_empty_directories_are_never_replaced(self):
        for kind in ('ode', 'neko'):
            for entry_type in ('file', 'directory'):
                with self.subTest(kind=kind, entry_type=entry_type):
                    target = self.target(kind, entry_type)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if entry_type == 'file':
                        target.write_bytes(b'previous capture')
                    else:
                        target.mkdir()
                    with self.assertRaisesRegex(ValueError, 'already exists'):
                        _record(kind, self.arguments(kind, entry_type))
                    self.assertEqual(target.read_bytes() if target.is_file() else list(target.iterdir()),
                                     b'previous capture' if entry_type == 'file' else [])

    def test_dangling_destination_and_lock_symlinks_are_rejected(self):
        for kind in ('ode', 'neko'):
            for entry_type in ('destination', 'lock'):
                with self.subTest(kind=kind, entry_type=entry_type):
                    target = self.target(kind, entry_type)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    link = target if entry_type == 'destination' else target.parent / f'.{target.name}.capture.lock'
                    outside = self.root / f'{kind}-{entry_type}-outside'
                    link.symlink_to(outside)
                    with self.assertRaisesRegex(ValueError, 'symlink'):
                        _record(kind, self.arguments(kind, entry_type))
                    self.assertTrue(link.is_symlink())
                    self.assertFalse(outside.exists())
                    if entry_type == 'lock':
                        self.assertFalse(target.exists())

    def test_fifo_lock_is_rejected(self):
        for kind in ('ode', 'neko'):
            with self.subTest(kind=kind):
                target = self.target(kind)
                target.parent.mkdir(parents=True)
                os.mkfifo(target.parent / f'.{target.name}.capture.lock')
                with self.assertRaisesRegex(ValueError, 'regular file'):
                    _record(kind, self.arguments(kind))
                self.assert_no_capture(kind)

    def test_destination_ancestor_symlink_is_rejected(self):
        outside = self.root / 'outside'
        outside.mkdir()
        (self.project / 'runs').symlink_to(outside, target_is_directory=True)
        for kind in ('ode', 'neko'):
            with self.subTest(kind=kind):
                with self.assertRaisesRegex(ValueError, 'symlink'):
                    _record(kind, self.arguments(kind))
        self.assertEqual(list(outside.iterdir()), [])

    def test_source_session_symlink_is_rejected(self):
        for kind, source in [('ode', self.ode_source), ('neko', self.neko_source)]:
            with self.subTest(kind=kind):
                moved = source.with_name(source.name + '-original')
                source.rename(moved)
                source.symlink_to(moved, target_is_directory=True)
                with self.assertRaisesRegex(ValueError, 'symlink'):
                    _record(kind, self.arguments(kind))
                self.assertFalse(self.target(kind).exists())
                self.assert_sources_unchanged()

    def test_source_file_symlink_is_rejected(self):
        for kind, source in [('ode', self.model), ('neko', self.manifest), ('neko', self.network)]:
            with self.subTest(kind=kind, source=source.name):
                moved = source.with_name(source.name + '-original')
                source.rename(moved)
                source.symlink_to(moved)
                with self.assertRaisesRegex(ValueError, 'symlink'):
                    _record(kind, self.arguments(kind))
                source.unlink()
                moved.rename(source)
                self.assert_no_capture(kind)

    def test_invalid_inventory_identity_hash_duplicate_and_escape_are_rejected(self):
        invalid = []
        for field, value in [('session_id', 'another-session'), ('sha256', '0' * 64),
                             ('path', str(self.network)), ('path', 'relative.txt')]:
            entry = dict(self.entries[0])
            entry[field] = value
            invalid.append([entry])
        invalid.extend([[], [self.entries[0], self.entries[0]]])
        for entries in invalid:
            with self.subTest(entries=entries):
                arguments = self.arguments('ode')
                arguments['entries'] = entries
                with self.assertRaises(ValueError):
                    _record('ode', arguments)
                self.assert_no_capture('ode')

    def test_concurrent_processes_publish_exactly_one_capture(self):
        context = multiprocessing.get_context('fork')
        for kind in ('ode', 'neko'):
            with self.subTest(kind=kind):
                results = context.Queue()
                barrier = context.Barrier(2)
                processes = [context.Process(target=_worker, args=(kind, self.arguments(kind), results, barrier))
                             for _ in range(2)]
                try:
                    for process in processes:
                        process.start()
                    for process in processes:
                        process.join(timeout=20)
                        self.assertFalse(process.is_alive(), 'concurrent capture stalled')
                        self.assertEqual(process.exitcode, 0)
                    outcomes = [results.get(timeout=2) for _ in range(2)]
                    self.assertEqual(sorted(outcome[0] for outcome in outcomes), ['ValueError', 'ok'])
                    self.assertIn('already exists', next(outcome[1] for outcome in outcomes if outcome[0] == 'ValueError'))
                    self.assert_complete(kind, self.target(kind))
                    self.assert_sources_unchanged()
                finally:
                    for process in processes:
                        if process.is_alive():
                            process.kill()
                        process.join(timeout=5)
                    results.close()
                    results.join_thread()

    def test_killed_writer_leaves_only_hidden_staging_and_allows_retry(self):
        context = multiprocessing.get_context('fork')
        for kind in ('ode', 'neko'):
            with self.subTest(kind=kind):
                results = context.Queue()
                ready = context.Event()
                process = context.Process(target=_worker, args=(kind, self.arguments(kind), results),
                                          kwargs=dict(ready=ready, interrupt_write=True))
                try:
                    process.start()
                    self.assertTrue(ready.wait(timeout=15), 'writer did not reach partial staging write')
                    target = self.target(kind)
                    self.assertFalse(target.exists())
                    self.assertEqual(len(list(target.parent.glob(f'.{target.name}.staging-*'))), 1)
                    process.kill()
                    process.join(timeout=5)
                    self.assertEqual(process.exitcode, -signal.SIGKILL)
                    self.assertFalse(target.exists())
                    self.assert_sources_unchanged()
                    _record(kind, self.arguments(kind))
                    self.assert_complete(kind, target)
                finally:
                    if process.is_alive():
                        process.kill()
                    process.join(timeout=5)
                    results.close()
                    results.join_thread()


if __name__ == '__main__':
    unittest.main()
