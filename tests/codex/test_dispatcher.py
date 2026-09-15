from __future__ import annotations
import json
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path
from unittest import mock
from scripts.codex.dispatcher.manager import TaskManager
from scripts.codex.dispatcher.store import TaskStore
from scripts.codex.specialist_runtime import executor
from scripts.codex.specialist_runtime.lifecycle import TRANSITIONS, validate_transition, TERMINAL
from scripts.codex.specialist_runtime.models import ExecutionState as State, SpecialistInvocationRequest as Request
from scripts.codex.launcher_config import SPECIALISTS, validate_mcp_inventory

class DispatcherTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        patch = mock.patch.object(executor, 'PROJECT_ROOT', self.root)
        patch.start(); self.addCleanup(patch.stop)

    def manager(self, runner=executor.execute):
        manager = TaskManager(self.root, runner=runner)
        self.addCleanup(manager.close)
        return manager

    def wait(self, manager, task_id):
        manager.workers[task_id][0].join(timeout=5)
        self.assertFalse(manager.workers[task_id][0].is_alive())
        return manager.get(task_id)

    def record(self, store, state='queued'):
        return store.create({'schema_version':1, 'task_id':uuid.uuid4().hex,
            'specialist':'network_curator', 'execution_state':state,
            'created_at':'now', 'invocation_id':'invocation', 'prompt_sha256':'hash'})

    def test_all_lifecycle_transitions(self):
        for previous in State:
            for following in State:
                if following in TRANSITIONS[previous]:
                    validate_transition(previous, following)
                else:
                    with self.assertRaises(ValueError):
                        validate_transition(previous, following)

    def test_atomic_failure_preserves_previous_record(self):
        store = TaskStore(self.root)
        record = self.record(store)
        with mock.patch('scripts.codex.dispatcher.store.os.replace', side_effect=OSError('disk failed')):
            with self.assertRaises(OSError):
                store.update(record['task_id'], execution_state='preflighting')
        self.assertEqual(store.read(record['task_id'])['execution_state'], 'queued')
        self.assertFalse(list((store.root/'tasks').glob('.task-*')))

    def test_corruption_is_isolated_and_path_traversal_rejected(self):
        store = TaskStore(self.root)
        valid, corrupt = self.record(store), self.record(store)
        store.path(corrupt['task_id']).write_text('broken')
        self.assertEqual(len(store.list()), 2)
        self.assertEqual(store.read(valid['task_id'])['execution_state'], 'queued')
        self.assertTrue(any(r.get('error') == 'corrupt task record' for r in store.list()))
        for task_id in ('../x', '', '0'*32+'/x', 'unknown', 'a'*32):
            with self.assertRaises(ValueError): store.read(task_id)
        store.path(corrupt['task_id']).write_text(json.dumps(dict(corrupt, schema_version=999)))
        with self.assertRaises(ValueError): store.read(corrupt['task_id'])

    def test_symlink_roots_and_records_rejected(self):
        with tempfile.TemporaryDirectory() as outside:
            (self.root/'.dispatcher').symlink_to(outside)
            with self.assertRaises(ValueError): TaskStore(self.root)
            (self.root/'.dispatcher').unlink()
            store = TaskStore(self.root)
            store.path('a'*32).symlink_to(Path(outside)/'record.json')
            with self.assertRaises(ValueError): store.read('a'*32)

    def test_restart_fails_active_states_without_rerun(self):
        store = TaskStore(self.root)
        ids = [self.record(store, state.value)['task_id'] for state in State]
        manager = self.manager()
        for task_id, previous in zip(ids, State):
            self.assertEqual(manager.get(task_id)['execution_state'], previous.value if previous in TERMINAL else 'failed')
        self.assertEqual(manager.workers, {})

    def test_second_manager_cannot_recover_live_owner(self):
        self.manager()
        with self.assertRaisesRegex(ValueError, 'another dispatcher'): TaskManager(self.root)

    def test_events_redacted_ordered_and_paginated(self):
        store = TaskStore(self.root)
        task_id = self.record(store)['task_id']
        for n in range(4):
            store.append_event(task_id, {'type':'heartbeat', 'summary':'TOKEN=secret-value', 'raw':'private reasoning'})
        events = store.events(task_id, 1, 2)
        self.assertEqual([r['sequence'] for r in events['events']], [2,3])
        self.assertEqual(events['next_sequence'], 3)
        self.assertNotIn('secret-value', json.dumps(events))
        self.assertNotIn('private reasoning', store.path(task_id,'events').read_text())
        for after, limit in ((-1,1),(0,0),(0,201),(True,1)):
            with self.assertRaises(ValueError): store.events(task_id, after, limit)

    def test_exact_task_persisted_before_worker_and_concurrency_rejected(self):
        started = threading.Event()
        def runner(request, **kwargs):
            result = kwargs['prepared']
            self.assertEqual((result.artifact_dir/'task.txt').read_text(), request.task)
            result.execution_state = State.PREFLIGHTING
            kwargs['state_callback'](result)
            started.set()
            while not kwargs['cancellation_requested'](): time.sleep(.01)
            result.execution_state = State.CANCELLED
            result.return_code = 130
            return result
        manager = self.manager(runner)
        task = manager.start(Request('network_curator', 'bounded input  \n'))
        self.assertTrue(started.wait(1))
        for role in ('network_curator','boolean_dynamics_modeler','multicellular_configurator'):
            with self.assertRaisesRegex(ValueError,'concurrency'): manager.start(Request(role,'inspect'))
        for _ in range(2): manager.start(Request('literature_reviewer','inspect'))
        with self.assertRaisesRegex(ValueError,'concurrency'): manager.start(Request('literature_reviewer','inspect'))
        manager.cancel(task['task_id'])
        self.assertEqual(self.wait(manager,task['task_id'])['execution_state'],'cancelled')
        self.assertEqual(manager.cancel(task['task_id'])['execution_state'],'cancelled')

    def test_runtime_exception_is_visible_failure(self):
        def broken(*args, **kwargs): raise ValueError('TOKEN=secret-value failed')
        manager = self.manager(broken)
        record = self.wait(manager,manager.start(Request('network_curator','inspect'))['task_id'])
        self.assertEqual(record['execution_state'],'failed')
        self.assertNotIn('secret-value',record['error'])

    def test_every_specialist_hostile_inventory_rejected(self):
        for role, (_, permitted) in SPECIALISTS.items():
            safe = [{'name':name,'enabled':name==permitted} for name in ('neko','maboss','physicell')]
            validate_mcp_inventory(safe,role)
            for name in ('neko','maboss','physicell','specialist_dispatcher','unknown'):
                if name == permitted: continue
                inventory = [row for row in safe if row['name']!=name]+[{'name':name,'enabled':True}]
                with self.subTest(role=role, prohibited=name), self.assertRaises(ValueError):
                    validate_mcp_inventory(inventory,role)
