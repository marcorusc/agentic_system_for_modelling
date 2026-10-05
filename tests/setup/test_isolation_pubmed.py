from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import tempfile
import tomllib
import unittest
from scripts import check_isolation
from scripts.setup_support import configure_codex
from scripts.codex.launcher_config import PUBMED_TOOLS, load_permitted_transport, toml_literal

ROOT = Path(__file__).resolve().parents[2]

class IsolationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)/'repo'
        self.root.mkdir()
        self.user = Path(self.tmp.name)/'user.json'

    def test_global_aliases_and_project_permissions_fail_without_leaking_values(self):
        self.user.write_text(json.dumps({'mcpServers':{'alias':{'command':'mcp-neko-server','env':{'TOKEN':'private-token'}}}}))
        path = self.root/'.claude/settings.json';path.parent.mkdir()
        path.write_text(json.dumps({'permissions':{'allow':['mcp__maboss-agent__*']}}))
        result=check_isolation.check(self.root,user_config=self.user)
        self.assertFalse(result['passed'])
        self.assertEqual(len(result['errors']),2)
        self.assertNotIn('private-token',json.dumps(result))

    def test_migration_is_previewable_preserves_unrelated_data_and_private_backups(self):
        original={'mcpServers':{'neko':{'command':'mcp-neko-server','env':{'TOKEN':'secret'}},'pubmed':{'url':'custom'}},'keep':42,
                  'projects':{str(self.root):{'mcpServers':{'biomass':{'command':'x'},'safe':{'command':'other'}}},
                              '/unrelated':{'mcpServers':{'biomass':{'command':'keep'}}}}}
        self.user.write_text(json.dumps(original))
        outputs=check_isolation.migration(self.user,(),None,self.root)
        self.assertEqual(json.loads(self.user.read_text()),original)
        planned=json.loads(outputs[self.user]);self.assertEqual(planned['keep'],42)
        self.assertEqual(planned['mcpServers'],{'pubmed':{'url':'custom'}})
        self.assertEqual(planned['projects']['/unrelated'],original['projects']['/unrelated'])
        self.assertEqual(planned['projects'][str(self.root)]['mcpServers'],{'safe':{'command':'other'}})
        result=check_isolation.write_config(self.user,outputs[self.user],self.root/'.setup/backups/isolation')
        backup=Path(result['backup'])
        self.assertEqual(json.loads(backup.read_text()),original)
        self.assertEqual(backup.stat().st_mode & 0o077,0)
        self.assertTrue(check_isolation.check(self.root,user_config=self.user)['passed'])
        self.assertFalse(check_isolation.migration(self.user,(),None,self.root))

    def test_codex_migration_keeps_custom_and_disabled_nonmodelling_servers(self):
        path=Path(self.tmp.name)/'config.toml'
        path.write_text('custom=42\n[mcp_servers.biomass]\ncommand="mcp-biomass-server"\n[mcp_servers.pubmed]\nurl="custom"\n')
        outputs=check_isolation.migration(None,(path,),None)
        data=tomllib.loads(outputs[path]);self.assertEqual(data['custom'],42)
        self.assertEqual(data['mcp_servers'],{'pubmed':{'url':'custom'}})

    def test_snapshot_missing_and_stale_fail(self):
        self.assertEqual(len(check_isolation.snapshot_errors(self.root,'2.4.0')),3)
        for name in ('neko','maboss','physicell'):
            p=self.root/f'.claude/skills/{name}-workflow/SKILL.md';p.parent.mkdir(parents=True)
            p.write_text('Operational snapshot for `mcp-biomodelling-servers` 2.4.0.')
        self.assertFalse(check_isolation.snapshot_errors(self.root,'2.4.0'))
        self.assertEqual(len(check_isolation.snapshot_errors(self.root,'2.5.0')),3)

    def test_pubmed_default_and_existing_custom_transports(self):
        shutil.copytree(ROOT/'.codex',self.root/'.codex')
        home=Path(self.tmp.name)/'home';home.mkdir()
        profile=home/'biomodel-literature-reviewer.config.toml'
        for existing in (None,{'url':'https://custom.example/mcp','enabled':True},{'url':'https://custom.example/mcp','enabled':False}):
            profile.write_text('mcp_servers='+toml_literal({} if existing is None else {'pubmed':existing})+'\n')
            outputs=configure_codex.render(self.root,self.root/'env',home)
            data=tomllib.loads(outputs[profile])
            if existing is None:
                self.assertEqual(data['mcp_servers']['pubmed']['url'],configure_codex.PUBMED_URL)
                self.assertEqual(set(data['mcp_servers']['pubmed']['enabled_tools']),set(PUBMED_TOOLS))
                self.assertEqual(len(PUBMED_TOOLS),7)
            else:self.assertEqual(data['mcp_servers']['pubmed'],existing)
            self.assertEqual(data['web_search'],'disabled')
            profile.write_text(outputs[profile])
            transport=load_permitted_transport(profile,'literature_reviewer')
            self.assertEqual(bool(transport),existing is None or existing['enabled'])
