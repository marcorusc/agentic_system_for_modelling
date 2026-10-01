"""Repository profile transports, pinned authoring references and Claude report hooks."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

from scripts.codex.launcher_config import SPECIALISTS, load_permitted_transport
from tests.codex.test_ode_evidence import report

ROOT = Path(__file__).resolve().parents[2]
GUARD = ROOT / '.claude/scripts/literature_file_guard.py'


class OdeProfileSkillTests(unittest.TestCase):
    def test_real_profile_templates_expose_only_the_role_transport(self):
        for role, (profile, permitted) in SPECIALISTS.items():
            with self.subTest(role=role):
                path = ROOT / '.codex/profiles' / f'{profile}.config.toml.example'
                value = tomllib.loads(path.read_text())
                servers = value['mcp_servers']
                self.assertEqual({name for name, config in servers.items() if config.get('enabled')},
                                 {permitted} if permitted else set())
                self.assertFalse(value['features']['apps'])
                self.assertFalse(servers['specialist_dispatcher']['enabled'])
                self.assertEqual(value['sandbox_mode'], 'read-only')
                self.assertEqual(value['approval_policy'], 'on-request')
                self.assertEqual(set(servers) & {'neko', 'maboss', 'physicell', 'biomass'},
                                 {'neko', 'maboss', 'physicell', 'biomass'})
                transport = load_permitted_transport(path, role)
                if permitted:
                    self.assertTrue(servers[permitted]['required'])
                    self.assertEqual(servers[permitted]['default_tools_approval_mode'], 'writes')
                    self.assertTrue(transport[1].startswith(f'mcp_servers.{permitted}='))
                else:
                    self.assertEqual(transport, [])
                if role == 'ode_modeler':
                    self.assertEqual(set(servers['biomass']['disabled_tools']),
                                     {'delete_session', 'clean_generated_files', 'close_session'})

    def test_ode_instructions_match_across_client_definitions(self):
        profile = tomllib.loads((ROOT / '.codex/profiles/biomodel-ode-modeler.config.toml.example').read_text())
        compatibility = tomllib.loads((ROOT / '.codex/agents/ode-modeler.toml.example').read_text())
        claude = (ROOT / '.claude/agents/ode-modeler.md').read_text()
        header, body = claude[4:].split('\n---\n', 1)
        self.assertEqual(compatibility['name'], 'ode_modeler')
        self.assertEqual(compatibility['developer_instructions'], profile['developer_instructions'])
        self.assertTrue(body.strip().startswith(profile['developer_instructions'].strip()))
        servers = header.split('mcpServers:\n', 1)[1].split('\ntools:', 1)[0]
        self.assertEqual(re.findall(r'^  - ([a-z_]+):$', servers, re.M), ['biomass'])
        self.assertIn('command: __configure_biomass_command__', servers)
        self.assertIn('CONDA_PREFIX: __configure_biomass_environment__', servers)
        self.assertIn('PATH: __configure_biomass_path__', servers)
        self.assertNotIn('/home/', servers)
        self.assertIn('  - biomass-workflow\n', header)
        self.assertIn('  - Task\n', header)
        self.assertIn('  - Agent\n', header)
        self.assertIn('  - mcp__biomass__close_session\n', header)
        for path in (ROOT / '.claude/agents').glob('*.md'):
            if path.name != 'ode-modeler.md':
                self.assertIn("  - 'mcp__biomass__*'\n", path.read_text().split('\n---\n', 1)[0])

    def test_local_reference_hashes_and_client_copies_match(self):
        codex = ROOT / 'skills/biomass-workflow'
        claude = ROOT / '.claude/skills/biomass-workflow'
        provenance = json.loads((codex / 'references/provenance.json').read_text())
        self.assertEqual(set(provenance['sha256']),
                         {'reaction_syntax.md', 'authoring_examples.md', 'model_editing.md', 'network_to_reactions.md'})
        for name, expected in provenance['sha256'].items():
            with self.subTest(reference=name):
                content = (codex / 'references' / name).read_bytes()
                self.assertEqual(hashlib.sha256(content).hexdigest(), expected)
                self.assertEqual(content, (claude / 'references' / name).read_bytes())
        self.assertEqual((codex / 'references/provenance.json').read_bytes(),
                         (claude / 'references/provenance.json').read_bytes())
        self.assertEqual((codex / 'SKILL.md').read_bytes(), (claude / 'SKILL.md').read_bytes())
        for target in re.findall(r'\]\((references/[^)]+)\)', (codex / 'SKILL.md').read_text()):
            self.assertTrue((codex / target).is_file(), target)


class ClaudeOdeReportHookTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / 'project'
        self.root.mkdir()
        self.target = self.root / 'evidence/reports/bio-session/ode/binding.md'

    def call(self, target=None, content=None, tool='Write', project=None):
        payload = {'tool_name': tool, 'tool_input': {'file_path': str(target or self.target)}}
        if content is not None:
            payload['tool_input']['content'] = content
        environment = dict(os.environ, CLAUDE_PROJECT_DIR=str(project or self.root), PYTHONDONTWRITEBYTECODE='1')
        return subprocess.run([sys.executable, str(GUARD)], input=json.dumps(payload),
                              text=True, capture_output=True, env=environment, timeout=10)

    def test_valid_ode_report_is_checked_without_writing_it(self):
        checked = self.call(content=report())
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertTrue(self.target.parent.is_dir())
        self.assertFalse(self.target.exists())
        self.target.write_text(report())
        read = self.call(tool='Read')
        self.assertEqual(read.returncode, 0, read.stderr)
        repeated = self.call(content=report())
        self.assertEqual(repeated.returncode, 2, repeated.stderr)
        self.assertIn('overwrite', repeated.stderr)
        self.assertEqual(self.target.read_text(), report())

    def test_invalid_ode_content_or_identity_never_creates_directory(self):
        for target, content in ((self.target, None), (self.target, 'not a report'),
                                (self.target.with_name('another.md'), report()),
                                (self.target.with_suffix('.txt'), report()),
                                (self.target.parent / 'nested/binding.md', report())):
            with self.subTest(target=target, content=content):
                checked = self.call(target, content)
                self.assertEqual(checked.returncode, 2, checked.stderr)
                self.assertNotIn('Traceback', checked.stderr)
                self.assertFalse(self.target.parent.exists())

    def test_alias_to_ode_and_symlinked_session_cannot_bypass_content_check(self):
        self.target.parent.mkdir(parents=True)
        alias = self.root / 'evidence/reports/alias'
        alias.symlink_to(self.target.parent, target_is_directory=True)
        for path in (alias / 'binding.md', self.root / 'evidence/reports/bio-session/ode/../ode/binding.md'):
            with self.subTest(path=path):
                checked = self.call(path, 'invalid report')
                self.assertEqual(checked.returncode, 2, checked.stderr)
                self.assertFalse(self.target.exists())
        session = self.root / 'evidence/reports/session-alias'
        session.symlink_to(self.target.parent.parent, target_is_directory=True)
        checked = self.call(session / 'ode/binding.md', report())
        self.assertEqual(checked.returncode, 2, checked.stderr)
        self.assertIn('symlink', checked.stderr)

    def test_project_environment_alias_does_not_disable_ode_validation(self):
        alias = self.root.parent / 'project-alias'
        alias.symlink_to(self.root, target_is_directory=True)
        checked = self.call(content='invalid report', project=alias)
        self.assertEqual(checked.returncode, 2, checked.stderr)
        self.assertFalse(self.target.parent.exists())

    def test_legacy_edge_and_read_controls_remain(self):
        edge = self.root / 'evidence/reports/neko-session/A__B.md'
        checked = self.call(edge, 'legacy edge content')
        self.assertEqual(checked.returncode, 0, checked.stderr)
        outside = self.call(self.root / 'CURRENT_STATE.md', 'state mutation')
        self.assertEqual(outside.returncode, 2, outside.stderr)
        for name in ('literature_queue.json', 'Network.sif'):
            checked = self.call(self.root / name, tool='Read')
            self.assertEqual(checked.returncode, 2, checked.stderr)


if __name__ == '__main__':
    unittest.main()
