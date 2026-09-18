from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.codex.ode_evidence import validate_ode_report, write_ode_report, ReportValidationError
from scripts.codex.ode_artifacts import digest
from scripts.codex.record_ode_artifacts import record
from scripts.codex.validate_handoff import validate_handoff, HandoffValidationError

REV = 'rev_' + 'a' * 32
TEXT = 'A --> B | kf=0.1 | A=1, B=0\n'


def evidence(claim='binding'):
    return f'''## ODE claim: {claim}
**Claim:** The specified molecular states bind.
**Kind:** mechanism
**Verdict:** insufficient evidence
**Confidence:** low
**Biological context:** Synthetic software test only.

### Evidence summary
No source has established this test claim.
### Sources
[]
### Conflicts
Unknown.
### Reported quantities
[]
### Open questions
Evidence needed.
'''


def fixture(root):
    run = root / 'runs/ode-modeler/bio-session'
    revision = run / 'captures/test' / REV
    (revision / 'generated_model').mkdir(parents=True)
    snapshot = {'document': {'version': 1, 'text': TEXT, 'configuration': {}, 'evidence': {}}, 'coverage': {}}
    contents = {'snapshot.json': json.dumps(snapshot), 'model.txt': TEXT,
                'model_summary.json': json.dumps({'equations': ['-k*A', 'k*A'], 'parameters': {}, 'initials': {}, 'species': ['A', 'B']}),
                'request.json': json.dumps({'operation': 'generate'}), 'generated_model/ode.py': '# synthetic test fixture\n'}
    for name, content in contents.items():
        (revision / name).write_text(content)
    (revision / 'integrity.json').write_text(json.dumps({name: digest(revision/name) for name in contents}))
    ode = {'contract_version': 2, 'input_kind': 'standalone_text', 'standalone_authorized': True,
           'source_sha256': hashlib.sha256(TEXT.encode()).hexdigest(), 'document_version': 1,
           'revision': REV, 'source_identifiers': [], 'evidence_paths': [], 'simulation_paths': [],
           'export_status': 'pending', 'revision_path': revision.relative_to(root).as_posix()}
    h = {'schema_version': 1, 'specialist': 'ode_modeler', 'stage': 'biomass_ode',
         'status': 'completed', 'session_id': 'bio-session', 'derived_from_session_id': None,
         'actions': [], 'assumptions': [], 'decisions_required': [], 'artifacts': [],
         'validation': {'checks': ['fixture integrity'], 'passed': True},
         'recommended_next_stage': 'researcher_approval', 'ode': ode}
    (run/'report.md').write_text('Synthetic fixture, not a biological conclusion.\n')
    refresh(root, h)
    return h, revision


def refresh(root, h):
    run = root/'runs/ode-modeler'/h['session_id']
    keys = ('schema_version', 'specialist', 'stage', 'session_id', 'derived_from_session_id', 'ode')
    (run/'manifest.json').write_text(json.dumps({k: h[k] for k in keys}))
    h['artifacts'] = [{'path': p.relative_to(root).as_posix(), 'sha256': digest(p)}
                      for p in run.rglob('*') if p.is_file()]


class ODEContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.h, self.rev = fixture(self.root)

    def validate(self):
        return validate_handoff(self.h, project_root=self.root)

    def test_standalone_completed_model(self):
        self.validate()

    def neko_input(self):
        from scripts.codex.record_neko_ode_handoff import record_neko
        server = self.root/'neko-server'
        source = server/'artifacts/neko-session'; source.mkdir(parents=True)
        network = source/'network.json'
        network.write_text(json.dumps({'nodes': [{'node_id': 'A'}, {'node_id': 'B'}],
                                       'edges': [{'edge_id': 'e', 'source': 'A', 'target': 'B'}]}))
        manifest = {'handoff_type': 'neko-to-biomass', 'source': {'server': 'NeKo', 'session_id': 'neko-session'},
                    'network_file': {'path': str(network), 'server': 'NeKo', 'session_id': 'neko-session',
                                     'role': 'neko_ode_network', 'sha256': digest(network)}}
        original = source/'manifest.json'; original.write_text(json.dumps(manifest))
        original_bytes = original.read_bytes()
        copied = record_neko(self.root, server, original, 'export1')
        self.assertEqual(original.read_bytes(), original_bytes)
        self.h['ode']['input_kind'] = 'neko'
        self.h['ode']['upstream_manifest'] = copied['upstream_manifest']
        self.h['derived_from_session_id'] = 'neko-session'
        snapshot = json.loads((self.rev/'snapshot.json').read_text())
        snapshot['document']['upstream'] = json.loads((self.root/copied['upstream_manifest']).read_text())
        (self.rev/'snapshot.json').write_text(json.dumps(snapshot))
        inventory = json.loads((self.rev/'integrity.json').read_text())
        inventory['snapshot.json'] = digest(self.rev/'snapshot.json')
        (self.rev/'integrity.json').write_text(json.dumps(inventory))
        refresh(self.root, self.h)
        self.validate()
        return copied

    def test_verified_neko_import_preserves_original_and_relocation(self):
        copied = self.neko_input()
        (self.root/copied['upstream_manifest']).with_name('network.json').write_text('altered')
        with self.assertRaisesRegex(HandoffValidationError, 'network hash'): self.validate()

    def test_recorded_neko_import_cannot_drop_preservation_provenance(self):
        copied = self.neko_input()
        parent = (self.root / copied['upstream_manifest']).parent
        (parent/'relocation.json').unlink()
        (parent/'original.handoff.json').unlink()
        with self.assertRaisesRegex(HandoffValidationError, 'missing artifact'):
            self.validate()

    def test_malformed_upstream_objects_are_typed_rejections(self):
        copied = self.neko_input()
        path = self.root/copied['upstream_manifest']
        original = path.read_text()
        for key in ('source', 'network_file'):
            manifest = json.loads(original)
            manifest[key] = 'malformed'
            path.write_text(json.dumps(manifest))
            with self.subTest(key=key), self.assertRaises(HandoffValidationError):
                self.validate()
            path.write_text(original)

    def test_missing_lineage_and_wrong_type(self):
        self.h['ode']['input_kind'] = 'neko'
        with self.assertRaises(HandoffValidationError): self.validate()
        self.h['derived_from_session_id'] = 'neko-session'
        parent = self.root/'runs/network-curator/neko-session'
        parent.mkdir(parents=True)
        manifest = {'handoff_type': 'neko-to-maboss', 'source': {'session_id': 'neko-session'}}
        (parent/'upstream.json').write_text(json.dumps(manifest))
        self.h['ode']['upstream_manifest'] = 'runs/network-curator/neko-session/upstream.json'
        refresh(self.root, self.h)
        with self.assertRaisesRegex(HandoffValidationError, 'wrong upstream'): self.validate()

    def test_standalone_requires_authorization_and_source_hash(self):
        for key in ('standalone_authorized', 'source_sha256'):
            h = copy.deepcopy(self.h)
            del self.h['ode'][key]
            with self.assertRaises(HandoffValidationError): self.validate()
            self.h = h

    def test_conversational_reactions_source(self):
        self.h['ode']['input_kind'] = 'reactions'
        self.h['ode']['construction_request'] = 'Explicit synthetic A to B conversion.'
        refresh(self.root, self.h)
        self.validate()

    def test_missing_metadata_and_stale_document(self):
        self.h['ode']['document_version'] = 2
        refresh(self.root, self.h)
        with self.assertRaisesRegex(HandoffValidationError, 'stale'): self.validate()
        del self.h['ode']
        with self.assertRaises(HandoffValidationError): self.validate()

    def test_altered_revision_even_if_envelope_rehashed(self):
        (self.rev/'model.txt').write_text('tampered')
        refresh(self.root, self.h)
        with self.assertRaisesRegex(HandoffValidationError, 'integrity mismatch'): self.validate()

    def test_missing_file_and_unlisted_file(self):
        self.h['artifacts'] = [a for a in self.h['artifacts'] if not a['path'].endswith('model.txt')]
        with self.assertRaises(HandoffValidationError): self.validate()
        (self.rev/'unexpected.py').write_text('tampered')
        refresh(self.root, self.h)
        with self.assertRaisesRegex(HandoffValidationError, 'cover all'): self.validate()

    def test_wrong_revision_and_other_session(self):
        for key, value in [('revision', 'rev_'+'b'*32), ('revision_path', 'runs/ode-modeler/other/'+REV)]:
            old = self.h['ode'][key]
            self.h['ode'][key] = value
            refresh(self.root, self.h)
            with self.assertRaises(HandoffValidationError): self.validate()
            self.h['ode'][key] = old

    def test_export_requires_matching_revision_approval_and_bundle(self):
        self.h['ode']['export_status'] = 'exported'
        refresh(self.root, self.h)
        with self.assertRaises(HandoffValidationError): self.validate()
        decisions = self.root/'DECISIONS.md'
        decisions.write_text(f'Decision: export-test\nStatus: approved\nSession: bio-session\nRevision: {REV}\nAction: export_model_bundle\n')
        approval = self.root/'runs/ode-modeler/bio-session/export-approval.md'
        approval.write_bytes(decisions.read_bytes())
        self.h['ode']['export_approval'] = {'decision_id': 'export-test', 'sha256': digest(approval),
                                           'path': approval.relative_to(self.root).as_posix()}
        bundle = self.rev.parent/'model.zip'
        with zipfile.ZipFile(bundle, 'w') as z:
            for p in self.rev.rglob('*'):
                if p.is_file(): z.write(p, 'model/'+p.relative_to(self.rev).as_posix())
            z.writestr('requirements.txt', 'biomass==0.14.0\n')
            z.writestr('run_simulation.py', '# test\n')
        self.h['ode']['bundle_path'] = bundle.relative_to(self.root).as_posix()
        refresh(self.root, self.h)
        self.validate()
        decisions.write_text(decisions.read_text()+'\nAn unrelated later decision.\n')
        self.validate()  # Append-only scientific decisions do not invalidate an exported model.
        decisions.write_text(decisions.read_text().replace(REV, 'rev_'+'c'*32))
        refresh(self.root, self.h)
        with self.assertRaisesRegex(HandoffValidationError, 'matching recorded'): self.validate()

    def test_simulation_missing_results(self):
        self.h['ode']['simulation_paths'] = ['runs/ode-modeler/bio-session/simulation.json']
        refresh(self.root, self.h)
        with self.assertRaises(HandoffValidationError): self.validate()

    def test_simulation_requires_successful_report_and_named_trajectories(self):
        run = self.root/'runs/ode-modeler/bio-session/simulate_test'; run.mkdir()
        (run/'request.json').write_text(json.dumps({'revision': REV}))
        report = {'numerical_valid': True, 'conditions': [{'name': 'test'}], 'time_span': [0, 1]}
        (run/'simulation.json').write_text(json.dumps(report))
        for name in ('species.csv', 'observables.csv'):
            (run/name).write_text('condition,time,A\ntest,0,1\ntest,1,0.9\n')
        self.h['ode']['simulation_paths'] = [(run/'simulation.json').relative_to(self.root).as_posix()]
        refresh(self.root, self.h); self.validate()
        report['numerical_valid'] = False
        (run/'simulation.json').write_text(json.dumps(report))
        refresh(self.root, self.h)
        with self.assertRaisesRegex(HandoffValidationError, 'successful'): self.validate()
        report['numerical_valid'] = True
        (run/'simulation.json').write_text(json.dumps(report))
        (run/'species.csv').rename(run/'unrelated.csv')
        refresh(self.root, self.h)
        with self.assertRaisesRegex(HandoffValidationError, 'species and observable'): self.validate()

    def test_failed_validation_cannot_complete(self):
        self.h['validation']['passed'] = False
        with self.assertRaises(HandoffValidationError): self.validate()


class ODEEvidenceTests(unittest.TestCase):
    def test_evidence_content(self):
        validate_ode_report(evidence(), 'binding')
        for content in (evidence().replace('insufficient evidence', 'supported'),
                        evidence().replace('mechanism', 'invented'),
                        evidence().replace('### Conflicts', '### Bad heading')):
            with self.assertRaises(ReportValidationError): validate_ode_report(content, 'binding')

    def test_quantities_require_source_links_and_units_field(self):
        source = {'pmid': '123', 'doi': None, 'location': 'Table 1', 'access': 'full-text',
                  'limitations': 'Synthetic test citation', 'context': 'Test', 'finding': 'Test', 'stance': 'supports'}
        quantity = {'name': 'k', 'value': '0.1', 'units': None, 'source': '123', 'location': 'Table 1'}
        content = evidence().replace('mechanism', 'quantity').replace('insufficient evidence', 'supported')
        content = content.replace('### Sources\n[]', '### Sources\n'+json.dumps([source]))
        content = content.replace('### Reported quantities\n[]', '### Reported quantities\n'+json.dumps([quantity]))
        validate_ode_report(content, 'binding')
        with self.assertRaises(ReportValidationError):
            validate_ode_report(content.replace('"source": "123"', '"source": "999"'), 'binding')

    def test_immutable_write_traversal_symlinks_and_review_kind(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            draft = root/'draft.md'; draft.write_text(evidence())
            entry = write_ode_report(root, 'bio-session', 'binding', draft)
            with self.assertRaises(ReportValidationError): write_ode_report(root, 'bio-session', 'binding', draft)
            with self.assertRaises(ReportValidationError): write_ode_report(root, '../escape', 'binding', draft)
            (root/'evidence/reports/alias').symlink_to(root/'evidence/reports/bio-session', target_is_directory=True)
            with self.assertRaises(ReportValidationError): write_ode_report(root, 'alias', 'another', draft)
            h = {'schema_version': 1, 'specialist': 'literature_reviewer', 'stage': 'literature_review',
                 'status': 'completed', 'session_id': 'bio-session', 'derived_from_session_id': None,
                 'review_kind': 'ode', 'actions': [], 'assumptions': [], 'decisions_required': [],
                 'artifacts': [entry], 'validation': {'checks': ['content'], 'passed': True}, 'recommended_next_stage': None}
            validate_handoff(h, project_root=root, expected_review_kind='ode')
            with self.assertRaisesRegex(HandoffValidationError, 'review kind mismatch'):
                validate_handoff(h, project_root=root)
            with self.assertRaises(HandoffValidationError): validate_handoff(h, project_root=root, expected_review_kind='edge')



class ODERecordingTests(unittest.TestCase):
    def test_copy_integrity_scope_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); project = root/'project'; project.mkdir()
            server = root/'BioMASS'; source = server/'artifacts/sid'
            source.mkdir(parents=True); file = source/'test.txt'; file.write_text('original')
            entries = [{'path': str(file), 'session_id': 'sid', 'sha256': digest(file)}]
            result = record(project, server, 'sid', 'capture1', entries)
            self.assertEqual((project/result['artifacts'][0]['path']).read_text(), 'original')
            self.assertEqual(file.read_text(), 'original')
            with self.assertRaises(ValueError): record(project, server, 'sid', 'capture1', entries)
            file.write_text('altered')
            with self.assertRaises(ValueError): record(project, server, 'sid', 'capture2', entries)
            self.assertFalse((project/'runs/ode-modeler/sid/captures/capture2').exists())
            entries[0]['session_id'] = 'other'
            with self.assertRaises(ValueError): record(project, server, 'sid', 'capture3', entries)





class ODEProvisionalTests(unittest.TestCase):
    setUp = ODEContractTests.setUp
    validate = ODEContractTests.validate

    def bundle(self, replacements=None, extra=None):
        replacements = replacements or {}
        bundle = self.rev.parent/'model.zip'
        with zipfile.ZipFile(bundle, 'w') as archive:
            for path in self.rev.rglob('*'):
                if path.is_file():
                    name = 'model/' + path.relative_to(self.rev).as_posix()
                    archive.writestr(name, replacements.get(name, path.read_bytes()))
            archive.writestr('requirements.txt', 'fixture-only\n')
            archive.writestr('run_simulation.py', '# fixture only\n')
            if extra:
                archive.writestr(*extra)
        self.h['ode']['bundle_path'] = bundle.relative_to(self.root).as_posix()
        return bundle

    def authorize_preservation(self):
        text = ('Decision: draft-workflow\nStatus: approved\nSession: bio-session\n'
                'Action: preserve_ode_candidates\nScope: Synthetic fixture candidates only.\n')
        (self.root/'DECISIONS.md').write_text(text)
        snapshot = self.root/'runs/ode-modeler/bio-session/workflow-authorization.md'
        snapshot.write_text(text)
        self.h['ode']['workflow_authorization'] = {
            'decision_id': 'draft-workflow', 'path': snapshot.relative_to(self.root).as_posix(),
            'sha256': digest(snapshot)}

    def provisional(self):
        self.h['ode']['export_status'] = 'provisional'
        self.authorize_preservation()
        self.bundle()
        refresh(self.root, self.h)

    def test_new_version_required_without_reinterpreting_history(self):
        for version in (None, 1, True, '2', 3):
            with self.subTest(version=version):
                self.h['ode']['contract_version'] = version
                with self.assertRaisesRegex(HandoffValidationError, 'contract_version'):
                    self.validate()
        self.h['ode']['contract_version'] = 2
        self.h['specialist'] = 'ode_dynamics_modeler'
        with self.assertRaisesRegex(HandoffValidationError, 'unknown specialist'):
            self.validate()

    def test_provisional_preservation_does_not_grant_acceptance(self):
        self.provisional()
        decisions_before = (self.root/'DECISIONS.md').read_bytes()
        self.validate()
        self.assertNotIn('export_approval', self.h['ode'])
        self.assertEqual((self.root/'DECISIONS.md').read_bytes(), decisions_before)
        self.h['ode']['export_status'] = 'exported'
        refresh(self.root, self.h)
        with self.assertRaisesRegex(HandoffValidationError, 'export_approval'):
            self.validate()

    def test_provisional_requires_existing_workflow_authorization(self):
        self.provisional()
        del self.h['ode']['workflow_authorization']
        refresh(self.root, self.h)
        with self.assertRaisesRegex(HandoffValidationError, 'workflow_authorization'):
            self.validate()

    def test_one_workflow_authorizes_preservation_of_later_candidate(self):
        self.provisional()
        authorization = copy.deepcopy(self.h['ode']['workflow_authorization'])
        new_revision = 'rev_'+'b'*32
        new_path = self.rev.with_name(new_revision)
        self.rev.rename(new_path)
        self.rev = new_path
        self.h['ode']['revision'] = new_revision
        self.h['ode']['revision_path'] = new_path.relative_to(self.root).as_posix()
        self.bundle()
        refresh(self.root, self.h)
        self.validate()
        self.assertEqual(self.h['ode']['workflow_authorization'], authorization)

    def test_needs_approval_still_checks_bundle_and_revision(self):
        self.provisional()
        self.h.update(status='needs_approval', decisions_required=['Review fixture candidate'],
                      recommended_next_stage=None)
        self.validate()
        self.bundle({'model/model.txt': b'tampered'})
        refresh(self.root, self.h)
        with self.assertRaisesRegex(HandoffValidationError, 'selected revision'):
            self.validate()

    def test_unpersisted_authoring_draft_remains_possible(self):
        self.h.update(status='needs_approval', decisions_required=['Review draft'],
                      recommended_next_stage=None, artifacts=[])
        self.h['ode'].pop('revision_path')
        self.h['ode']['revision'] = None
        self.validate()

    def test_draft_cannot_claim_nonexistent_project_artifacts(self):
        self.h.update(status='needs_approval', decisions_required=['Review draft'],
                      recommended_next_stage=None)
        self.h['ode'].pop('revision_path')
        self.h['artifacts'] = [{'path': 'runs/ode-modeler/bio-session/missing.md', 'sha256': '0'*64}]
        with self.assertRaisesRegex(HandoffValidationError, 'existing regular file'):
            self.validate()
        # A server revision alone can be recorded before project capture.
        self.h['artifacts'] = []
        self.validate()

    def test_bundle_file_and_directory_prefixes_cannot_collide(self):
        self.provisional()
        for name in ('model', 'run_simulation.py/child'):
            self.bundle(extra=(name, 'conflict'))
            refresh(self.root, self.h)
            with self.subTest(name=name), self.assertRaisesRegex(HandoffValidationError, 'paths conflict'):
                self.validate()

    def test_malformed_snapshot_fields_are_typed_rejections(self):
        path = self.rev/'snapshot.json'
        original = path.read_text()
        for key, value in (('source_file', 'malformed'), ('text', []), ('version', True)):
            snapshot = json.loads(original)
            snapshot['document'][key] = value
            path.write_text(json.dumps(snapshot))
            inventory = json.loads((self.rev/'integrity.json').read_text())
            inventory['snapshot.json'] = digest(path)
            (self.rev/'integrity.json').write_text(json.dumps(inventory))
            refresh(self.root, self.h)
            with self.subTest(key=key), self.assertRaises(HandoffValidationError):
                self.validate()

    def test_pending_status_cannot_hide_bundle_or_approval(self):
        self.bundle()
        refresh(self.root, self.h)
        with self.assertRaisesRegex(HandoffValidationError, 'bundle_path'):
            self.validate()
        self.h['ode'].pop('bundle_path')
        self.h['ode']['export_approval'] = {'decision_id': 'unverified'}
        with self.assertRaisesRegex(HandoffValidationError, 'cannot claim'):
            self.validate()

    def test_invalid_bundle_contents_rejected_even_after_envelope_rehash(self):
        self.provisional()
        for replacements, extra in (
            ({'model/integrity.json': b'{}'}, None),
            ({}, ('model/hidden.py', 'unexpected')),
            ({}, ('../outside', 'traversal')),
            ({}, ('/absolute', 'absolute')),
        ):
            with self.subTest(replacements=replacements, extra=extra):
                self.bundle(replacements, extra)
                refresh(self.root, self.h)
                with self.assertRaises(HandoffValidationError):
                    self.validate()
        bundle = self.bundle()
        bundle.write_bytes(b'not a zip')
        refresh(self.root, self.h)
        with self.assertRaisesRegex(HandoffValidationError, 'ZIP'):
            self.validate()

    def test_symlink_bundle_member_is_rejected(self):
        self.provisional()
        info = zipfile.ZipInfo('link')
        info.create_system = 3
        info.external_attr = 0o120777 << 16
        self.bundle(extra=(info, 'model/model.txt'))
        refresh(self.root, self.h)
        with self.assertRaisesRegex(HandoffValidationError, 'unsafe bundle member'):
            self.validate()

    def test_nested_integrity_file_must_be_in_inventory(self):
        (self.rev/'generated_model/integrity.json').write_text('{}')
        refresh(self.root, self.h)
        with self.assertRaisesRegex(HandoffValidationError, 'cover all'):
            self.validate()

    def test_generated_python_syntax_is_checked_without_execution(self):
        generated = self.rev/'generated_model/ode.py'
        generated.write_text('raise RuntimeError("must never execute")\n')
        inventory = json.loads((self.rev/'integrity.json').read_text())
        inventory['generated_model/ode.py'] = digest(generated)
        (self.rev/'integrity.json').write_text(json.dumps(inventory))
        refresh(self.root, self.h)
        self.validate()
        generated.write_text('def invalid(:\n')
        inventory['generated_model/ode.py'] = digest(generated)
        (self.rev/'integrity.json').write_text(json.dumps(inventory))
        refresh(self.root, self.h)
        with self.assertRaisesRegex(HandoffValidationError, 'invalid syntax'):
            self.validate()

    def test_duplicate_fields_and_nonfinite_json_are_rejected(self):
        path = self.rev/'snapshot.json'
        original = path.read_text()
        for value in ('{"document": {}, "document": []}', original.replace('"coverage": {}', '"coverage": NaN')):
            path.write_text(value)
            inventory = json.loads((self.rev/'integrity.json').read_text())
            inventory['snapshot.json'] = digest(path)
            (self.rev/'integrity.json').write_text(json.dumps(inventory))
            refresh(self.root, self.h)
            with self.subTest(value=value), self.assertRaisesRegex(HandoffValidationError, 'JSON'):
                self.validate()

    def test_workflow_authorization_action_must_match_exactly(self):
        self.provisional()
        decisions = self.root/'DECISIONS.md'
        decisions.write_text(decisions.read_text().replace('preserve_ode_candidates', 'preserve_ode_candidates_other'))
        with self.assertRaisesRegex(HandoffValidationError, 'matching recorded'):
            self.validate()

    def test_no_ode_transition_can_skip_researcher_review(self):
        self.provisional()
        for stage in ('physicell_configuration', 'maboss_dynamics', 'ode_simulation'):
            self.h['recommended_next_stage'] = stage
            with self.assertRaisesRegex(HandoffValidationError, 'approval gate'):
                self.validate()


if __name__ == '__main__': unittest.main()
