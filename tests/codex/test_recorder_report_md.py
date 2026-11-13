from __future__ import annotations
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.capture.record_invocation import record
from tests.data.test_record_invocation_data import RecordDataInvocationTests as DataBase, transcript_events


def net_transcript(path, session='session-1', report='Full specialist report.'):
    events = [
        {'type': 'user', 'timestamp': '2026-10-05T00:00:00Z', 'message': {'content': 'Inspect only'}},
        {'type': 'assistant', 'timestamp': '2026-10-05T00:00:01Z', 'message': {'id': 'one', 'usage': {'input_tokens': 1, 'output_tokens': 1}, 'content': [
            {'type': 'tool_use', 'id': 'call', 'name': 'mcp__neko-agent__status', 'input': {'session_id': session}}]}},
        {'type': 'user', 'message': {'content': [{'type': 'tool_result', 'tool_use_id': 'call', 'content': json.dumps({'server': 'NeKo', 'session_id': session})}]}},
        {'type': 'assistant', 'timestamp': '2026-10-05T00:00:10Z', 'message': {'id': 'two', 'usage': {'input_tokens': 1, 'output_tokens': 1}, 'content': [
            {'type': 'text', 'text': report}]}},
    ]
    path.write_text('\n'.join(json.dumps(e) for e in events))
    return path


class ReportMdTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.project = self.root / 'project'; self.project.mkdir()
        self.report = self.project / 'runs/network-curator/session-1/report.md'

    def rec(self, report='Full specialist report.', session='session-1', agent='agent-1'):
        t = net_transcript(self.root / 't.jsonl', session, report)
        return record(self.project, {'agent_type': 'network-curator', 'agent_id': agent, 'agent_transcript_path': str(t)})

    def test_report_written_for_bound_session(self):
        result = self.rec()
        self.assertEqual(result['report_md'], 'written')
        final = (self.project / result['capture_path'] / 'final_report.md').read_bytes()
        self.assertEqual(self.report.read_bytes(), final)
        meta = json.loads((self.project / result['capture_path'] / 'invocation.json').read_text())
        self.assertEqual(meta['report_md'], 'written')

    def test_identical_report_noop(self):
        self.rec()
        mtime = self.report.stat().st_mtime_ns
        self.assertEqual(self.rec(agent='agent-2')['report_md'], 'identical')
        self.assertEqual(self.report.stat().st_mtime_ns, mtime)

    def test_existing_different_report_kept_first(self):
        self.report.parent.mkdir(parents=True)
        self.report.write_bytes(b'first\n')
        self.assertEqual(self.rec()['report_md'], 'kept-first')
        self.assertEqual(self.report.read_bytes(), b'first\n')

    def test_unbound_invocation_writes_no_report(self):
        t = self.root / 't.jsonl'
        t.write_text(json.dumps({'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': 'x'}]}}))
        result = record(self.project, {'agent_type': 'network-curator', 'agent_id': 'agent-2', 'agent_transcript_path': str(t)})
        self.assertEqual(result['status'], 'unbound')
        self.assertNotIn('report_md', result)
        self.assertEqual(list((self.project / 'runs').rglob('report.md')), [])

    def test_symlinked_session_dir_refused(self):
        outside = self.root / 'outside'; outside.mkdir()
        (self.project / 'runs/network-curator').mkdir(parents=True)
        (self.project / 'runs/network-curator/session-1').symlink_to(outside)
        with self.assertRaises(ValueError):
            self.rec()
        self.assertEqual(list(outside.iterdir()), [])

    def test_symlinked_report_refused(self):
        self.report.parent.mkdir(parents=True)
        victim = self.root / 'victim.txt'; victim.write_text('v')
        self.report.symlink_to(victim)
        with self.assertRaises(ValueError):
            self.rec()
        self.assertEqual(victim.read_text(), 'v')


class DataAnalystReportTests(DataBase):
    def test_data_analyst_report_after_integrity(self):
        events = transcript_events(self.sid, self.digest)
        events.append({'type': 'assistant', 'message': {'role': 'assistant', 'content': [{'type': 'text', 'text': 'Data report.'}]}})
        result = record(self.root, self.payload(events))
        self.assertTrue(self.integrity()['passed'])
        self.assertEqual(result['report_md'], 'written')
        self.assertTrue(self.integrity()['passed'])
        base = self.root / 'runs' / 'data-analyst' / self.sid
        self.assertEqual((base / 'report.md').read_bytes(), (base / 'invocation/agent-1/final_report.md').read_bytes())


del DataBase
if __name__ == '__main__':
    unittest.main()
