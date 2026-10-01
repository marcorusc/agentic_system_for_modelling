"""Reusable capture regression fixtures; no engines, model servers or sessions."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from scripts.codex.ode_capture_inventory import verified_inventory
from scripts.codex.record_ode_artifacts import record
from scripts.codex.ode_artifacts import digest
from tests.codex.test_ode_integration import fixture


class ODEInventoryTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);self.project=self.root/'project';self.project.mkdir()
        handoff,revision=fixture(self.project)
        handoff.update(status='needs_approval',artifacts=[],decisions_required=['Parent capture pending'],recommended_next_stage=None)
        handoff['ode'].pop('revision_path')
        self.session='bio-session';self.server=self.root/'server'
        self.file=self.server/'artifacts'/self.session/'model.txt';self.file.parent.mkdir(parents=True);self.file.write_text('synthetic')
        self.entry={'path':str(self.file),'sha256':digest(self.file),'size_bytes':self.file.stat().st_size}
        handoff['server_artifacts']=[self.entry]
        self.inv=self.project/'runs/ode-modeler'/self.session/'specialist-invocations'/'fixture-run';self.inv.mkdir(parents=True)
        (self.inv/'task.txt').write_text('Capture fixture')
        self.handoff=handoff
        self.provenance={'specialist':'ode_modeler','process_exit_code':0,'cancelled':False,'handoff_parse_error':None,
                         'malformed_event_count':0,'invocation_id':self.inv.name,'event_stream':'events.jsonl',
                         'prompt_sha256':digest(self.inv/'task.txt'),'apps_enabled':False,
                         'effective_mcp_inventory':{'biomass':True,'neko':False,'specialist_dispatcher':False}}
        self.event={'type':'item.completed','item':{'type':'mcp_tool_call','server':'biomass','tool':'list_generated_files',
                    'arguments':{'session_id':self.session},'status':'completed','error':None,'result':{'structured_content':{
                    'server':'BioMASS','session_id':self.session,'scope':'session','count':1,
                    'files':[{'path':str(self.file),'session_id':self.session,'size_bytes':self.entry['size_bytes']}]}}}}
        self.save()

    def save(self):
        for name,value in [('handoff.json',self.handoff),('provenance.json',self.provenance)]:
            (self.inv/name).write_text(json.dumps(value))
        (self.inv/'events.jsonl').write_text(json.dumps(self.event)+'\n')

    def test_missing_redundant_ownership_is_restored_without_editing_original(self):
        original=(self.inv/'handoff.json').read_bytes()
        entries,provenance=verified_inventory(self.project,self.inv,self.session)
        self.assertEqual(entries,[{**self.entry,'session_id':self.session}])
        receipt=record(self.project,self.server,self.session,'verified',entries,invocation_provenance=provenance)
        self.assertEqual(receipt['invocation'],provenance)
        self.assertEqual((self.inv/'handoff.json').read_bytes(),original)
        self.assertEqual(self.file.read_text(),'synthetic')
        with self.assertRaisesRegex(ValueError,'already exists'):
            record(self.project,self.server,self.session,'verified',entries,invocation_provenance=provenance)

    def test_conflicting_ownership_size_or_extra_file_fails(self):
        for key,value in [('session_id','wrong'),('size_bytes',999),('server','NeKo')]:
            self.handoff['server_artifacts']=[{**self.entry,key:value}];self.save()
            with self.subTest(key=key),self.assertRaises(ValueError): verified_inventory(self.project,self.inv,self.session)
        self.handoff['server_artifacts']=[self.entry,self.entry];self.save()
        with self.assertRaises(ValueError): verified_inventory(self.project,self.inv,self.session)

    def test_missing_failed_wrong_session_or_duplicate_catalogue_fails(self):
        original=copy.deepcopy(self.event)
        for case in ('failed','session','duplicate','count'):
            self.event=copy.deepcopy(original);item=self.event['item'];catalogue=item['result']['structured_content']
            if case=='failed':item['status']='failed'
            if case=='session':item['arguments']['session_id']='wrong'
            if case=='duplicate':catalogue['files']*=2;catalogue['count']=2
            if case=='count':catalogue['count']=2
            self.save()
            with self.subTest(case=case),self.assertRaises(ValueError):verified_inventory(self.project,self.inv,self.session)

    def test_cancelled_nonzero_or_unsafe_invocation_fails(self):
        original=copy.deepcopy(self.provenance)
        for key,value in [('cancelled',True),('process_exit_code',1),('prompt_sha256','0'*64),('apps_enabled',True),
                          ('effective_mcp_inventory',{'biomass':True,'neko':True})]:
            self.provenance={**original,key:value};self.save()
            with self.subTest(key=key),self.assertRaises(ValueError):verified_inventory(self.project,self.inv,self.session)

    def test_changed_record_or_source_cannot_publish(self):
        entries,provenance=verified_inventory(self.project,self.inv,self.session)
        (self.inv/'task.txt').write_text('changed')
        with self.assertRaisesRegex(ValueError,'record changed'):
            record(self.project,self.server,self.session,'changed-record',entries,invocation_provenance=provenance)
        self.assertFalse((self.project/'runs/ode-modeler'/self.session/'captures/changed-record').exists())
        self.file.write_text('tampered')
        with self.assertRaisesRegex(ValueError,'hash mismatch'):
            record(self.project,self.server,self.session,'changed-source',entries)

    def test_explicit_recording_still_rejects_unproven_ownership_and_size(self):
        with self.assertRaisesRegex(ValueError,'identity'):
            record(self.project,self.server,self.session,'missing',[self.entry])
        with self.assertRaisesRegex(ValueError,'byte count'):
            record(self.project,self.server,self.session,'size',[{**self.entry,'session_id':self.session,'size_bytes':999}])


@unittest.skipUnless(importlib.util.find_spec('mcp_biomodelling_servers'),'optional backend pure contract reader unavailable')
class BooleanCaptureTests(unittest.TestCase):
    def setUp(self):
        from mcp_biomodelling_servers.handoff import (NeKoToMaBoSSHandoffManifest,HandoffProvenance,HandoffPackage,
                                                       HandoffNetwork,handoff_artifact,write_handoff_manifest)
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.root=Path(temporary.name)
        self.project=self.root/'project';self.project.mkdir();self.server=self.root/'server'
        self.source=self.server/'artifacts/neko-session';self.source.mkdir(parents=True)
        self.bnet=self.source/'exported.bnet';self.bnet.write_text('X, Y\nY, X\n')
        self.manifest=NeKoToMaBoSSHandoffManifest(source=HandoffProvenance(server='NeKo',session_id='neko-session',
            mcp_package=HandoffPackage(name='mcp-biomodelling-servers',version='2.3.0'),
            modelling_package=HandoffPackage(name='nekomata',version='1.10.0'),operation='export_neko_handoff'),
            biological_context='Synthetic capture test',network=HandoffNetwork(nodes=['X','Y']),
            bnet_file=handoff_artifact(self.bnet,server='NeKo',session_id='neko-session',role='neko_bnet'))
        self.path=write_handoff_manifest(self.source/'exported.handoff.json',self.manifest)

    def capture(self,name='captured'):
        from scripts.codex.record_neko_boolean_handoff import record_neko
        return record_neko(self.project,self.server,self.path,name)

    def test_portable_capture_preserves_bytes_and_only_relocates_path(self):
        from mcp_biomodelling_servers.handoff import load_handoff_manifest
        original=self.path.read_bytes();result=self.capture()
        path=self.project/result['upstream_manifest'];imported=load_handoff_manifest(path,expected_handoff_type='neko-to-maboss')
        self.assertEqual(Path(imported.bnet_file.path).name,self.bnet.name)
        self.assertEqual(Path(imported.bnet_file.path).read_bytes(),self.bnet.read_bytes())
        raw=json.loads(original);raw['bnet_file']['path']=imported.bnet_file.path
        self.assertEqual(json.loads(path.read_text()),raw)
        self.assertEqual((path.parent/'original.handoff.json').read_bytes(),original)
        for e in result['artifacts']:self.assertEqual(digest(self.project/e['path']),e['sha256'])
        with self.assertRaisesRegex(ValueError,'already exists'):self.capture()

    def test_same_node_set_in_different_order_is_rejected(self):
        raw=json.loads(self.path.read_text());raw['network']['nodes']=['Y','X'];self.path.write_text(json.dumps(raw))
        with self.assertRaises(ValueError):self.capture()
        self.assertFalse((self.project/'runs').exists())

    def test_changed_bytes_and_outside_session_are_rejected(self):
        self.bnet.write_text('X, X\nY, Y\n')
        with self.assertRaises(ValueError):self.capture()
        self.bnet.write_text('X, Y\nY, X\n')
        outside=self.root/self.bnet.name;outside.write_bytes(self.bnet.read_bytes())
        raw=json.loads(self.path.read_text());raw['bnet_file']['path']=str(outside);self.path.write_text(json.dumps(raw))
        with self.assertRaises(ValueError):self.capture()
        self.assertFalse((self.project/'runs').exists())


if __name__=='__main__':unittest.main()
