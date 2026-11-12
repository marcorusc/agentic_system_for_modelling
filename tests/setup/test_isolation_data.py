from __future__ import annotations
import json
import shutil
import tempfile
import unittest
from pathlib import Path
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
