"""Real child-process fixtures exercise the shared runtime; no model servers or LLMs."""
from __future__ import annotations

import contextlib
import copy
import io
import json
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from scripts.codex import run_specialist as cli
from scripts.codex.dispatcher.manager import TaskManager
from scripts.codex.launcher_config import SPECIALISTS
from scripts.codex.specialist_runtime import executor
from scripts.codex.specialist_runtime.models import SpecialistInvocationRequest as Request
from scripts.codex.ode_artifacts import digest
from scripts.codex.ode_evidence import write_ode_report
from tests.codex.test_ode_integration import fixture as ode_fixture, refresh, evidence

FAKE = r'''
import json, pathlib, sys, time
root = pathlib.Path(__file__).parent
with (root/'commands.jsonl').open('a') as log:
    log.write(json.dumps(sys.argv[1:])+'\n')
settings = json.loads((root/'response.json').read_text())
if '--version' in sys.argv:
    print('codex-cli 0.153.0'); sys.exit(0)
if 'list' in sys.argv:
    print(json.dumps(settings['inventory'])); sys.exit(0)
output = pathlib.Path(sys.argv[sys.argv.index('--output-last-message')+1])
print(json.dumps({'type':'thread.started'}), flush=True)
print(json.dumps({'type':'turn.started'}), flush=True)
if settings.get('slow'): time.sleep(30)
if settings.get('malformed'): print('not json TOKEN=fixture-secret', flush=True)
output.write_text(json.dumps(settings['handoff']))
print(json.dumps({'type':'turn.completed'}), flush=True)
sys.exit(settings.get('return_code', 0))
'''


def blocked(role, session, kind=None):
    stages = {'network_curator': 'neko_network', 'boolean_dynamics_modeler': 'maboss_dynamics',
              'multicellular_configurator': 'physicell_configuration', 'ode_modeler': 'biomass_ode',
              'literature_reviewer': 'literature_review'}
    h = {'schema_version': 1, 'specialist': role, 'stage': stages[role], 'status': 'blocked',
         'session_id': session, 'derived_from_session_id': None, 'actions': ['software fixture'],
         'assumptions': [], 'decisions_required': ['synthetic blocker'], 'artifacts': [],
         'validation': {'checks': ['synthetic fixture only'], 'passed': False},
         'recommended_next_stage': None}
    if kind is not None:
        h['review_kind'] = kind
    return h


class ODERuntimeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.binary = self.root/'fake-codex'
        self.binary.write_text('#!' + sys.executable + '\n' + FAKE)
        self.binary.chmod(0o700)
        self.profile = self.root/'profile.toml'
        self.settings = self.root/'response.json'
        self.commands = self.root/'commands.jsonl'
        for name, value in (('PROJECT_ROOT', self.root),
                            ('resolve_codex_executable', lambda value: str(self.binary)),
                            ('profile_path', lambda name: self.profile)):
            patch = mock.patch.object(executor, name, value)
            patch.start(); self.addCleanup(patch.stop)
        patch = mock.patch.object(cli, 'PROJECT_ROOT', self.root)
        patch.start(); self.addCleanup(patch.stop)
        self.manager = TaskManager(self.root)
        self.addCleanup(self.manager.close)

    def configure(self, role='ode_modeler', kind=None, *, backend=None, handoff=None, **settings):
        server = SPECIALISTS[role][1]
        if role == 'literature_reviewer':
            server = 'pubmed' if backend == 'pubmed' else None
        self.profile.write_text(f'[mcp_servers.{server}]\ncommand="fixture-server"\n' if server else '[mcp_servers]\n')
        data = {'inventory': [{'name': server, 'enabled': True}] if server else [],
                'handoff': handoff or blocked(role, 'fixture-session', kind)}
        data.update(settings)
        self.settings.write_text(json.dumps(data))
        self.commands.write_text('')

    def finish(self, task):
        task_id = task['task_id']
        self.manager.workers[task_id][0].join(5)
        self.assertFalse(self.manager.workers[task_id][0].is_alive(), 'fixture worker did not finish')
        return self.manager.get(task_id)

    def provenance(self, path):
        return json.loads((self.root/path/'provenance.json').read_text())

    def invocations(self):
        return [json.loads(line) for line in self.commands.read_text().splitlines()]

    @staticmethod
    def config_vector(command):
        return [command[i+1] for i, arg in enumerate(command[:-1]) if arg == '-c']

    def test_cli_dispatcher_equivalence_for_every_role_and_evidence_mode(self):
        modes = [(role, None, None) for role in SPECIALISTS if role != 'literature_reviewer']
        modes += [('literature_reviewer', 'edge', 'pubmed'), ('literature_reviewer', 'ode', 'pubmed'),
                  ('literature_reviewer', 'ode', 'web_search')]
        for role, kind, backend in modes:
            with self.subTest(role=role, kind=kind, backend=backend):
                self.configure(role, kind, backend=backend)
                task = 'Bounded software fixture.\nPreserve exact input.  \n'
                tools = ('inspect_model',) if role == 'ode_modeler' else ()
                request = Request(role, task, 'fixture-session', tools,
                                  backend == 'web_search', review_kind=kind)
                record = self.finish(self.manager.start(request))
                self.assertEqual(record['execution_state'], 'succeeded', record)
                self.assertEqual(record['handoff_status'], 'blocked')
                args = [role, '--prompt', task, '--record-session-id', 'fixture-session']
                if kind:
                    args += ['--review-kind', kind]
                if backend == 'web_search':
                    args += ['--allow-web-search']
                for tool in tools:
                    args += ['--approve-tool', tool]
                results = []
                execute = executor.execute
                def capture(*a, **kw):
                    result = execute(*a, **kw)
                    results.append(result)
                    return result
                with mock.patch.object(executor, 'execute', side_effect=capture), contextlib.redirect_stdout(io.StringIO()):
                    code = cli.main(args)
                self.assertEqual(code, 0)
                result = results[0]
                self.assertEqual(record['handoff'], result.handoff)
                self.assertNotEqual(record['invocation_id'], result.invocation_id)
                self.assertEqual(record['review_kind'], request.review_kind)
                left, right = self.provenance(record['artifact_dir']), self.provenance(result.artifact_dir)
                for key in ('specialist', 'review_kind', 'record_session_id', 'profile', 'transport', 'effective_mcp_inventory',
                            'apps_enabled', 'sandbox', 'ephemeral', 'mcp_enabled', 'approved_mcp_tools',
                            'web_search_enabled', 'literature_backend', 'prompt_sha256', 'process_exit_code'):
                    self.assertEqual(left[key], right[key], key)
                self.assertEqual(left['dispatcher_task_id'], record['task_id'])
                self.assertIsNone(right['dispatcher_task_id'])
                for directory in (self.root/record['artifact_dir'], result.artifact_dir):
                    self.assertEqual((directory/'task.txt').read_text(), task)
                    self.assertEqual(json.loads((directory/'handoff.json').read_text()), result.handoff)
                calls = self.invocations()
                self.assertEqual(len(calls), 6)  # version, inventory, execution on both routes
                for inventory, execution in ((calls[1], calls[2]), (calls[4], calls[5])):
                    self.assertEqual(self.config_vector(inventory), self.config_vector(execution))
                    self.assertIn('features.apps=false', execution)
                    self.assertIn('--ephemeral', execution)
                    self.assertIn('--strict-config', execution)
                    self.assertIn('mcp_servers.specialist_dispatcher={"command"="__disabled_specialist_dispatcher__","enabled"=false}', execution)
                self.assertEqual(self.config_vector(calls[2]), self.config_vector(calls[5]))
                self.assertEqual(calls[2][-1], calls[5][-1])

    def test_completed_ode_artifacts_pass_through_shared_runtime(self):
        handoff, _ = ode_fixture(self.root)
        self.configure(handoff=handoff)
        record = self.finish(self.manager.start(Request('ode_modeler', 'inspect fixture', 'bio-session')))
        self.assertEqual(record['execution_state'], 'succeeded', record)
        self.assertEqual(record['handoff'], handoff)
        self.assertIn('runs/ode-modeler/bio-session/specialist-invocations', record['artifact_dir'])

    def test_handoff_mode_identity_contract_and_integrity_mismatches_fail_closed(self):
        valid, revision = ode_fixture(self.root)
        cases = []
        for field, value in (('specialist', 'network_curator'), ('session_id', 'wrong-session')):
            invalid = copy.deepcopy(valid); invalid[field] = value
            cases.append((Request('ode_modeler', 'inspect', 'bio-session'), invalid))
        invalid = copy.deepcopy(valid); invalid['ode']['contract_version'] = 1
        cases.append((Request('ode_modeler', 'inspect', 'bio-session'), invalid))
        for requested, returned in (('edge', 'ode'), ('ode', 'edge')):
            cases.append((Request('literature_reviewer', 'inspect', 'bio-session', allow_web_search=True, review_kind=requested),
                          blocked('literature_reviewer', 'bio-session', returned)))
        for request, invalid in cases:
            with self.subTest(role=request.specialist, kind=request.review_kind, invalid=invalid):
                self.configure(request.specialist, request.review_kind, handoff=invalid)
                record = self.finish(self.manager.start(request))
                self.assertEqual(record['execution_state'], 'failed', record)
                self.assertEqual(record['return_code'], 3)
                self.assertIsNone(record['handoff'])
                self.assertTrue(record['error'])
                self.assertTrue((self.root/record['artifact_dir']/'provenance.json').is_file())
                expected_root = 'runs/network-curator/' if request.review_kind == 'edge' else 'runs/ode-modeler/'
                self.assertTrue(record['artifact_dir'].startswith(expected_root))
        (revision/'model.txt').write_text('tampered fixture')
        self.configure(handoff=valid)
        record = self.finish(self.manager.start(Request('ode_modeler', 'inspect', 'bio-session')))
        self.assertEqual(record['execution_state'], 'failed', record)
        self.assertIsNone(record['handoff'])

    def test_ode_process_and_recording_failures_do_not_publish_handoffs(self):
        for settings, code in (({'return_code': 7}, 7), ({'malformed': True}, 3)):
            with self.subTest(settings=settings):
                self.configure(**settings)
                record = self.finish(self.manager.start(Request('ode_modeler', 'inspect', 'fixture-session')))
                self.assertEqual(record['execution_state'], 'failed', record)
                self.assertEqual(record['return_code'], code)
                self.assertIsNone(record['handoff'])
                events = self.root/record['event_stream']
                self.assertNotIn('fixture-secret', events.read_text())
        self.configure()
        with mock.patch.object(executor, 'record_invocation', side_effect=OSError('fixture disk failure')):
            record = self.finish(self.manager.start(Request('ode_modeler', 'inspect', 'fixture-session')))
        self.assertEqual(record['execution_state'], 'failed', record)
        self.assertIsNone(record['handoff'])

    def test_unsafe_ode_inventory_never_executes_child(self):
        for prohibited in ('neko', 'maboss', 'physicell', 'specialist_dispatcher', 'codex_apps'):
            with self.subTest(prohibited=prohibited):
                self.configure(inventory=[{'name': 'biomass', 'enabled': True}, {'name': prohibited, 'enabled': True}])
                record = self.finish(self.manager.start(Request('ode_modeler', 'inspect', 'fixture-session')))
                self.assertEqual(record['execution_state'], 'failed', record)
                self.assertEqual(record['return_code'], 2)
                self.assertEqual(len(self.invocations()), 2)
                self.assertIsNone(record['event_stream'])

    def test_ode_and_ode_evidence_children_can_be_cancelled_without_resumption(self):
        for role, kind in (('ode_modeler', None), ('literature_reviewer', 'ode')):
            with self.subTest(role=role):
                self.configure(role, kind, slow=True)
                task = self.manager.start(Request(role, 'inspect', 'fixture-session', allow_web_search=kind is not None, review_kind=kind))
                deadline = time.monotonic()+3
                while time.monotonic() < deadline:
                    if any(e['type'] == 'thread.started' for e in self.manager.events(task['task_id'])['events']):
                        break
                    time.sleep(.01)
                else:
                    self.fail('child did not report startup')
                self.manager.cancel(task['task_id'])
                record = self.finish(task)
                self.assertEqual(record['execution_state'], 'cancelled', record)
                self.assertEqual(record['return_code'], 130)
                self.assertIsNone(record['handoff'])
                self.assertEqual(self.provenance(record['artifact_dir'])['review_kind'], kind)
                self.assertEqual(len(self.invocations()), 3)

    def test_cli_windows_bridge_forwards_review_mode_and_rejects_invalid_scope(self):
        # Use the repository's accepted config keys; no subprocess is launched.
        from scripts.codex.launcher_config import WINDOWS_CONFIG_FIELDS
        config = {key: ('Ubuntu' if 'distribution' in key else '/fixture') for key in WINDOWS_CONFIG_FIELDS}
        with mock.patch.object(cli, 'load_windows_launcher_config', return_value=config), \
             mock.patch.object(cli, 'subprocess') as process:
            process.DEVNULL = -3
            process.Popen.return_value.wait.return_value = 0
            code = cli.main(['literature_reviewer', '--prompt', 'inspect', '--transport', 'wsl',
                             '--review-kind', 'ode', '--record-session-id', 'bio-session'])
        self.assertEqual(code, 0)
        command = process.Popen.call_args.args[0]
        self.assertEqual(command[command.index('--review-kind')+1], 'ode')
        self.assertEqual(command[command.index('--record-session-id')+1], 'bio-session')
        with mock.patch.object(executor, 'execute') as run:
            for args in (['ode_modeler', '--review-kind', 'edge'], ['literature_reviewer', '--review-kind', 'ode']):
                self.assertEqual(cli.main(args + ['--prompt', 'inspect']), 2)
            run.assert_not_called()

    def test_provisional_review_bundle_preserves_authority_without_stage_acceptance(self):
        h, revision = ode_fixture(self.root)
        decisions = self.root/'DECISIONS.md'
        decisions.write_text('Decision: draft-workflow\nStatus: approved\nSession: bio-session\nAction: preserve_ode_candidates\n')
        snapshot = self.root/'runs/ode-modeler/bio-session/workflow authorization.md'
        snapshot.write_bytes(decisions.read_bytes())
        h['ode']['workflow_authorization'] = {'path': snapshot.relative_to(self.root).as_posix(),
                                             'sha256': digest(snapshot), 'decision_id': 'draft-workflow', 'reviewed_by': 'researcher'}
        bundle = revision.parent/'model.zip'
        with zipfile.ZipFile(bundle, 'w') as archive:
            for path in revision.rglob('*'):
                if path.is_file():
                    archive.write(path, 'model/' + path.relative_to(revision).as_posix())
            archive.writestr('requirements.txt', 'fixture-only\n')
            archive.writestr('run_simulation.py', '# fixture only\n')
        h['ode'].update(export_status='provisional', bundle_path=bundle.relative_to(self.root).as_posix())
        h.update(status='needs_approval', decisions_required=['Inspect synthetic candidate'], recommended_next_stage=None)
        refresh(self.root, h)
        self.configure(handoff=h)
        before = decisions.read_bytes()
        record = self.finish(self.manager.start(Request('ode_modeler', 'inspect candidate', 'bio-session')))
        self.assertEqual(record['execution_state'], 'succeeded', record)
        self.assertEqual(record['handoff_status'], 'needs_approval')
        self.assertEqual(record['handoff'], h)
        saved = json.loads((self.root/record['artifact_dir']/'handoff.json').read_text())
        self.assertEqual(saved, h)
        self.assertEqual(decisions.read_bytes(), before)
        self.assertIsNone(saved['recommended_next_stage'])
        self.assertNotIn('export_approval', saved['ode'])

    def test_completed_ode_evidence_uses_claim_contract_and_session_root(self):
        draft = self.root/'claim.md'
        draft.write_text(evidence())
        entry = write_ode_report(self.root, 'bio-session', 'binding', draft)
        h = blocked('literature_reviewer', 'bio-session', 'ode')
        h.update(status='completed', decisions_required=[], validation={'checks': ['report format'], 'passed': True},
                 artifacts=[entry])
        self.configure('literature_reviewer', 'ode', backend='pubmed', handoff=h)
        request = Request('literature_reviewer', 'review binding fixture', 'bio-session', allow_web_search=True, review_kind='ode')
        record = self.finish(self.manager.start(request))
        self.assertEqual(record['execution_state'], 'succeeded', record)
        self.assertEqual(record['handoff'], h)
        self.assertTrue(record['artifact_dir'].startswith('runs/ode-modeler/bio-session/'))
        metadata = self.provenance(record['artifact_dir'])
        self.assertEqual(metadata['literature_backend'], 'pubmed')
        self.assertFalse(metadata['web_search_enabled'])
        self.assertNotIn('--search', self.invocations()[-1])
