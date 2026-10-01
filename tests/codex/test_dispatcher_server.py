"""Real SDK protocol tests; run with dispatcher/requirements.txt installed."""
from __future__ import annotations
import asyncio
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
    from scripts.codex.specialist_runtime.models import ExecutionState as State


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

    async def test_nine_explicit_tools_and_no_escape_arguments(self):
        async with Client(self.server) as client:
            listed = await client.list_tools()
            self.assertEqual({tool.name for tool in listed.tools},set(INPUTS))
            self.assertEqual(len(listed.tools),9)
            for tool in listed.tools:
                self.assertFalse(tool.input_schema['additionalProperties'])
                self.assertFalse(set(tool.input_schema.get('properties',{})) & {
                    'command','profile','environment','cwd','codex_executable','specialist','mcp_server'})
            schemas = {tool.name: tool.input_schema for tool in listed.tools}
            self.assertEqual(set(schemas['start_ode_modeler']['properties']),
                             {'task', 'record_session_id', 'approved_tools'})
            review_schema = schemas['start_literature_reviewer']['properties']['review_kind']
            self.assertEqual(review_schema['enum'], ['edge', 'ode'])
            self.assertEqual(review_schema['default'], 'edge')
            model_tools = ('start_network_curator', 'start_boolean_dynamics_modeler',
                           'start_multicellular_configurator', 'start_ode_modeler')
            for name in model_tools:
                for extra in ('profile', 'command', 'mcp_server', 'codex_executable',
                              'cwd', 'allow_web_search', 'review_kind'):
                    result = await client.call_tool(name, {'task': 'inspect', extra: True})
                    self.assertTrue(result.is_error, (name, extra))
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
                ('start_ode_dynamics_modeler',{'task':'inspect'}),
                ('start_ode_modeler',{'task':' '}),
                ('start_ode_modeler',{'task':'inspect','record_session_id':'../outside'}),
                ('start_ode_modeler',{'task':'inspect','approved_tools':['*']}),
                ('start_ode_modeler',{'task':'inspect','approved_tools':['delete_session']}),
                ('start_literature_reviewer',{'task':'inspect','review_kind':'ode'}),
                ('start_literature_reviewer',{'task':'inspect','review_kind':'ode','record_session_id':None}),
                ('start_literature_reviewer',{'task':'inspect','review_kind':'ode','record_session_id':''}),
                ('start_literature_reviewer',{'task':'inspect','review_kind':'ode','record_session_id':42}),
                ('start_literature_reviewer',{'task':'inspect','review_kind':'ode','record_session_id':'../outside'}),
                *[('start_literature_reviewer', {'task':'inspect','review_kind':mode})
                  for mode in ('unknown', 'ODE', '', None, False, 1, [])],
                ('get_specialist_task',{'task_id':'../outside'}),
                ('get_specialist_events',{'task_id':'a'*32,'limit':201}),
            ):
                result=await client.call_tool(name,args)
                self.assertTrue(result.is_error,(name,args,result))
            result=await client.call_tool('list_specialist_tasks',{})
            self.assertEqual(result.structured_content,{'tasks':[]})

    async def test_ode_and_literature_modes_forwarded_and_queryable(self):
        requests = []
        def runner(request, **kwargs):
            requests.append(request)
            result = kwargs['prepared']
            for state in (State.PREFLIGHTING, State.RUNNING, State.VALIDATING, State.RECORDING):
                result.execution_state = state
                kwargs['state_callback'](result)
            kwargs['event_callback']({'type': 'heartbeat', 'summary': 'Protocol test progress'})
            # This fake tests adapter and manager plumbing; runtime tests validate real handoffs.
            result.handoff = {'status': 'blocked', 'specialist': request.specialist}
            result.execution_state = State.SUCCEEDED
            result.return_code = 0
            return result
        self.manager.runner = runner
        cases = (
            ('start_ode_modeler', {'record_session_id': 'biomass-test',
                                   'approved_tools': ['export_model_bundle']}, 'ode_modeler', None),
            ('start_literature_reviewer', {}, 'literature_reviewer', 'edge'),
            ('start_literature_reviewer', {'review_kind': 'edge', 'record_session_id': 'neko-test'},
             'literature_reviewer', 'edge'),
            ('start_literature_reviewer', {'review_kind': 'ode', 'record_session_id': 'biomass-test',
                                           'allow_web_search': True}, 'literature_reviewer', 'ode'),
        )
        async with Client(self.server) as client:
            for name, arguments, role, mode in cases:
                with self.subTest(name=name, mode=mode, arguments=arguments):
                    task = 'Bounded protocol task  \n'
                    result = await client.call_tool(name, {'task': task, **arguments})
                    self.assertFalse(result.is_error, result)
                    task_id = result.structured_content['task_id']
                    await asyncio.to_thread(self.manager.workers[task_id][0].join, 3)
                    self.assertFalse(self.manager.workers[task_id][0].is_alive())
                    request = requests[-1]
                    self.assertEqual(request.specialist, role)
                    self.assertEqual(request.task, task)
                    self.assertEqual(request.review_kind, mode)
                    self.assertEqual(request.record_session_id, arguments.get('record_session_id'))
                    self.assertEqual(request.approved_tools, tuple(arguments.get('approved_tools', [])))
                    self.assertEqual(request.allow_web_search, arguments.get('allow_web_search', False))
                    queried = await client.call_tool('get_specialist_task', {'task_id': task_id})
                    record = queried.structured_content
                    self.assertEqual(record['execution_state'], 'succeeded', record)
                    self.assertEqual(record['review_kind'], mode)
                    self.assertEqual(record['record_session_id'], request.record_session_id)
                    self.assertEqual(record['handoff'], {'status': 'blocked', 'specialist': role})
                    self.assertEqual((self.root / record['artifact_dir'] / 'task.txt').read_text(), task)
                    events = await client.call_tool('get_specialist_events', {'task_id': task_id})
                    self.assertIn('Protocol test progress', json.dumps(events.structured_content))
                    listed = await client.call_tool('list_specialist_tasks', {})
                    listed_record = next(row for row in listed.structured_content['tasks']
                                         if row['task_id'] == task_id)
                    self.assertEqual(listed_record['review_kind'], mode)
                    self.assertNotIn('handoff', listed_record)
                    cancelled = await client.call_tool('cancel_specialist_task', {'task_id': task_id})
                    self.assertEqual(cancelled.structured_content['execution_state'], 'succeeded')

    async def test_start_returns_id_and_failure_is_queryable(self):
        with mock.patch.object(executor,'resolve_codex_executable',return_value='codex'), \
             mock.patch.object(executor,'profile_path',return_value=self.root/'missing'):
            async with Client(self.server) as client:
                result=await client.call_tool('start_network_curator',{'task':'inspect'})
                self.assertFalse(result.is_error,result)
                task_id=result.structured_content['task_id']
                await asyncio.to_thread(self.manager.workers[task_id][0].join,3)
                result=await client.call_tool('get_specialist_task',{'task_id':task_id})
                self.assertEqual(result.structured_content['execution_state'],'failed')
                self.assertIsNone(result.structured_content['handoff'])
                events=await client.call_tool('get_specialist_events',{'task_id':task_id})
                self.assertTrue(events.structured_content['events'])
                cancelled=await client.call_tool('cancel_specialist_task',{'task_id':task_id})
                self.assertEqual(cancelled.structured_content['execution_state'],'failed')

    async def test_stdio_transport_and_clean_disconnect(self):
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
                self.assertEqual(len(listed.tools),9)
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
