"""Boolean capture works with legacy storage and explicit per-server caches."""
import json
import copy
import shutil
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.capture.artifact_capture import boolean_artifact_root
from scripts.capture.record_neko_boolean_handoff import record_neko
from scripts.capture.record_maboss_physicell_handoff import record_maboss
from scripts import gate, state

try:
    from mcp_biomodelling_servers.handoff import (
        HandoffProvenance, NeKoToMaBoSSHandoffManifest,
        MaBoSSToPhysiCellHandoffManifest, handoff_artifact,
        load_handoff_manifest,
    )
    BACKEND = True
except ImportError:
    BACKEND = False


class RootTests(unittest.TestCase):
    def test_explicit_root_selection_rejects_ambiguity_and_symlinks(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'artifacts').mkdir()
            self.assertEqual(boolean_artifact_root(root, None), root / 'artifacts')
            self.assertEqual(boolean_artifact_root(None, root), root)
            for arguments in ((None, None), (root, root), (None, root / 'missing')):
                with self.assertRaises(ValueError):
                    boolean_artifact_root(*arguments)
            (root / 'link').symlink_to(root / 'artifacts')
            with self.assertRaisesRegex(ValueError, 'symlink'):
                boolean_artifact_root(None, root / 'link')


@unittest.skipUnless(BACKEND, 'requires pure backend contract readers')
class BooleanCaptureTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.project = self.root / 'project'
        self.project.mkdir()
        self.cache = self.root / 'cache'

    def source(self, server, session):
        return HandoffProvenance(
            server=server, session_id=session,
            mcp_package={'name': 'mcp-biomodelling-servers', 'version': 'test'},
            modelling_package={'name': 'nekomata' if server == 'NeKo' else 'maboss', 'version': 'test'},
            operation='test-export',
        )

    def fixture(self, server):
        session = 'neko-session' if server == 'NeKo' else 'maboss-session'
        folder = self.cache / server / session
        folder.mkdir(parents=True)
        common = dict(source=self.source(server, session), network={'nodes': ['A'], 'output_nodes': ['A']})
        if server == 'NeKo':
            bnet = folder / 'model.bnet'
            bnet.write_text('targets, factors\nA, A\n')
            model = NeKoToMaBoSSHandoffManifest(**common,
                bnet_file=handoff_artifact(bnet, server=server, session_id=session, role='neko_bnet'))
        else:
            bnd, cfg = folder / 'model.bnd', folder / 'model.cfg'
            bnd.write_text('Node A { logic = A; }\n')
            cfg.write_text('A.istate = 1;\n')
            model = MaBoSSToPhysiCellHandoffManifest(**common,
                bnd_file=handoff_artifact(bnd, server=server, session_id=session, role='maboss_bnd'),
                cfg_file=handoff_artifact(cfg, server=server, session_id=session, role='maboss_cfg'),
                simulation={'parameters': {}}, target={'cell_type': 'cell'})
        manifest = folder / 'handoff.json'
        manifest.write_text(model.model_dump_json())
        return manifest, model

    def capture(self, server, manifest, capture_id='capture-1'):
        recorder = record_neko if server == 'NeKo' else record_maboss
        return recorder(self.project, None, manifest, capture_id,
                        artifact_root=self.cache / server)

    def target(self, server, session, capture_id='capture-1'):
        role, category = ('network-curator', 'boolean-handoffs') if server == 'NeKo' else ('boolean-dynamics-modeler', 'physicell-handoffs')
        return self.project / 'runs' / role / session / category / capture_id

    def test_explicit_cache_capture_is_portable_and_does_not_overwrite(self):
        for server in ('NeKo', 'MaBoSS'):
            with self.subTest(server=server):
                manifest, model = self.fixture(server)
                original = manifest.read_bytes()
                self.capture(server, manifest)
                target = self.target(server, model.source.session_id)
                self.assertEqual((target / 'original.handoff.json').read_bytes(), original)
                with self.assertRaisesRegex(ValueError, 'already exists'):
                    self.capture(server, manifest)
                shutil.rmtree(self.cache / server)
                loaded = load_handoff_manifest(target / 'import.handoff.json')
                self.assertEqual(loaded.source, model.source)
                self.assertEqual(loaded.schema_version, '1.0')

    def test_wrong_root_and_changed_payload_never_publish(self):
        for server in ('NeKo', 'MaBoSS'):
            with self.subTest(server=server):
                manifest, model = self.fixture(server)
                recorder = record_neko if server == 'NeKo' else record_maboss
                with self.assertRaises(ValueError):
                    recorder(self.project, None, manifest, 'outside', artifact_root=self.project)
                ref = model.bnet_file if server == 'NeKo' else model.bnd_file
                Path(ref.path).write_text('changed')
                with self.assertRaises(ValueError):
                    self.capture(server, manifest)
                self.assertFalse(self.target(server, model.source.session_id).exists())

    def derivative(self, server, session):
        from mcp_biomodelling_servers.import_lineage import capture_import, write_source_export
        folder = self.root / ('historical-' + server)
        folder.mkdir()
        suffix = '.sif' if server == 'NeKo' else '.bnet'
        ancestor = folder / ('original' + suffix)
        ancestor.write_text('A\t1\tB\n' if server == 'NeKo' else 'targets, factors\nA, A\nB, A\n')
        sidecar = write_source_export(ancestor, server='NeKo', session_id='ancestor-session', imports=[])
        edited = folder / ('edited' + suffix)
        edited.write_text('A\t-1\tB\n' if server == 'NeKo' else 'targets, factors\nA, !A\nB, A\n')
        return capture_import(edited, server=server, session_id=session,
                              parent_manifest=str(sidecar), derived_from=str(ancestor))

    def v2(self, manifest, model, imports):
        raw = model.model_dump(mode='json')
        raw.update(schema_version='2.0', source_ancestry=[item.model_dump(mode='json') for item in imports])
        manifest.write_text(json.dumps(raw))
        return raw

    def test_v2_derived_source_survives_both_captures_and_deleted_originals(self):
        manifest, neko = self.fixture('NeKo')
        imported = self.derivative('NeKo', neko.source.session_id)
        self.v2(manifest, neko, [imported])
        self.capture('NeKo', manifest)
        captured_neko = self.target('NeKo', neko.source.session_id) / 'import.handoff.json'
        upstream = load_handoff_manifest(captured_neko)

        manifest, maboss = self.fixture('MaBoSS')
        raw = self.v2(manifest, maboss, upstream.source_ancestry)
        raw['parent_manifest'] = handoff_artifact(captured_neko, server='NeKo',
            session_id=neko.source.session_id, role='parent_manifest').model_dump(mode='json')
        raw['lineage'] = [upstream.source.model_dump(mode='json')]
        manifest.write_text(json.dumps(raw))
        self.capture('MaBoSS', manifest)
        target = self.target('MaBoSS', maboss.source.session_id)
        captured = target / 'import.handoff.json'
        shutil.rmtree(self.cache)
        shutil.rmtree(self.root / 'historical-NeKo')
        shutil.rmtree(self.target('NeKo', neko.source.session_id))
        loaded = load_handoff_manifest(captured)
        self.assertEqual(loaded.source_ancestry[0].relationship, 'edited-derivative')
        gate.verify_manifest(self.project, json.loads(captured.read_text()),
                             'maboss-to-physicell', maboss.source.session_id, ['A'])
        self.assertTrue(list((target / 'ancestry').iterdir()))
        index = json.loads((self.project / 'runs/index.json').read_text())
        self.assertIn('/ancestry/', json.dumps(index))

    def test_v2_ordinary_bnet_derivative_does_not_invent_stage_parent(self):
        manifest, model = self.fixture('MaBoSS')
        imported = self.derivative('MaBoSS', model.source.session_id)
        self.v2(manifest, model, [imported])
        self.capture('MaBoSS', manifest)
        shutil.rmtree(self.cache)
        shutil.rmtree(self.root / 'historical-MaBoSS')
        target = self.target('MaBoSS', model.source.session_id)
        loaded = load_handoff_manifest(target / 'import.handoff.json')
        self.assertIsNone(loaded.parent_manifest)
        self.assertEqual(loaded.lineage, [])
        self.assertEqual(loaded.source_ancestry[0].derived_from.session_id, 'ancestor-session')

        # Known ancestry cannot substitute for current revision review/approval.
        for name in ('CURRENT_STATE.md', 'DECISIONS.md', 'VALIDATION_PLAN.md'):
            shutil.copyfile(state.ROOT / 'templates' / name, self.project / name)
        artifact = {'path': (target / 'import.handoff.json').relative_to(self.project).as_posix(),
                    'sha256': state.digest(target / 'import.handoff.json')}
        session = model.source.session_id
        state.update(self.project, 'registry-add', dict(zip(state.REGISTRY,
            ['boolean-dynamics-modeler', session, 'boolean-dynamics', 'active',
             'ancestor-session', 'pending', artifact['path']])))
        with self.assertRaises(ValueError):
            gate.check(self.project, 'multicellular', session, ['A'])
        review = {'id': 'review-v2', 'kind': 'stage_review', 'session_id': session,
                  'stage': 'boolean-dynamics', 'outcome': 'approved', 'artifact': artifact}
        for role in ('scientific-reviewer', 'reproducibility-auditor'):
            report = self.project / 'runs' / (role + '.md')
            report.write_text('Independent synthetic fixture review.')
            review[role] = {'path': report.relative_to(self.project).as_posix(), 'sha256': state.digest(report)}
        state.update(self.project, 'record', review)
        approval = {'id': 'approval-v2', 'kind': 'stage_approval', 'session_id': session,
                    'stage': 'boolean-dynamics', 'downstream_stage': 'multicellular',
                    'outputs': ['A'], 'approved_by': 'researcher',
                    'authorization': 'Synthetic test approval of this exact changed model.', 'artifact': artifact}
        state.update(self.project, 'record', approval)
        state.update(self.project, 'registry-handoff', {'session_id': session, 'handoff': 'approved'})
        state.update(self.project, 'registry-handoff', {'session_id': session, 'handoff': 'exported', 'artifact': artifact})
        self.assertTrue(gate.check(self.project, 'multicellular', session, ['A'])['passed'])
        updated = json.loads((target / 'import.handoff.json').read_text())
        updated['biological_context'] = 'A changed revision requires renewed approval.'
        (target / 'import.handoff.json').write_text(json.dumps(updated))
        with self.assertRaises(ValueError):
            gate.check(self.project, 'multicellular', session, ['A'])

    def test_v2_tampered_snapshot_and_wrong_owner_rejected_before_publication(self):
        manifest, model = self.fixture('NeKo')
        imported = self.derivative('NeKo', model.source.session_id)
        original = self.v2(manifest, model, [imported])
        for variant in ('blob', 'owner', 'missing', 'version'):
            with self.subTest(variant=variant):
                raw = copy.deepcopy(original)
                entry = raw['source_ancestry'][0]
                if variant == 'blob':
                    digest = next(iter(entry['evidence']['blobs']))
                    entry['evidence']['blobs'][digest] = 'dGFtcGVyZWQ='
                elif variant == 'owner':
                    entry['source']['session_id'] = 'wrong-session'
                elif variant == 'missing':
                    del raw['source_ancestry']
                else:
                    raw['schema_version'] = '3.0'
                manifest.write_text(json.dumps(raw))
                with self.assertRaises(ValueError):
                    self.capture('NeKo', manifest)
                with self.assertRaises(ValueError):
                    gate.verify_manifest(self.root, raw, 'neko-to-maboss', model.source.session_id, ['A'])
                self.assertFalse(self.target('NeKo', model.source.session_id).exists())

    def test_v2_metadata_can_use_configured_python_without_starting_a_server(self):
        from scripts import boolean_contract
        manifest, model = self.fixture('NeKo')
        raw = self.v2(manifest, model, [])
        # A system-Python hook lacks the contract package, but its explicitly
        # configured modelling interpreter can validate the exact same bytes.
        with mock.patch.object(boolean_contract, '_validate', side_effect=ImportError), \
             mock.patch('scripts.codex.dispatcher.launch.launch_configuration',
                        return_value=(sys.executable, os.environ.copy())):
            boolean_contract.validate_metadata(raw)
        with mock.patch.object(boolean_contract, '_validate', side_effect=ImportError), \
             mock.patch('scripts.codex.dispatcher.launch.launch_configuration',
                        return_value=('/nonexistent/modelling-python', os.environ.copy())):
            with self.assertRaisesRegex(ValueError, 'could not run'):
                boolean_contract.validate_metadata(raw)

    def test_v2_stage_parent_ancestry_cannot_be_silently_dropped(self):
        manifest, neko = self.fixture('NeKo')
        imported = self.derivative('NeKo', neko.source.session_id)
        self.v2(manifest, neko, [imported])
        self.capture('NeKo', manifest)
        parent = self.target('NeKo', neko.source.session_id) / 'import.handoff.json'
        manifest, maboss = self.fixture('MaBoSS')
        raw = self.v2(manifest, maboss, [])
        raw['parent_manifest'] = handoff_artifact(parent, server='NeKo',
            session_id=neko.source.session_id, role='parent_manifest').model_dump(mode='json')
        raw['lineage'] = [neko.source.model_dump(mode='json')]
        manifest.write_text(json.dumps(raw))
        with self.assertRaisesRegex(ValueError, 'ancestry'):
            self.capture('MaBoSS', manifest)
        with self.assertRaisesRegex(ValueError, 'ancestry'):
            gate.verify_manifest(self.root, raw, 'maboss-to-physicell', maboss.source.session_id, ['A'])


if __name__ == '__main__':
    unittest.main()
