"""Backend 2.5.0 handoffs: NeKo 2.1 / ODE 2.0 curation and MaBoSS 2.1 readouts."""
import copy
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts import gate
from scripts.codex.ode_artifacts import digest
from scripts.codex.validate_handoff import HandoffValidationError, validate_handoff
from scripts.curation_contract import (check_binding, check_parent_scope, check_readout_isolation,
                                       relocation_of)
from test_ode_integration import fixture as ode_fixture, refresh as ode_refresh

try:
    from mcp_biomodelling_servers.handoff import (
        HandoffProvenance, MaBoSSToPhysiCellHandoffManifest, NeKoToMaBoSSHandoffManifest,
        handoff_artifact, load_handoff_manifest, verify_handoff_manifest,
    )
    from mcp_biomodelling_servers.neko_provenance import NeKoExportEvidence
    BACKEND = True
except ImportError:
    BACKEND = False

SESSION = 'neko-session'


def artifact_ref(path, role, session=SESSION, server='NeKo'):
    return {'session_id': session, 'name': path.name, 'path': str(path), 'suffix': path.suffix,
            'media_type': 'application/json' if path.suffix == '.json' else 'text/plain',
            'size_bytes': path.stat().st_size, 'server': server, 'role': role,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def companion_bytes(model, state_id=0, session=SESSION, working=True):
    """Compact neko-export v1 companion, as written by backend 2.5.0."""
    return json.dumps({
        'format': 'neko-export', 'schema_version': 1,
        'mcp': {'session_id': session, 'network_id': 'net-1', 'state_id': state_id, 'database_name': 'SIGNOR'},
        'export': {'artifact': model, 'node_renames': {}, 'library_projection': None},
        'history': {'format': 'neko-history', 'schema_version': 1, 'database_name': 'SIGNOR',
                    'current_state_id': state_id, 'working_state_matches_current': working, 'states': []},
    }, separators=(',', ':')).encode()


class CurationContractTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        bnet = self.root / 'model.bnet'
        bnet.write_text('targets, factors\nA, A\n')
        self.model = artifact_ref(bnet, 'neko_bnet')

    def test_binding_ignores_only_the_relocated_path(self):
        raw = companion_bytes(self.model)
        moved = dict(self.model, path='/elsewhere/model.bnet')
        self.assertEqual(check_binding(raw, moved, SESSION, 0)['mcp']['state_id'], 0)
        for field, value in (('sha256', '0' * 64), ('name', 'other.bnet'), ('size_bytes', 1), ('role', 'neko_sif')):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'not bound'):
                check_binding(raw, dict(self.model, **{field: value}), SESSION, 0)

    def test_binding_rejects_wrong_state_session_and_unsaved_work(self):
        cases = ((companion_bytes(self.model), SESSION, 1, 'session/state'),
                 (companion_bytes(self.model), 'other', 0, 'session/state'),
                 (companion_bytes(self.model), SESSION, None, 'integer history_state_id'),
                 (companion_bytes(self.model, working=False), SESSION, 0, 'saved working state'),
                 (b'not json', SESSION, 0, 'not valid JSON'),
                 (json.dumps({'format': 'neko-history'}).encode(), SESSION, 0, 'neko-export'))
        for raw, session, state, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                check_binding(raw, self.model, session, state)

    def test_relocation_permits_only_named_payload_paths(self):
        original = {'network_file': {'path': '/a/n.json', 'sha256': 'x'}, 'curation_file': {'path': '/a/c.json'}, 'k': 1}
        moved = copy.deepcopy(original)
        moved['network_file']['path'] = '/b/n.json'
        moved['curation_file']['path'] = '/b/c.json'
        self.assertTrue(relocation_of(original, moved, ('network_file', 'curation_file')))
        moved['k'] = 2
        self.assertFalse(relocation_of(original, moved, ('network_file', 'curation_file')))
        moved['k'] = 1
        moved['network_file']['sha256'] = 'y'
        self.assertFalse(relocation_of(original, moved, ('network_file', 'curation_file')))

    def test_readouts_keep_their_rule_and_never_feed_the_core(self):
        readouts = {'R': {'origin': 'readout', 'rule': 'A & !B', 'explanation': 'summary'}}
        bnd = ('// MCP_READOUTS_V1 {"definitions": {}}\nNode A { logic = A; }\nNode B { logic = NOT (A); }\n'
               'Node R {\n\tlogic = A & !B;\n\trate_up = @logic ? 1.0 : 0;\n}\n')
        check_readout_isolation(bnd, ['A', 'B', 'R'], readouts)
        check_readout_isolation('Node A { logic = A; }\n', ['A'], {})
        failures = ((bnd.replace('NOT (A)', 'A | R'), ['A', 'B', 'R'], 'feeds back'),
                    (bnd.replace('logic = A & !B', 'logic = A'), ['A', 'B', 'R'], 'differs from BND'),
                    (bnd + 'Node X { logic = A; }\n', ['A', 'B', 'R'], 'cannot verify'),
                    (bnd, ['A', 'B'], 'name nodes'))
        for text, nodes, message in failures:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                check_readout_isolation(text, nodes, readouts)

    def test_only_declared_readouts_may_extend_the_parent_core(self):
        check_parent_scope(['A', 'B'], ['A'], ['A', 'B', 'R'], ['A', 'R'], {'R': {}})
        check_parent_scope(['A', 'B'], ['A'], ['B', 'A'], ['A'], None)
        failures = ((['A', 'B'], ['A'], ['A', 'B', 'X'], ['A'], {}, 'nodes disagree'),
                    (['A', 'B'], ['A'], ['A', 'B'], ['A'], {'B': {}}, 'reclassify'),
                    (['A', 'B'], ['A'], ['A', 'B', 'R'], ['B'], {'R': {}}, 'output selections'))
        for parent, parent_outputs, nodes, outputs, readouts, message in failures:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                check_parent_scope(parent, parent_outputs, nodes, outputs, readouts)


class GateVersionTableTests(unittest.TestCase):
    """Version and v1-metadata checks run before any backend contract import."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        folder = self.root / 'runs/network-curator' / SESSION
        folder.mkdir(parents=True)
        bnet = folder / 'network.bnet'
        bnet.write_text('targets, factors\nA, A\n')
        self.manifest = {'schema_name': 'mcp-biomodelling-handoff', 'schema_version': '1.0',
                         'handoff_type': 'neko-to-maboss', 'source': {'server': 'NeKo', 'session_id': SESSION},
                         'network': {'nodes': ['A'], 'output_nodes': ['A']},
                         'bnet_file': artifact_ref(bnet, 'neko_bnet')}
        for ref in (self.manifest['bnet_file'],):
            ref['path'] = str(Path(ref['path']).relative_to(self.root))

    def test_v1_still_passes_and_cannot_smuggle_new_metadata(self):
        gate.verify_manifest(self.root, self.manifest, 'neko-to-maboss', SESSION, ['A'])
        for key, value in (('curation_file', {'path': 'x.json'}), ('readouts', {}), ('model_revision', 'a' * 64)):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'v1 handoffs cannot declare'):
                gate.verify_manifest(self.root, dict(self.manifest, **{key: value}), 'neko-to-maboss', SESSION, ['A'])

    def test_unknown_or_type_inappropriate_versions_fail_closed(self):
        for expected, version in (('neko-to-maboss', '2.2'), ('neko-to-maboss', '3.0'), ('neko-to-biomass', '2.1'),
                                  ('maboss-to-physicell', '2.2'), ('neko-to-maboss', None)):
            data = dict(self.manifest, schema_version=version, handoff_type=expected)
            with self.subTest(expected=expected, version=version), \
                    self.assertRaisesRegex(ValueError, 'unsupported typed handoff version'):
                gate.verify_manifest(self.root, data, expected, SESSION)


class ODECurationTests(unittest.TestCase):
    """Dependency-free NeKo->BioMASS v2.0 capture and ODE completion checks."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.h, self.rev = ode_fixture(self.root)
        self.cache = self.root / 'cache/NeKo'
        self.source = self.cache / SESSION
        self.source.mkdir(parents=True)
        self.network = self.source / 'export.network.json'
        self.network.write_text(json.dumps({'nodes': [{'node_id': 'A'}, {'node_id': 'B'}],
                                            'edges': [{'edge_id': 'e', 'source': 'A', 'target': 'B'}]}))
        network_ref = artifact_ref(self.network, 'neko_ode_network')
        self.companion = self.source / 'export.network.abc.history.json'
        self.companion.write_bytes(companion_bytes(network_ref))
        self.manifest = {'schema_name': 'mcp-biomodelling-handoff', 'schema_version': '2.0',
                         'handoff_type': 'neko-to-biomass',
                         'source': {'server': 'NeKo', 'session_id': SESSION},
                         'biological_context': 'Synthetic fixture.', 'history_state_id': 0,
                         'network_file': network_ref,
                         'curation_file': artifact_ref(self.companion, 'neko_history')}
        self.path = self.source / 'export.handoff.json'
        self.path.write_text(json.dumps(self.manifest))

    def record(self, capture='c1'):
        from scripts.capture.record_neko_ode_handoff import record_neko
        return record_neko(self.root, None, self.path, capture, artifact_root=self.cache)

    def complete(self, copied, upstream):
        self.h['ode'].update(input_kind='neko', upstream_manifest=copied['upstream_manifest'])
        self.h['derived_from_session_id'] = SESSION
        snapshot = json.loads((self.rev / 'snapshot.json').read_text())
        snapshot['document']['upstream'] = upstream
        (self.rev / 'snapshot.json').write_text(json.dumps(snapshot))
        inventory = json.loads((self.rev / 'integrity.json').read_text())
        inventory['snapshot.json'] = digest(self.rev / 'snapshot.json')
        (self.rev / 'integrity.json').write_text(json.dumps(inventory))
        ode_refresh(self.root, self.h)
        return validate_handoff(self.h, project_root=self.root)

    def test_capture_copies_and_pins_the_companion(self):
        copied = self.record()
        target = self.root / copied['upstream_manifest']
        imported = json.loads(target.read_text())
        self.assertEqual(Path(imported['curation_file']['path']).parent, target.parent)
        self.assertEqual((target.parent / self.companion.name).read_bytes(), self.companion.read_bytes())
        relocation = json.loads((target.parent / 'relocation.json').read_text())
        self.assertEqual(relocation['curation_sha256'], self.manifest['curation_file']['sha256'])
        self.assertIn('original backend manifest', relocation['curation_binding'])
        self.assertTrue(relocation_of(self.manifest, imported, ('network_file', 'curation_file')))

    def test_completion_accepts_the_original_backend_upstream_only_with_relocation(self):
        copied = self.record()
        # BioMASS 2.5.0 must import the original, so its snapshot records it.
        self.complete(copied, self.manifest)
        imported = json.loads((self.root / copied['upstream_manifest']).read_text())
        self.complete(copied, imported)
        other = copy.deepcopy(self.manifest)
        other['biological_context'] = 'A different upstream.'
        with self.assertRaisesRegex(HandoffValidationError, 'snapshot upstream differs'):
            self.complete(copied, other)

    def test_completion_rejects_tampered_or_unpinned_companion(self):
        copied = self.record()
        companion = (self.root / copied['upstream_manifest']).parent / self.companion.name
        companion.write_bytes(companion.read_bytes() + b' ')
        with self.assertRaisesRegex(HandoffValidationError, 'curation companion hash'):
            self.complete(copied, self.manifest)

    def test_completion_rejects_non_path_changes_even_with_consistent_hashes(self):
        copied = self.record()
        imported_path = self.root / copied['upstream_manifest']
        imported = json.loads(imported_path.read_text())
        imported['biological_context'] = 'Rewritten after capture.'
        imported_path.write_text(json.dumps(imported))
        relocation_path = imported_path.parent / 'relocation.json'
        relocation = json.loads(relocation_path.read_text())
        relocation['import_manifest_sha256'] = digest(imported_path)
        relocation_path.write_text(json.dumps(relocation))
        with self.assertRaisesRegex(HandoffValidationError, 'relocation changed NeKo scientific provenance'):
            self.complete(copied, self.manifest)

    def test_recording_rejects_bad_versions_owners_and_paths(self):
        cases = []
        missing = copy.deepcopy(self.manifest); del missing['curation_file']
        cases.append((missing, 'curation_file declaration'))
        cases.append((dict(self.manifest, schema_version='2.1'), 'curation_file declaration'))
        legacy = dict(self.manifest, schema_version='1.0')
        cases.append((legacy, 'curation_file declaration'))
        wrong_owner = copy.deepcopy(self.manifest); wrong_owner['curation_file']['session_id'] = 'other'
        cases.append((wrong_owner, 'ownership mismatch'))
        outside = self.cache / 'other-session'
        outside.mkdir()
        shutil.copyfile(self.companion, outside / self.companion.name)
        escaped = copy.deepcopy(self.manifest); escaped['curation_file']['path'] = str(outside / self.companion.name)
        cases.append((escaped, 'subpath'))
        tampered = copy.deepcopy(self.manifest); tampered['curation_file']['sha256'] = '0' * 64
        cases.append((tampered, 'hash or byte count'))
        unbound = copy.deepcopy(self.manifest); unbound['history_state_id'] = 3
        cases.append((unbound, 'session/state'))
        for index, (manifest, message) in enumerate(cases):
            self.path.write_text(json.dumps(manifest))
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                self.record(f'bad-{index}')
        published = self.root / 'runs/network-curator' / SESSION / 'ode-handoffs'
        self.assertEqual(sorted(published.glob('bad-*')) if published.exists() else [], [])


@unittest.skipUnless(BACKEND, 'requires backend 2.5.0 contract readers')
class BackendV25CaptureTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.project = self.base / 'project'
        self.project.mkdir()
        self.neko_root = self.base / 'cache/NeKo'
        self.maboss_root = self.base / 'cache/MaBoSS'

    def provenance(self, server, session):
        return HandoffProvenance(
            server=server, session_id=session,
            mcp_package={'name': 'mcp-biomodelling-servers', 'version': '2.5.0'},
            modelling_package={'name': 'nekomata' if server == 'NeKo' else 'maboss', 'version': 'test'},
            operation='test-export')

    def neko(self, session=SESSION):
        folder = self.neko_root / session
        folder.mkdir(parents=True)
        bnet = folder / 'export.bnet'
        bnet.write_text('targets, factors\nA, A\nB, !A\n')
        bnet_ref = handoff_artifact(bnet, server='NeKo', session_id=session, role='neko_bnet')
        companion = folder / 'export.abc.history.json'
        evidence = NeKoExportEvidence.model_validate_json(companion_bytes(bnet_ref.model_dump(mode='json'), session=session))
        companion.write_bytes(evidence.model_dump_json().encode())
        model = NeKoToMaBoSSHandoffManifest(
            schema_version='2.1', source_ancestry=[], source=self.provenance('NeKo', session),
            network={'nodes': ['A', 'B'], 'output_nodes': ['A']}, history_state_id=0, bnet_file=bnet_ref,
            curation_file=handoff_artifact(companion, server='NeKo', session_id=session, role='neko_history'))
        path = folder / 'export.handoff.json'
        path.write_text(model.model_dump_json())
        verify_handoff_manifest(model)  # the fixture itself is accepted by the backend
        return path, model

    def maboss(self, parent_path, parent, *, readouts=None, bnd=None, nodes=None, outputs=None, session='maboss-session'):
        folder = self.maboss_root / session
        folder.mkdir(parents=True)
        readouts = {'R': {'origin': 'readout', 'rule': 'A & !B', 'explanation': 'summary'}} if readouts is None else readouts
        bnd_path, cfg_path = folder / 'export.bnd', folder / 'export.cfg'
        bnd_path.write_text(bnd or 'Node A { logic = A; }\nNode B { logic = NOT (A); }\nNode R { logic = A & !B; }\n')
        cfg_path.write_text('A.istate = 1;\n')
        model = MaBoSSToPhysiCellHandoffManifest(
            schema_version='2.1', source_ancestry=[], source=self.provenance('MaBoSS', session),
            lineage=[parent.source], network={'nodes': nodes or ['A', 'B', 'R'], 'output_nodes': outputs or ['A', 'R']},
            bnd_file=handoff_artifact(bnd_path, server='MaBoSS', session_id=session, role='maboss_bnd'),
            cfg_file=handoff_artifact(cfg_path, server='MaBoSS', session_id=session, role='maboss_cfg'),
            parent_manifest=handoff_artifact(parent_path, server='NeKo', session_id=parent.source.session_id, role='parent_manifest'),
            simulation={'parameters': {}}, target={'cell_type': 'cell'}, model_revision='a' * 64, readouts=readouts)
        path = folder / 'export.handoff.json'
        path.write_text(model.model_dump_json())
        return path, model

    def capture_neko(self, path, capture='c1'):
        from scripts.capture.record_neko_boolean_handoff import record_neko
        return record_neko(self.project, None, path, capture, artifact_root=self.neko_root)

    def capture_maboss(self, path, capture='c1'):
        from scripts.capture.record_maboss_physicell_handoff import record_maboss
        record_maboss(self.project, None, path, capture, parent_root=self.neko_root, artifact_root=self.maboss_root)
        return self.project / 'runs/boolean-dynamics-modeler/maboss-session/physicell-handoffs' / capture / 'import.handoff.json'

    def test_neko_21_capture_is_gate_verifiable_but_backend_bound_to_original(self):
        path, _ = self.neko()
        result = self.capture_neko(path)
        self.assertEqual(result['backend_import_manifest'], str(path))
        captured = self.project / result['upstream_manifest']
        data = json.loads(captured.read_text())
        self.assertEqual(Path(data['curation_file']['path']).parent, captured.parent)
        gate.verify_manifest(self.project, data, 'neko-to-maboss', SESSION, ['A'])
        # Documents why specialists import the original backend manifest.
        with self.assertRaisesRegex(ValueError, 'not bound'):
            load_handoff_manifest(captured)
        load_handoff_manifest(path)

    def test_neko_21_recording_fails_for_tampered_or_escaped_companion(self):
        path, model = self.neko()
        companion = Path(model.curation_file.path)
        original = companion.read_bytes()
        companion.write_bytes(original + b' ')
        with self.assertRaises(ValueError):
            self.capture_neko(path, 'tampered')
        companion.write_bytes(original)
        escaped_dir = self.neko_root / 'elsewhere'
        escaped_dir.mkdir()
        shutil.copyfile(companion, escaped_dir / companion.name)
        moved = json.loads(path.read_text())
        moved['curation_file']['path'] = str(escaped_dir / companion.name)
        path.write_text(json.dumps(moved))
        with self.assertRaisesRegex(ValueError, 'subpath'):
            self.capture_neko(path, 'escaped')

    def test_relocated_verification_permits_only_path_changes(self):
        from scripts.capture.neko_curation import verify_relocated
        path, original = self.neko()
        moved_dir = self.base / 'moved'
        moved_dir.mkdir()
        for field in ('bnet_file', 'curation_file'):
            shutil.copyfile(getattr(original, field).path, moved_dir / getattr(original, field).name)
        relocated = original.model_copy(deep=True)
        relocated.bnet_file.path = str(moved_dir / original.bnet_file.name)
        relocated.curation_file.path = str(moved_dir / original.curation_file.name)
        raw = Path(relocated.curation_file.path).read_bytes()
        verify_relocated(original, relocated, 'bnet_file', raw)
        with self.assertRaisesRegex(ValueError, 'changed during validation'):
            verify_relocated(original, relocated, 'bnet_file', raw + b' ')
        changed = relocated.model_copy(deep=True)
        changed.bnet_file.sha256 = '0' * 64
        with self.assertRaisesRegex(ValueError, 'more than artifact paths'):
            verify_relocated(original, changed, 'bnet_file', raw)
        state = relocated.model_copy(deep=True)
        state.history_state_id = 1
        with self.assertRaisesRegex(ValueError, 'curation state'):
            verify_relocated(original, state, 'bnet_file', raw)

    def test_gate_rejects_tampered_or_foreign_session_companion(self):
        path, _ = self.neko()
        result = self.capture_neko(path)
        data = json.loads((self.project / result['upstream_manifest']).read_text())
        companion = Path(data['curation_file']['path'])
        foreign = self.project / 'runs/network-curator/other-session/c' / companion.name
        foreign.parent.mkdir(parents=True)
        shutil.copyfile(companion, foreign)
        moved = copy.deepcopy(data)
        moved['curation_file']['path'] = str(foreign)
        with self.assertRaisesRegex(ValueError, 'same session tree'):
            gate.verify_manifest(self.project, moved, 'neko-to-maboss', SESSION, ['A'])
        companion.write_bytes(companion.read_bytes().replace(b'"state_id":0', b'"state_id":1', 1))
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            gate.verify_manifest(self.project, data, 'neko-to-maboss', SESSION, ['A'])
        repinned = copy.deepcopy(data)
        repinned['curation_file']['sha256'] = hashlib.sha256(companion.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, 'session/state'):
            gate.verify_manifest(self.project, repinned, 'neko-to-maboss', SESSION, ['A'])

    def test_maboss_21_readout_capture_with_curated_parent_is_gate_verifiable(self):
        parent_path, parent = self.neko()
        path, model = self.maboss(parent_path, parent)
        verify_handoff_manifest(model)
        captured = self.capture_maboss(path)
        target = captured.parent
        self.assertTrue((target / 'parent/curation/export.abc.history.json').is_file())
        relocation = json.loads((target / 'relocation.json').read_text())
        self.assertIn('original backend manifest', relocation['parent_curation_binding'])
        data = json.loads(captured.read_text())
        self.assertEqual(data['readouts'], model.readouts)
        gate.verify_manifest(self.project, data, 'maboss-to-physicell', 'maboss-session', ['A', 'R'])

    def test_maboss_21_without_curated_parent_uses_backend_verifier(self):
        path, model = self.maboss(*self.neko())
        data = json.loads(path.read_text())
        data.pop('parent_manifest')
        data['lineage'] = []
        standalone = path.with_name('standalone.handoff.json')
        standalone.write_text(json.dumps(data))
        from scripts.capture.record_maboss_physicell_handoff import record_maboss
        record_maboss(self.project, None, standalone, 'standalone', artifact_root=self.maboss_root)
        captured = self.project / 'runs/boolean-dynamics-modeler/maboss-session/physicell-handoffs/standalone/import.handoff.json'
        gate.verify_manifest(self.project, json.loads(captured.read_text()), 'maboss-to-physicell', 'maboss-session', ['A', 'R'])

    def gate_local(self, **changes):
        """Gate a MaBoSS 2.1 manifest whose payloads live directly in the project."""
        parent_path, parent = self.neko()
        neko_capture = self.capture_neko(parent_path)
        parent_copy = self.project / neko_capture['upstream_manifest']
        parent_model = NeKoToMaBoSSHandoffManifest.model_validate_json(parent_copy.read_text())
        self.maboss_root = self.project / 'runs/boolean-dynamics-modeler'
        path, _ = self.maboss(parent_copy, parent_model, **changes)
        return gate.verify_manifest(self.project, json.loads(path.read_text()), 'maboss-to-physicell', 'maboss-session')

    def test_gate_rejects_undeclared_nodes_feedback_and_reclassification(self):
        core = 'Node A { logic = A; }\nNode B { logic = NOT (A); }\n'
        cases = (
            (dict(bnd=core + 'Node R { logic = A & !B; }\nNode X { logic = A; }\n'), 'BND nodes do not match'),
            (dict(bnd=core + 'Node R { logic = A & !B; }\nNode X { logic = A; }\n', nodes=['A', 'B', 'R', 'X']), 'nodes disagree'),
            (dict(bnd='Node A { logic = A | R; }\nNode B { logic = NOT (A); }\nNode R { logic = A & !B; }\n'), 'feeds back'),
            # B keeps a valid readout rule and isolation, but is a NeKo core node.
            (dict(bnd='Node A { logic = A; }\nNode B { logic = A; }\nNode R { logic = A; }\n',
                  readouts={'B': {'origin': 'readout', 'rule': 'A', 'explanation': 's'}}, outputs=['A']), 'reclassify'),
        )
        for changes, message in cases:
            with self.subTest(message=message):
                self.setUp()
                with self.assertRaisesRegex(ValueError, message):
                    self.gate_local(**changes)
        self.setUp()
        self.gate_local()  # the unmodified fixture passes the same route


if __name__ == '__main__':
    unittest.main()
