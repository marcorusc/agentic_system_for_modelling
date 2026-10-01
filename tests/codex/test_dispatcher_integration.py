"""Full dispatcher/runtime path with an actual fake Codex executable."""
from __future__ import annotations
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock
from scripts.codex.specialist_runtime import executor
from scripts.codex.specialist_runtime.models import SpecialistInvocationRequest as Request
from scripts.codex.dispatcher.manager import TaskManager
from scripts.codex.launcher_process import stream_jsonl_process

FAKE = r'''
import json, pathlib, sys, time
if '--version' in sys.argv:
    print('codex-cli 0.153.0'); sys.exit(0)
if 'list' in sys.argv:
    print('[{"name":"neko","enabled":true}]'); sys.exit(0)
mode = sys.argv[-1].split('Task:\n')[-1]
output = pathlib.Path(sys.argv[sys.argv.index('--output-last-message')+1])
handoff = {"schema_version":1,"specialist":"network_curator","stage":"neko_network",
"status":"blocked","session_id":None,"derived_from_session_id":None,"actions":["inspected"],
"assumptions":[],"decisions_required":["technical test"],"artifacts":[],
"validation":{"checks":["technical test"],"passed":False},"recommended_next_stage":None}
print(json.dumps({"type":"thread.started"}),flush=True)
print(json.dumps({"type":"turn.started"}),flush=True)
print(json.dumps({"type":"item.started","item":{"id":"t","type":"mcp_tool_call","server":"neko","tool":"inspect"}}),flush=True)
print(json.dumps({"type":"item.completed","item":{"type":"reasoning","text":"private reasoning TOKEN=secret-value"}}),flush=True)
if mode == 'slow': time.sleep(30)
if mode == 'malformed': print('TOKEN=secret-value broken',flush=True)
print(json.dumps({"type":"item.completed","item":{"id":"t","type":"mcp_tool_call","server":"neko","tool":"inspect","result":{"access_token":"secret-value"}}}),flush=True)
output.write_text('not a handoff' if mode == 'invalid' else json.dumps(handoff))
print(json.dumps({"type":"turn.completed"}),flush=True)
sys.exit(7 if mode == 'nonzero' else 0)
'''

class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.binary = self.root/'fake-codex'
        self.binary.write_text('#!'+sys.executable+'\n'+FAKE)
        self.binary.chmod(0o700)
        self.profile = self.root/'profile.toml'
        self.profile.write_text('[mcp_servers.neko]\ncommand="fake"\n')
        for name,value in (('PROJECT_ROOT',self.root),('resolve_codex_executable',lambda value: str(self.binary)),('profile_path',lambda profile: self.profile)):
            patch=mock.patch.object(executor,name,value)
            patch.start(); self.addCleanup(patch.stop)
        def stream(*args, **kwargs): return stream_jsonl_process(*args, **kwargs, heartbeat_interval=.03)
        patch=mock.patch.object(executor,'stream_jsonl_process',stream)
        patch.start(); self.addCleanup(patch.stop)
        self.manager=TaskManager(self.root)
        self.addCleanup(self.manager.close)

    def run_task(self,mode):
        started=time.monotonic()
        task=self.manager.start(Request('network_curator',mode))
        self.assertLess(time.monotonic()-started,.5)
        return task['task_id']

    def finish(self,task_id):
        self.manager.workers[task_id][0].join(5)
        self.assertFalse(self.manager.workers[task_id][0].is_alive())
        return self.manager.get(task_id)

    def test_success_artifacts_and_operational_events(self):
        task_id=self.run_task('success')
        record=self.finish(task_id)
        self.assertEqual(record['execution_state'],'succeeded',record)
        self.assertEqual(record['handoff_status'],'blocked')
        artifact=self.root/record['artifact_dir']
        for name in ('task.txt','events.jsonl','specialist-output.txt','handoff.json','provenance.json'):
            self.assertTrue((artifact/name).is_file(),name)
        self.assertNotIn('secret-value',(artifact/'events.jsonl').read_text())
        events=self.manager.events(task_id,limit=200)
        self.assertNotIn('private reasoning',json.dumps(events))
        self.assertNotIn('secret-value',json.dumps(events))
        self.assertIn('mcp_tool_call_started',json.dumps(events))
        self.assertIn('mcp_tool_call_completed',json.dumps(events))
        provenance=json.loads((artifact/'provenance.json').read_text())
        self.assertEqual(provenance['dispatcher_task_id'],task_id)

    def test_malformed_handoff_process_and_recording_failures(self):
        for mode,code in (('malformed',3),('invalid',3),('nonzero',7)):
            with self.subTest(mode=mode):
                record=self.finish(self.run_task(mode))
                self.assertEqual(record['execution_state'],'failed',record)
                self.assertEqual(record['return_code'],code)
                self.assertIsNone(record['handoff'])
        with mock.patch.object(executor,'record_invocation',side_effect=OSError('recording failed')):
            record=self.finish(self.run_task('success'))
        self.assertEqual(record['execution_state'],'failed')
        self.assertIsNone(record['handoff'])

    def test_slow_child_heartbeat_query_and_cancellation(self):
        task_id=self.run_task('slow')
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            events=self.manager.events(task_id,limit=200)
            if (any(e['type']=='heartbeat' for e in events['events'])
                    and self.manager.get(task_id)['current_activity'] is not None): break
            time.sleep(.01)
        else: self.fail('heartbeat and active tool were not both observed')
        self.assertEqual(self.manager.get(task_id)['current_activity']['names'],['neko.inspect'])
        self.manager.cancel(task_id)
        record=self.finish(task_id)
        self.assertEqual(record['execution_state'],'cancelled',record)
        self.assertEqual(record['return_code'],130)
        self.assertTrue((self.root/record['artifact_dir']/'provenance.json').exists())

    def test_unsafe_inventory_never_starts_child(self):
        self.binary.write_text(self.binary.read_text().replace('"name":"neko","enabled":true','"name":"maboss","enabled":true'))
        record=self.finish(self.run_task('success'))
        self.assertEqual(record['execution_state'],'failed')
        self.assertIsNone(record['event_stream'])
        self.assertIn('prohibited',record['error'])
