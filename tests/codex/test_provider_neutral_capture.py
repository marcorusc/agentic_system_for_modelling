import importlib.util
import json
import multiprocessing
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from scripts.capture.index import register_capture
from scripts.capture.record_physicell_config import record_physicell
from scripts.capture.record_invocation import record
from scripts.capture.usage_summary import render

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('guard', ROOT / '.claude/scripts/specialist_report_guard.py')
guard = importlib.util.module_from_spec(spec); spec.loader.exec_module(guard)

def register_worker(project, target):
    register_capture(Path(project), Path(target))

class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = self.root / 'project'; self.project.mkdir()
        self.source = self.root / 'source'; self.source.mkdir()
    def tearDown(self): self.temp.cleanup()
    def transcript(self, session='session-1'):
        path = self.root / 'transcript.jsonl'
        events = [
            {'type':'user','timestamp':'2026-10-05T00:00:00Z','message':{'content':'Inspect only'}},
            {'type':'assistant','timestamp':'2026-10-05T00:00:01Z','message':{'id':'one','usage':{'input_tokens':10,'output_tokens':4},'content':[{'type':'tool_use','id':'call','name':'mcp__neko-agent__status','input':{'session_id':session}}]}},
            {'type':'user','message':{'content':[{'type':'tool_result','tool_use_id':'call','content':json.dumps({'server':'NeKo','session_id':session,'token':'secret'})}]}},
            {'type':'assistant','timestamp':'2026-10-05T00:00:10Z','message':{'id':'two','usage':{'input_tokens':12,'output_tokens':7},'content':[{'type':'text','text':'Full specialist report.'}]}}
        ]
        path.write_text('\n'.join(json.dumps(e) for e in events))
        return path
    def test_physicell_relocates_inputs_preserves_source_and_ignores_disabled(self):
        (self.source / 'a.bnd').write_text('Node A { logic = A; }')
        (self.source / 'a.cfg').write_text('A.istate = 1;')
        (self.source / 'config').mkdir(); (self.source / 'config/cells.csv').write_text('x,y,z,type\n')
        xml=self.source/'settings.xml'
        xml.write_text('<PhysiCell_settings><intracellular><bnd_filename>a.bnd</bnd_filename><cfg_filename>a.cfg</cfg_filename></intracellular><cells enabled="true"><folder>config</folder><filename>cells.csv</filename></cells><missing enabled="false"><filename>absent.csv</filename></missing></PhysiCell_settings>')
        original=xml.read_bytes()
        result=record_physicell(self.project,self.source,xml,'session-1','capture-1')
        target=self.project/result['capture_path']
        self.assertEqual(xml.read_bytes(),original)
        self.assertEqual((target/'original.xml').read_bytes(),original)
        self.assertIn('./config/a.bnd',(target/'package/config/PhysiCell_settings.xml').read_text())
        self.assertTrue((target/'package/config/cells.csv').is_file())
        self.assertIsNone(result['resource']['version'])
        with self.assertRaisesRegex(ValueError,'already exists'):
            record_physicell(self.project,self.source,xml,'session-1','capture-1')
    def test_physicell_rejects_missing_active_escape_and_entities(self):
        xml=self.source/'settings.xml'
        for text in ['<PhysiCell_settings><filename>missing</filename></PhysiCell_settings>',
                     '<PhysiCell_settings><filename>../outside</filename></PhysiCell_settings>',
                     '<!DOCTYPE a><PhysiCell_settings/>']:
            xml.write_text(text)
            with self.assertRaises(ValueError): record_physicell(self.project,self.source,xml,'session-1','capture-1')
        self.assertFalse((self.project/'runs/index.json').exists())
    def test_index_recovery_is_idempotent_and_detects_tampering(self):
        target=self.project/'runs/network-curator/session-1/captures/capture-1';target.mkdir(parents=True)
        (target/'report.md').write_text('evidence')
        register_capture(self.project,target);register_capture(self.project,target)
        self.assertEqual(len(json.loads((self.project/'runs/index.json').read_text())['runs']),1)
        (target/'report.md').write_text('changed')
        with self.assertRaisesRegex(ValueError,'changed'): register_capture(self.project,target)
    def test_concurrent_index_updates_do_not_lose_records(self):
        targets=[]
        for number in range(4):
            target=self.project/f'runs/network-curator/session-1/captures/capture-{number}';target.mkdir(parents=True)
            (target/'file').write_text('data'); targets.append(target)
        processes=[multiprocessing.get_context('fork').Process(target=register_worker,args=(str(self.project),str(t))) for t in targets]
        for p in processes:p.start()
        for p in processes:p.join(5);self.assertEqual(p.exitcode,0)
        self.assertEqual(len(json.loads((self.project/'runs/index.json').read_text())['runs']),4)
    def test_capture_survives_index_failure_and_recovers(self):
        xml=self.source/'settings.xml';xml.write_text('<PhysiCell_settings/>')
        with mock.patch('scripts.capture.record_physicell_config.register_capture', side_effect=OSError('index unavailable')):
            with self.assertRaisesRegex(OSError, 'index unavailable'):
                record_physicell(self.project,self.source,xml,'session-1','capture-1')
        target=self.project/'runs/multicellular-configurator/session-1/configs/capture-1'
        self.assertTrue((target/'capture.json').is_file())
        self.assertFalse((self.project/'runs/index.json').exists())
        result=register_capture(self.project,target)
        self.assertEqual(result['session_id'],'session-1')
    def test_resource_metadata_requires_aware_times_and_preserves_source(self):
        from scripts.capture.resource import record_resource
        metadata=self.root/'resource.json'
        metadata.write_text(json.dumps({'name':'SIGNOR','version':None,'cache_timestamp':'2026-10-05T12:00:00'}))
        stage=self.root/'stage';stage.mkdir()
        with self.assertRaisesRegex(ValueError,'timezone'):record_resource(stage,metadata)
        metadata.write_text(json.dumps({'name':'SIGNOR','version':None,'cache_timestamp':'2026-10-05T12:00:00+09:00'}))
        result=record_resource(stage,metadata)
        self.assertIsNone(result['version'])
        self.assertEqual((stage/'resource.original.json').read_bytes(),metadata.read_bytes())
    def test_report_guard_binds_specialist_session_and_rejects_overwrite(self):
        transcript=self.transcript()
        target=self.project/'runs/network-curator/session-1/report.md'
        payload={'tool_name':'Write','tool_input':{'file_path':str(target),'content':'Report'},'transcript_path':str(transcript)}
        guard.validate(payload,self.project,'network-curator')
        target.write_text('Report')
        with self.assertRaisesRegex(ValueError,'immutable'):guard.validate(payload,self.project,'network-curator')
        payload['tool_input']['file_path']=str(target.with_name('other.md'))
        with self.assertRaises(ValueError):guard.validate(payload,self.project,'network-curator')
        payload['tool_input']['file_path']=str(self.project/'runs/network-curator/other/report.md')
        with self.assertRaisesRegex(ValueError,'absent'):guard.validate(payload,self.project,'network-curator')
    def test_invocation_capture_indexes_usage_and_full_report(self):
        result=record(self.project,{'agent_type':'network-curator','agent_id':'agent-1','agent_transcript_path':str(self.transcript())})
        target=self.project/result['capture_path']
        self.assertEqual(result['usage']['input_tokens'],22)
        self.assertEqual(result['usage']['wall_time_seconds'],10)
        self.assertEqual(result['usage']['tool_calls'],1)
        self.assertIsNone(result['usage']['cost_usd'])
        self.assertIn('Full specialist report.',(target/'final_report.md').read_text())
        self.assertNotIn('secret', (target/'transcript.jsonl').read_text())
        table=render(json.loads((self.project/'runs/index.json').read_text()))
        self.assertIn('| 22 | 11 | 1 | 10.0 | unavailable |',table)
        with self.assertRaisesRegex(ValueError,'already exists'):
            record(self.project,{'agent_type':'network-curator','agent_id':'agent-1','agent_transcript_path':str(self.root/'transcript.jsonl')})
    def test_invocation_ambiguous_session_fails_without_index(self):
        transcript=self.transcript()
        with transcript.open('a') as out:
            out.write('\n'+json.dumps({'type':'assistant','message':{'content':[{'type':'tool_use','id':'call2','name':'mcp__neko__status','input':{'session_id':'other'}}]}}))
        with self.assertRaisesRegex(ValueError,'exactly one'):
            record(self.project,{'agent_type':'network-curator','agent_id':'agent-1','agent_transcript_path':str(transcript)})
        self.assertFalse((self.project/'runs/index.json').exists())


class CodexUsageTests(unittest.TestCase):
    def test_usage_deduplicates_items_and_preserves_unknowns(self):
        from scripts.capture.codex_usage import usage_summary
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            events=[{'type':'item.started','item':{'type':'mcp_tool_call','id':'tool-1'}},
                    {'type':'item.completed','item':{'type':'mcp_tool_call','id':'tool-1'}},
                    {'type':'turn.completed','usage':{'input_tokens':100,'output_tokens':25}}]
            (root/'events.jsonl').write_text('\n'.join(json.dumps(e) for e in events))
            result=usage_summary(root,{'process_elapsed_seconds':1.5})
            self.assertEqual(result['tool_calls'],1)
            self.assertEqual(result['input_tokens'],100)
            self.assertEqual(result['wall_time_seconds'],1.5)
            self.assertIsNone(result['cached_input_tokens'])
            self.assertIsNone(result['cost_usd'])
    def test_recording_failure_preserves_files_and_propagates(self):
        from scripts.codex.launcher_provenance import record_invocation
        with tempfile.TemporaryDirectory() as directory:
            project=Path(directory)
            with mock.patch('scripts.capture.index.register_capture',side_effect=OSError('index unavailable')):
                with self.assertRaisesRegex(OSError,'index unavailable'):
                    record_invocation(project_root=project,specialist='network_curator',prompt='Inspect',
                        final_output='report',handoff={'session_id':'session-1'},expected_session_id='session-1',
                        provenance={},invocation_id='invocation-1')
            self.assertTrue((project/'runs/network-curator/session-1/specialist-invocations/invocation-1/provenance.json').is_file())
    def test_presession_failure_is_preserved_without_index(self):
        from scripts.codex.launcher_provenance import record_invocation
        with tempfile.TemporaryDirectory() as directory:
            project=Path(directory)
            target=record_invocation(project_root=project,specialist='network_curator',prompt='Inspect',
                        final_output='blocked',handoff={'session_id':None,'status':'blocked'},expected_session_id=None,
                        provenance={},invocation_id='invocation-1')
            self.assertIn('_blocked',target.parts)
            self.assertTrue((target/'provenance.json').is_file())
            self.assertFalse((project/'runs/index.json').exists())

if __name__=='__main__':unittest.main()

class CaptureIntegrityReviewTests(CaptureTests):
    def test_only_current_session_fields_authorize_report_paths(self):
        transcript = self.transcript()
        event = {'type':'user','message':{'content':[{'type':'tool_result','tool_use_id':'call',
            'content':json.dumps({'server':'NeKo','session_id':'session-1',
                 'sessions':[{'session_id':'listed-session'}],
                 'lineage':[{'session_id':'upstream-session'}],
                 'artifact':{'session_id':'artifact-session'}})}]}}
        with transcript.open('a') as output: output.write('\n'+json.dumps(event))
        self.assertEqual(guard.transcript_sessions(transcript,'network-curator'), {'session-1'})
        result = record(self.project,{'agent_type':'network-curator','agent_id':'agent-1','agent_transcript_path':str(transcript)})
        self.assertEqual(result['session_id'],'session-1')

    def test_fresh_session_creation_and_wrapped_current_results(self):
        transcript = self.root/'created.jsonl'
        events = [
            {'message':{'content':[{'type':'tool_use','id':'fresh','name':'mcp__maboss-agent__create_session','input':{}}]}},
            {'message':{'content':[{'type':'tool_result','tool_use_id':'fresh','content':[{'type':'text','text':'Session created: scientific-session (set as default)'}]}]}},
            {'message':{'content':[{'type':'tool_use','id':'status','name':'mcp__maboss-agent__status','input':{}}]}},
            {'message':{'content':[{'type':'tool_result','tool_use_id':'status','content':json.dumps({'structuredContent':{'session_id':'scientific-session','server':'MaBoSS','source_manifest':{'session_id':'upstream'}}})}]}},
            {'message':{'content':[{'type':'text','text':'random session_id: fabricated-session'}]}}
        ]
        transcript.write_text('\n'.join(json.dumps(e) for e in events))
        self.assertEqual(guard.transcript_sessions(transcript,'boolean-dynamics-modeler'), {'scientific-session'})

    def test_index_rejects_identity_mismatch_and_bad_usage(self):
        target = self.project/'runs/network-curator/session-1/invocation/agent-1'
        target.mkdir(parents=True)
        meta = target/'invocation.json'
        meta.write_text(json.dumps({'session_id':'other','specialist':'network-curator','invocation_id':'agent-1'}))
        with self.assertRaisesRegex(ValueError,'session identity'):
            register_capture(self.project,target)
        meta.write_text(json.dumps({'session_id':'session-1','specialist':'network-curator','invocation_id':'agent-1'}))
        for usage in ({'input_tokens':-1}, {'output_tokens':True}, {'wall_time_seconds':float('nan')}, {'cost_usd':-1}, {'private':'secret'}):
            with self.assertRaisesRegex(ValueError,'usage'):
                register_capture(self.project,target,usage=usage)
        self.assertFalse((self.project/'runs/index.json').exists())

    def test_literature_invocation_keeps_explicit_role_and_session_lineage(self):
        target = self.project/'runs/network-curator/session-1/specialist-invocations/agent-1'
        target.mkdir(parents=True)
        (target/'handoff.json').write_text(json.dumps({'session_id':'session-1','specialist':'literature_reviewer'}))
        result = register_capture(self.project,target)
        self.assertEqual(result['specialist'],'literature-reviewer')
        self.assertEqual(result['session_id'],'session-1')

    def test_malformed_index_is_not_replaced(self):
        target = self.project/'runs/network-curator/session-1/captures/capture-1'
        target.mkdir(parents=True); (target/'report').write_text('report')
        index = self.project/'runs/index.json'
        for data in ([], {'schema_version':1,'runs':['bad']}):
            index.write_text(json.dumps(data)); original = index.read_bytes()
            with self.assertRaisesRegex(ValueError,'malformed'):
                register_capture(self.project,target)
            self.assertEqual(index.read_bytes(),original)

    def test_repeated_transcript_tool_blocks_do_not_double_count_calls(self):
        transcript = self.transcript()
        events = [json.loads(line) for line in transcript.read_text().splitlines()]
        with transcript.open('a') as output: output.write('\n'+json.dumps(events[1]))
        result = record(self.project,{'agent_type':'network-curator','agent_id':'agent-1','agent_transcript_path':str(transcript)})
        self.assertEqual(result['usage']['tool_calls'],1)
        self.assertEqual(result['usage']['input_tokens'],22)
