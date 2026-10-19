"""Contract-backed capture regressions; run in the modelling environment as well."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from scripts.capture.record_maboss_physicell_handoff import record_maboss

try:
    from mcp_biomodelling_servers.handoff import MaBoSSToPhysiCellHandoffManifest
    BACKEND = True
except ImportError:
    BACKEND = False

@unittest.skipUnless(BACKEND, 'requires installed backend contract readers (no MCP calls)')
class MaBoSSCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = self.root/'project';self.project.mkdir()
        self.server = self.root/'server';self.source = self.server/'artifacts/session-1';self.source.mkdir(parents=True)
        self.bnd = self.source/'network.bnd';self.bnd.write_text('Node A { logic = A; }\n')
        self.cfg = self.source/'network.cfg';self.cfg.write_text('A.istate = 1;\n')
        self.manifest = self.source/'handoff.json'
        self.raw = {'schema_name':'mcp-biomodelling-handoff','schema_version':'1.0','handoff_type':'maboss-to-physicell',
            'created_at':'2026-10-05T00:00:00Z','source':self.provenance('MaBoSS','session-1','maboss'),
            'lineage':[],'network':{'nodes':['A'],'output_nodes':['A']},'bnd_file':self.artifact(self.bnd,'MaBoSS','session-1','maboss_bnd'),
            'cfg_file':self.artifact(self.cfg,'MaBoSS','session-1','maboss_cfg'),
            'simulation':{'parameters':{}},'target':{'cell_type':'cell'}}
        self.save()
    def tearDown(self):self.temp.cleanup()
    def provenance(self,server,session,package):
        return {'server':server,'session_id':session,'mcp_package':{'name':'mcp-biomodelling-servers','version':'2.4.0'},
                'modelling_package':{'name':package,'version':'test'},'operation':'export','recorded_at':'2026-10-05T00:00:00Z'}
    def artifact(self,path,server,session,role):
        return {'path':str(path),'name':path.name,'suffix':path.suffix,'session_id':session,'server':server,
                'role':role,'media_type':'application/json' if path.suffix=='.json' else 'text/plain',
                'size_bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    def save(self):self.manifest.write_text(json.dumps(self.raw))
    def capture(self):return record_maboss(self.project,self.server,self.manifest,'capture-1')
    def test_pair_and_original_manifest_preserved(self):
        result=self.capture();target=self.project/result['capture_path']
        self.assertEqual((target/'original.handoff.json').read_bytes(),self.manifest.read_bytes())
        imported=json.loads((target/'import.handoff.json').read_text())
        self.assertEqual(imported['bnd_file']['path'],str(target/'network.bnd'))
        self.assertEqual((target/'network.cfg').read_bytes(),self.cfg.read_bytes())
    def test_bad_hash_and_node_identity_rejected(self):
        self.bnd.write_text('Node B { logic = B; }\n')
        with self.assertRaisesRegex(ValueError,'hash'):self.capture()
        self.raw['bnd_file']=self.artifact(self.bnd,'MaBoSS','session-1','maboss_bnd');self.save()
        with self.assertRaisesRegex(ValueError,'nodes'):self.capture()
    def test_nested_parent_is_portable_and_lineage_preserved(self):
        parent_dir=self.project/'parent';parent_dir.mkdir()
        bnet=parent_dir/'network.bnet';bnet.write_text('targets, factors\nA, A\n')
        source=self.provenance('NeKo','parent-session','nekomata')
        parent={'schema_name':'mcp-biomodelling-handoff','schema_version':'1.0','handoff_type':'neko-to-maboss',
                'created_at':'2026-10-05T00:00:00Z','source':source,'lineage':[],
                'network':{'nodes':['A'],'output_nodes':['A']},'bnet_file':self.artifact(bnet,'NeKo','parent-session','neko_bnet')}
        file=parent_dir/'original.handoff.json';file.write_text(json.dumps(parent))
        self.raw['parent_manifest']=self.artifact(file,'NeKo','parent-session','parent_manifest')
        self.raw['lineage']=[source];self.save()
        result=self.capture();target=self.project/result['capture_path']
        imported=json.loads((target/'import.handoff.json').read_text())
        parent_import=json.loads(Path(imported['parent_manifest']['path']).read_text())
        self.assertTrue(Path(parent_import['bnet_file']['path']).is_relative_to(target))
        self.assertEqual((target/'parent/original.handoff.json').read_bytes(),file.read_bytes())
        self.assertEqual(imported['lineage'],self.raw['lineage'])
        self.assertEqual(imported['parent_manifest']['sha256'],hashlib.sha256(Path(imported['parent_manifest']['path']).read_bytes()).hexdigest())

if __name__=='__main__':unittest.main()
