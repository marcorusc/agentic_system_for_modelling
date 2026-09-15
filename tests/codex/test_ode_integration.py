from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
import io
from contextlib import redirect_stdout
from unittest import mock
from pathlib import Path

from scripts.codex.ode_evidence import validate_ode_report, write_ode_report, ReportValidationError
from scripts.codex.ode_artifacts import digest
from scripts.codex.record_ode_artifacts import record
from scripts.codex.validate_handoff import validate_handoff, HandoffValidationError
from scripts.codex import launcher_config, launcher_provenance

ROOT = Path(__file__).resolve().parents[2]
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
    ode = {'input_kind': 'standalone_text', 'standalone_authorized': True,
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

    def test_verified_neko_import_preserves_original_and_relocation(self):
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
        (self.root/copied['upstream_manifest']).with_name('network.json').write_text('altered')
        with self.assertRaisesRegex(HandoffValidationError, 'network hash'): self.validate()

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
            with self.assertRaises(HandoffValidationError): validate_handoff(h, project_root=root, expected_review_kind='edge')

    def test_claude_guard_validates_content_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root/'evidence/reports/bio-session/ode/binding.md'
            def guard(content):
                return subprocess.run([sys.executable, str(ROOT/'.claude/scripts/literature_file_guard.py')],
                    input=json.dumps({'tool_name': 'Write', 'tool_input': {'file_path': str(path), 'content': content}}),
                    text=True, capture_output=True, env={**os.environ, 'CLAUDE_PROJECT_DIR': str(root)})
            self.assertEqual(guard(evidence()).returncode, 0)
            self.assertNotEqual(guard('malformed').returncode, 0)
            path.write_text(evidence())
            self.assertNotEqual(guard(evidence()).returncode, 0)


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

    def test_ode_literature_without_backend_records_typed_blocked_result(self):
        from scripts.codex import run_specialist
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = root/'literature.toml'; profile.write_text('[mcp_servers]\n')
            args = run_specialist.parser().parse_args(['literature_reviewer', '--review-kind', 'ode',
                '--record-session-id', 'bio-session', '--prompt', 'Review the literal test claim.'])
            replies = [mock.Mock(stdout='codex-cli 0.153.0', stderr='', returncode=0),
                       mock.Mock(stdout='[]', stderr='', returncode=0)]
            out = io.StringIO()
            with mock.patch.object(run_specialist, 'PROJECT_ROOT', root), \
                 mock.patch.object(run_specialist, 'profile_path', return_value=profile), \
                 mock.patch.object(run_specialist, 'resolve_codex_executable', return_value=sys.executable), \
                 mock.patch.object(run_specialist.subprocess, 'run', side_effect=replies), \
                 redirect_stdout(out):
                self.assertEqual(run_specialist.run_native(args), 0)
            h = json.loads(out.getvalue())
            self.assertEqual(h['review_kind'], 'ode'); self.assertEqual(h['status'], 'blocked')
            invocations = list((root/'runs/ode-modeler/bio-session/specialist-invocations').glob('*/handoff.json'))
            self.assertEqual(len(invocations), 1)
            self.assertFalse((root/'runs/network-curator').exists())

    def test_all_roles_disable_biomass_except_ode_and_ode_review_records_separately(self):
        for role, (_, permitted) in launcher_config.SPECIALISTS.items():
            inventory = [{'name': s, 'enabled': s == permitted} for s in launcher_config.MODELLING_SERVERS]
            launcher_config.validate_mcp_inventory(inventory, role)
            if role != 'ode_modeler':
                inventory[-1]['enabled'] = True
                with self.assertRaises(ValueError): launcher_config.validate_mcp_inventory(inventory, role)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(launcher_provenance.specialist_run_base(root, 'literature_reviewer', 'ode'), root/'runs/ode-modeler')
            self.assertEqual(launcher_provenance.specialist_run_base(root, 'literature_reviewer'), root/'runs/network-curator')


if __name__ == '__main__': unittest.main()
