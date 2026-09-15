"""Real SDK protocol tests; run with dispatcher/requirements.txt installed."""
from __future__ import annotations
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SDK = importlib.util.find_spec('mcp') is not None
if SDK:
    from mcp import Client
    from scripts.codex.dispatcher.server import create_server, INPUTS
    from scripts.codex.dispatcher.manager import TaskManager
    from scripts.codex.specialist_runtime import executor


@unittest.skipUnless(SDK, 'official MCP SDK required; run the dispatcher SDK test job')
class ServerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        patch = mock.patch.object(executor,'PROJECT_ROOT',self.root)
        patch.start(); self.addCleanup(patch.stop)
        self.manager = TaskManager(self.root)
        self.addCleanup(self.manager.close)
        self.server = create_server(lambda:self.manager)

    async def test_eight_explicit_tools_and_no_escape_arguments(self):
        async with Client(self.server) as client:
            listed = await client.list_tools()
            self.assertEqual({tool.name for tool in listed.tools},set(INPUTS))
            self.assertEqual(len(listed.tools),8)
            for tool in listed.tools:
                self.assertFalse(tool.input_schema['additionalProperties'])
                self.assertFalse(set(tool.input_schema.get('properties',{})) & {
                    'command','profile','environment','cwd','codex_executable','specialist','mcp_server'})
            for extra in ('profile','command','mcp_server','codex_executable','cwd','allow_web_search'):
                result=await client.call_tool('start_network_curator',{'task':'inspect',extra:True})
                self.assertTrue(result.is_error,extra)
            self.assertEqual(self.manager.list(),[])

    async def test_calls_and_validation_errors(self):
        async with Client(self.server) as client:
            for name,args in (
                ('run_shell',{'command':'x'}),
                ('start_network_curator',{'task':' '}),
                ('start_network_curator',{'task':'inspect','approved_tools':['*']}),
                ('start_network_curator',{'task':'inspect','approved_tools':['delete_session']}),
                ('start_literature_reviewer',{'task':'inspect','approved_tools':[]}),
                ('start_literature_reviewer',{'task':'inspect','allow_web_search':'false'}),
                ('get_specialist_task',{'task_id':'../outside'}),
                ('get_specialist_events',{'task_id':'a'*32,'limit':201}),
            ):
                result=await client.call_tool(name,args)
                self.assertTrue(result.is_error,(name,args,result))
            result=await client.call_tool('list_specialist_tasks',{})
            self.assertEqual(result.structured_content,{'tasks':[]})

    async def test_start_returns_id_and_failure_is_queryable(self):
        with mock.patch.object(executor,'resolve_codex_executable',return_value='codex'), \
             mock.patch.object(executor,'profile_path',return_value=self.root/'missing'):
            async with Client(self.server) as client:
                result=await client.call_tool('start_network_curator',{'task':'inspect'})
                self.assertFalse(result.is_error,result)
                task_id=result.structured_content['task_id']
                import asyncio
                await asyncio.to_thread(self.manager.workers[task_id][0].join,3)
                result=await client.call_tool('get_specialist_task',{'task_id':task_id})
                self.assertEqual(result.structured_content['execution_state'],'failed')
                self.assertIsNone(result.structured_content['handoff'])
                events=await client.call_tool('get_specialist_events',{'task_id':task_id})
                self.assertTrue(events.structured_content['events'])
                cancelled=await client.call_tool('cancel_specialist_task',{'task_id':task_id})
                self.assertEqual(cancelled.structured_content['execution_state'],'failed')

    async def test_stdio_transport_and_clean_disconnect(self):
        import asyncio
        import os
        import shutil
        import sys
        from mcp import ClientSession, StdioServerParameters, stdio_client
        source = Path(__file__).resolve().parents[2] / 'scripts'
        shutil.copytree(source, self.root/'scripts', ignore=shutil.ignore_patterns('__pycache__'))
        environment = os.environ.copy()
        environment['CODEX_HOME'] = str(self.root/'empty-codex-home')
        parameters = StdioServerParameters(command=sys.executable,
            args=['-m','scripts.codex.dispatcher.server'],cwd=str(self.root),env=environment)
        # Close the in-process manager before the independent stdio server takes its lease.
        self.manager.close()
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                self.assertEqual(len(listed.tools),8)
                result = await session.call_tool('start_network_curator',{'task':'inspection only'})
                self.assertFalse(result.is_error,result)
                task_id=result.structured_content['task_id']
                for _ in range(100):
                    status=await session.call_tool('get_specialist_task',{'task_id':task_id})
                    if status.structured_content['execution_state']=='failed': break
                    await asyncio.sleep(.02)
                else: self.fail('missing profile must fail promptly')
                events=await session.call_tool('get_specialist_events',{'task_id':task_id})
                self.assertTrue(events.structured_content['events'])
        # Disconnect released the lease; no worker or server has to be killed by PID.
        manager=TaskManager(self.root)
        manager.close()
