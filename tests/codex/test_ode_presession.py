"""Existing pre-session ODE result behavior and its client guidance."""
from __future__ import annotations

from pathlib import Path
import tempfile
import tomllib
import unittest

from scripts.codex.launcher_config import build_command
from scripts.codex.validate_handoff import HandoffValidationError, validate_handoff
from scripts.setup_support import configure_codex

ROOT = Path(__file__).resolve().parents[2]


def presession(status):
    return {
        'schema_version': 1, 'specialist': 'ode_modeler', 'stage': 'biomass_ode',
        'status': status, 'session_id': None, 'derived_from_session_id': None,
        'actions': [], 'assumptions': [], 'decisions_required': ['Pre-session technical blocker'],
        'artifacts': [], 'validation': {'checks': ['No scientific session or input exists'], 'passed': False},
        'recommended_next_stage': None,
    }


class ODEPreSessionTests(unittest.TestCase):
    def test_existing_validator_accepts_blocked_and_failed_without_ode(self):
        with tempfile.TemporaryDirectory() as temporary:
            for status in ('blocked', 'failed'):
                with self.subTest(status=status):
                    value = presession(status)
                    self.assertIs(validate_handoff(value, project_root=Path(temporary)), value)
                    self.assertNotIn('ode', value)

    def test_existing_validator_rejects_partial_ode_even_when_presession(self):
        with tempfile.TemporaryDirectory() as temporary:
            for status in ('blocked', 'failed'):
                for partial in ({}, {'contract_version': 2}, {'contract_version': 2, 'input_kind': 'neko'}, None):
                    with self.subTest(status=status, partial=partial):
                        value = presession(status)
                        value['ode'] = partial
                        with self.assertRaises(HandoffValidationError):
                            validate_handoff(value, project_root=Path(temporary))

    def test_presession_exception_does_not_allow_completed_or_needs_approval(self):
        with tempfile.TemporaryDirectory() as temporary:
            for status in ('completed', 'needs_approval'):
                with self.subTest(status=status), self.assertRaisesRegex(HandoffValidationError, 'requires session_id'):
                    validate_handoff(presession(status), project_root=Path(temporary))

    def test_ode_wrapper_clarifies_exact_presession_case(self):
        text = build_command('fixture-codex', 'ode_modeler', 'inspect deployment context')[-1]
        for phrase in ('pre-session blocked or failed', 'session_id=null', 'derived_from_session_id=null',
                       'no scientific input, revision or artifacts exist', 'omit the entire ode object',
                       'Do not fabricate ODE provenance or return a partial ode object',
                       'include complete ode metadata with ode.contract_version=2'):
            self.assertIn(phrase, text)
        other = build_command('fixture-codex', 'network_curator', 'inspect deployment context')[-1]
        self.assertNotIn('omit the entire ode object', other)

    def test_canonical_clients_and_setup_output_agree(self):
        source = tomllib.loads((ROOT/'.codex/profiles/biomodel-ode-modeler.config.toml.example').read_text())
        texts = [source['developer_instructions'], (ROOT/'.claude/agents/ode-modeler.md').read_text()]
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            rendered = configure_codex.render(ROOT, home/'fixture-environment', home, with_biomass=True)
            texts.append(tomllib.loads(rendered[home/'biomodel-ode-modeler.config.toml'])['developer_instructions'])
        for text in texts:
            with self.subTest(text=text[:50]):
                self.assertIn(configure_codex._ODE_PRESESSION_GUIDANCE, text)
                self.assertNotIn('and ode.contract_version=2 with the provenance required by docs/ode-contract.md.', text)
                self.assertNotIn('Before parent capture, return a metadata-only needs_approval handoff', text)
                self.assertIn('For a scientific ODE result awaiting', text)

    def test_setup_migrates_exact_old_guidance_without_duplicate_or_custom_loss(self):
        target = Path('biomodel-ode-modeler.config.toml')
        old = ('Preserve this unrelated custom instruction.\n'
               'and ode.contract_version=2 with the provenance required by docs/ode-contract.md.\n'
               'Before parent capture, return a metadata-only needs_approval handoff\n'
               + configure_codex._ODE_GUIDANCE_BEFORE_PRESESSION)
        migrated = configure_codex._ode_instructions('ode_modeler', old, target)
        self.assertIn('Preserve this unrelated custom instruction.', migrated)
        self.assertNotIn(configure_codex._ODE_GUIDANCE_BEFORE_PRESESSION, migrated)
        self.assertEqual(migrated.count(configure_codex.ODE_PROFILE_GUIDANCE['ode_modeler']), 1)
        self.assertEqual(configure_codex._ode_instructions('ode_modeler', migrated, target), migrated)


if __name__ == '__main__':
    unittest.main()
