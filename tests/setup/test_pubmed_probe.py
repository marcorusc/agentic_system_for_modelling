import asyncio
from contextlib import asynccontextmanager
import json
from types import SimpleNamespace
import unittest
from unittest import mock

from scripts.setup_support import probe_pubmed
from scripts.setup_support.state import SetupError

class PubMedProbeTests(unittest.TestCase):
    def test_wrapper_has_whole_process_timeout_and_sanitizes_failure(self):
        with mock.patch.object(probe_pubmed,'run',side_effect=SetupError('Authorization: secret-value')) as run:
            result=probe_pubmed.probe('/env/python',timeout=7)
        self.assertFalse(result['passed'])
        self.assertNotIn('secret-value',json.dumps(result))
        self.assertEqual(run.call_args.kwargs['timeout'],7)
        self.assertIn('--worker',run.call_args.args[0])
        self.assertEqual(result['scientific_calls'],0)

    def test_capabilities_required_and_no_article_search(self):
        for names,passed in [(list(probe_pubmed.PUBMED_TOOLS),True),(['search_articles'],False)]:
            with mock.patch.object(probe_pubmed,'run',return_value=SimpleNamespace(stdout=json.dumps({'tools':names}))):
                self.assertEqual(probe_pubmed.probe('/env/python')['passed'],passed)

    def test_both_sdk_stream_shapes_and_read_only_operations(self):
        for count in (2,3):
            calls=[]
            @asynccontextmanager
            async def client(url):
                yield tuple(object() for _ in range(count))
            class Session:
                async def initialize(self): calls.append('initialize')
                async def list_tools(self):
                    calls.append('tools/list')
                    return SimpleNamespace(tools=[SimpleNamespace(name=n) for n in probe_pubmed.PUBMED_TOOLS],nextCursor=None)
            @asynccontextmanager
            async def session(read,write): yield Session()
            result=asyncio.run(probe_pubmed.inspect_endpoint(probe_pubmed.PUBMED_URL,client_factory=client,session_factory=session))
            self.assertEqual(calls,['initialize','tools/list'])
            self.assertEqual(result['tools'],list(probe_pubmed.PUBMED_TOOLS))

    def test_timeout_and_repeated_cursor_fail(self):
        @asynccontextmanager
        async def client(url): yield object(),object()
        class Session:
            async def initialize(self): pass
            async def list_tools(self,cursor=None): return SimpleNamespace(tools=[],nextCursor='repeat')
        @asynccontextmanager
        async def session(read,write): yield Session()
        with self.assertRaisesRegex(ValueError,'repeated'):
            asyncio.run(probe_pubmed.inspect_endpoint(probe_pubmed.PUBMED_URL,client_factory=client,session_factory=session))
        class Slow(Session):
            async def initialize(self): await asyncio.sleep(2)
        @asynccontextmanager
        async def slow(read,write): yield Slow()
        with self.assertRaises(TimeoutError):
            asyncio.run(probe_pubmed.inspect_endpoint(probe_pubmed.PUBMED_URL,client_factory=client,session_factory=slow,deadline_seconds=.01))

    def test_url_never_contains_embedded_credentials(self):
        for value in ['http://example.test/mcp','https://user:password@example.test/mcp','https://example.test/mcp?token=secret']:
            with self.assertRaises(ValueError): probe_pubmed.endpoint(value)
