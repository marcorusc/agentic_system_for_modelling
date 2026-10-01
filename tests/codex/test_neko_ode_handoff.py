"""Regression checks for portable NeKo-to-BioMASS artifact capture."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from scripts.codex.record_neko_ode_handoff import record_neko


class NeKoODEHandoffTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='neko-ode-handoff-tests-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / 'project'
        self.project.mkdir()
        self.server = self.root / 'neko-server'
        self.session = 'f41d1528-d996-4233-bf99-7989dd843f73'
        source = self.server / 'artifacts' / self.session
        source.mkdir(parents=True)
        self.network = source / 'approved-cell-cycle.network.json'
        self.network.write_text(json.dumps({
            'nodes': [{'node_id': 'A'}, {'node_id': 'B'}],
            'edges': [{'edge_id': 'A_to_B', 'source': 'A', 'target': 'B', 'effect': 'activation'}],
        }) + '\n', encoding='utf-8')
        self.network_bytes = self.network.read_bytes()
        self.manifest = {
            'schema_name': 'mcp-biomodelling-handoff', 'schema_version': '1.0',
            'handoff_type': 'neko-to-biomass',
            'source': {
                'server': 'NeKo', 'session_id': self.session,
                'mcp_package': {'name': 'mcp-biomodelling-servers', 'version': '2.3.0'},
                'modelling_package': {'name': 'nekomata', 'version': '0.2.9'},
                'operation': 'export_biomass_handoff', 'recorded_at': '2026-09-18T00:00:00Z',
            },
            'biological_context': 'Synthetic artifact-reader compatibility fixture.',
            'history_state_id': 0,
            'network_file': {
                'server': 'NeKo', 'session_id': self.session, 'role': 'neko_ode_network',
                'name': self.network.name, 'path': str(self.network), 'suffix': '.json',
                'media_type': 'application/json', 'size_bytes': len(self.network_bytes),
                'sha256': hashlib.sha256(self.network_bytes).hexdigest(),
            },
        }
        self.manifest_path = source / 'approved-cell-cycle.handoff.json'
        self.manifest_path.write_text(json.dumps(self.manifest, indent=2) + '\n', encoding='utf-8')
        self.manifest_bytes = self.manifest_path.read_bytes()

    def capture(self):
        return record_neko(self.project, self.server, self.manifest_path, 'capture-1')

    def test_capture_preserves_exported_basename_and_only_relocates_manifest_path(self):
        result = self.capture()
        imported_path = self.project / result['upstream_manifest']
        captured_network = imported_path.parent / self.network.name
        imported = json.loads(imported_path.read_text())
        expected = copy.deepcopy(self.manifest)
        expected['network_file']['path'] = str(captured_network)
        self.assertEqual(imported, expected)
        self.assertEqual(imported['network_file']['name'], Path(imported['network_file']['path']).name)
        self.assertEqual(captured_network.read_bytes(), self.network_bytes)
        self.assertFalse((imported_path.parent / 'network.json').exists())
        self.assertEqual((imported_path.parent / 'original.handoff.json').read_bytes(), self.manifest_bytes)
        self.assertEqual(self.manifest_path.read_bytes(), self.manifest_bytes)
        self.assertEqual(self.network.read_bytes(), self.network_bytes)
        listed = {entry['path']: entry['sha256'] for entry in result['artifacts']}
        self.assertEqual(listed[captured_network.relative_to(self.project).as_posix()],
                         self.manifest['network_file']['sha256'])
        for path, expected_hash in listed.items():
            self.assertEqual(hashlib.sha256((self.project / path).read_bytes()).hexdigest(), expected_hash)
        relocation = json.loads((imported_path.parent / 'relocation.json').read_text())
        self.assertEqual(relocation['source_network_path'], str(self.network))
        self.assertEqual(relocation['network_sha256'], self.manifest['network_file']['sha256'])

    @unittest.skipUnless(importlib.util.find_spec('mcp_biomodelling_servers'),
                         'optional installed server package supplies the pure handoff reader')
    def test_relocated_capture_is_accepted_by_actual_server_reader(self):
        # This imports a pure file validator: it starts no MCP server or session.
        from mcp_biomodelling_servers.ode_handoff import read_ode_handoff
        original, original_network = read_ode_handoff(str(self.manifest_path))
        result = self.capture()
        imported, imported_network = read_ode_handoff(str(self.project / result['upstream_manifest']))
        self.assertEqual(imported_network, original_network)
        self.assertEqual(imported.network_file.name, original.network_file.name)
        expected = original.model_dump(mode='json')
        expected['network_file']['path'] = imported.network_file.path
        self.assertEqual(imported.model_dump(mode='json'), expected)

    def test_capture_rejects_basename_collisions_before_publishing(self):
        for name in ('original.handoff.json', 'import.handoff.json', 'relocation.json'):
            with self.subTest(name=name):
                conflicting = self.network.with_name(name)
                conflicting.write_bytes(self.network_bytes)
                changed = copy.deepcopy(self.manifest)
                changed['network_file'].update(name=name, path=str(conflicting))
                self.manifest_path.write_text(json.dumps(changed), encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'basename conflicts with capture metadata'):
                    self.capture()
                self.assertFalse((self.project / 'runs').exists())
                self.assertEqual(conflicting.read_bytes(), self.network_bytes)


if __name__ == '__main__':
    unittest.main()
