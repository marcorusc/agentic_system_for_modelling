from __future__ import annotations
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from scripts.evidence_contract import parse_footer
from scripts.codex.write_literature_report import validate_report, write_report, ReportValidationError
from scripts.codex.validate_handoff import validate_handoff
from tests.codex.test_literature_report_writer import VALID_REPORT
from tests.codex.test_validate_handoff import handoff_for


class EvidenceContractTests(unittest.TestCase):
    def test_excluded_citations_never_appear_as_supporting(self):
        parsed = validate_report(VALID_REPORT, 'GAB1', 'AKT1', 'session-1')
        self.assertEqual(parsed.pmids, ('12345678',))
        self.assertEqual(parsed.excluded_pmids, ('87654321',))

    def test_missing_mismatched_duplicate_and_misclassified_footers_fail(self):
        data = parse_footer(VALID_REPORT)
        bad = [VALID_REPORT.split('```yaml')[0], VALID_REPORT + '\nprose after footer',
               VALID_REPORT.replace('"neko_session_id":"session-1"', '"neko_session_id":"other"'),
               VALID_REPORT.replace('"verdict":"supported"', '"verdict":"supported","verdict":"supported"')]
        for field, value in [('supporting_pmids', ['87654321']), ('excluded_pmids', []), ('edge', ['AKT1', 'stimulation', 'GAB1']), ('supporting_pmids', ['12345678', '12345678']), ('confidence', 'high')]:
            changed = dict(data); changed[field] = value
            bad.append(VALID_REPORT.split('```yaml')[0] + '```yaml\n' + json.dumps(changed) + '\n```\n')
        for content in bad:
            with self.subTest(content=content), self.assertRaises(ReportValidationError):
                validate_report(content, 'GAB1', 'AKT1', 'session-1')

    def test_candidates_revisions_and_completed_handoff(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); draft = root / 'draft.md'; draft.write_text(VALID_REPORT)
            kwargs = dict(project_root=root, session_id='session-1', source='GAB1', target='AKT1', draft_path=draft, candidate=True)
            with self.assertRaisesRegex(ReportValidationError, 'previous'):
                write_report(**kwargs, revision=2)
            first = write_report(**kwargs)
            second = write_report(**kwargs, revision=2)
            self.assertEqual(second['path'], 'evidence/reports/session-1/candidates/GAB1__AKT1.r2.md')
            with self.assertRaisesRegex(ReportValidationError, 'overwrite'):
                write_report(**kwargs, revision=2)
            payload = handoff_for('literature_reviewer', 'literature_review', 'session-1', None)
            payload['session_id'] = 'session-1'
            payload['artifacts'] = [first, second]
            validate_handoff(payload, project_root=root)
            self.assertEqual((root / first['path']).read_text(), VALID_REPORT)


class FooterBoundaryTests(unittest.TestCase):
    def test_raw_footer_reader_rejects_invalid_types_enums_and_overlapping_pmids(self):
        original = parse_footer(VALID_REPORT)
        for field, value in [('verdict', 'approved'), ('confidence', 1), ('interaction_type', None),
                             ('edge', ['GAB1','  ','AKT1']), ('edge', ['../escape','stimulation','AKT1']),
                             ('supporting_pmids', [12345678]), ('supporting_pmids', []),
                             ('excluded_pmids', ['12345678']),
                             ('neko_session_id', '../escape')]:
            data = dict(original); data[field] = value
            content = VALID_REPORT.split('```yaml')[0] + '```yaml\n' + json.dumps(data) + '\n```\n'
            with self.subTest(field=field, value=value), self.assertRaises(ValueError): parse_footer(content)
