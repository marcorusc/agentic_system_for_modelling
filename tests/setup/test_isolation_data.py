from __future__ import annotations
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from scripts import check_isolation

ROOT = Path(__file__).resolve().parents[2]


class DataIsolationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / 'repo'
        (self.root / '.claude/agents').mkdir(parents=True)
        shutil.copy(ROOT / '.claude/agents/data-analyst.md', self.root / '.claude/agents/data-analyst.md')
        shutil.copy(ROOT / '.claude/settings.json', self.root / '.claude/settings.json')
        # Never touch the real user configuration: HOME points at a temp dir.
        self.home = Path(tmp.name) / 'home'
        self.home.mkdir()
        env = {k: v for k, v in os.environ.items() if k != 'CLAUDE_CONFIG_DIR'}
        env['HOME'] = str(self.home)
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def errors(self):
        return check_isolation.check(self.root)['errors']

    def test_repository_copy_passes(self):
        self.assertEqual(self.errors(), [])

    def test_isolation_flags_mcp_on_data_analyst(self):
        path = self.root / '.claude/agents/data-analyst.md'
        path.write_text(path.read_text().replace('tools:\n', 'mcpServers:\n  - x:\n      type: stdio\ntools:\n', 1))
        self.assertTrue(any('data-analyst' in e and 'mcpServers' in e for e in self.errors()))

    def test_isolation_flags_missing_deny(self):
        path = self.root / '.claude/agents/data-analyst.md'
        path.write_text(path.read_text().replace("  - Agent\n", "", 1))
        self.assertTrue(any('data-analyst' in e and 'Agent' in e for e in self.errors()))

    def test_isolation_flags_vendored_skill_in_claude_skills(self):
        for base in ('.claude/skills', 'skills'):
            (self.root / base / 'depmap').mkdir(parents=True)
        errors = [e for e in self.errors() if 'depmap' in e]
        self.assertEqual(len(errors), 2)

    def run_main(self) -> dict:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            check_isolation.main(['--root', str(self.root)])
        return json.loads(out.getvalue())

    def test_isolation_flags_vendored_skill_in_user_skills_dir(self):
        self.assertEqual(check_isolation.user_skills_dir(), self.home / '.claude/skills')
        self.assertTrue(self.run_main()['passed'])
        (self.home / '.claude/skills/pydeseq2').mkdir(parents=True)
        result = self.run_main()
        self.assertFalse(result['passed'])
        flagged = [e for e in result['errors'] if 'pydeseq2' in e]
        self.assertEqual(len(flagged), 1, result['errors'])
        self.assertIn(str(self.home / '.claude/skills/pydeseq2'), flagged[0])
        self.assertIn('remove', flagged[0])
        self.assertTrue((self.home / '.claude/skills/pydeseq2').is_dir())  # detection only

    def test_isolation_user_skills_dir_honours_claude_config_dir(self):
        config = Path(self.home) / 'alt-config'
        (config / 'skills/depmap').mkdir(parents=True)
        (self.home / '.claude/skills/gget').mkdir(parents=True)
        with mock.patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': str(config)}):
            self.assertEqual(check_isolation.user_skills_dir(), config / 'skills')
            errors = self.run_main()['errors']
        self.assertTrue(any(str(config / 'skills/depmap') in e for e in errors), errors)
        self.assertFalse(any('gget' in e for e in errors), errors)

    def test_repository_only_skips_user_skills_dir(self):
        (self.home / '.claude/skills/pydeseq2').mkdir(parents=True)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            check_isolation.main(['--root', str(self.root), '--repository-only'])
        self.assertTrue(json.loads(out.getvalue())['passed'])

    def test_setup_verification_flags_vendored_user_skill(self):
        from scripts.setup_support import verify
        capabilities = {'passed': True, 'errors': [], 'mcp': {}}
        with mock.patch.object(verify, 'run') as run:
            clean = verify.verify(self.root, None, {'claude': '/fixture/claude'}, capability_report=capabilities)
            (self.home / '.claude/skills/pydeseq2').mkdir(parents=True)
            flagged = verify.verify(self.root, None, {'claude': '/fixture/claude'}, capability_report=capabilities)
        self.assertTrue(clean['passed'], clean['errors'])
        self.assertFalse(flagged['passed'])
        self.assertTrue(any(str(self.home / '.claude/skills/pydeseq2') in e for e in flagged['errors']),
                        flagged['errors'])
        self.assertEqual(run.call_count, 2)

    def test_isolation_flags_missing_orchestrator_hook(self):
        path = self.root / '.claude/settings.json'
        data = json.loads(path.read_text())
        data['hooks']['PreToolUse'] = [h for h in data['hooks']['PreToolUse']
                                       if h.get('matcher') != 'Bash']
        path.write_text(json.dumps(data))
        self.assertTrue(any('data_orchestrator_guard.py' in e for e in self.errors()))


class PolicyTextTests(unittest.TestCase):
    def test_claude_md_mentions_data_derived_and_delegation(self):
        text = (ROOT / 'CLAUDE.md').read_text()
        for needle in ('data-derived', 'data-analyst may also author', 'scripts/data/session.py'):
            self.assertIn(needle, text)


if __name__ == '__main__':
    unittest.main()
