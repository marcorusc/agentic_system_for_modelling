"""ODE and evidence-mode operational controls; workers perform no modelling."""
from __future__ import annotations

import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from unittest import mock

from scripts.codex.dispatcher.manager import TaskManager
from scripts.codex.dispatcher.store import TaskStore
from scripts.codex.specialist_runtime import executor
from scripts.codex.specialist_runtime.models import (
    ExecutionState as State,
    SpecialistInvocationRequest as Request,
)


class OdeDispatcherTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        patch = mock.patch.object(executor, 'PROJECT_ROOT', self.root)
        patch.start()
        self.addCleanup(patch.stop)

    def manager(self, runner):
        manager = TaskManager(self.root, runner=runner)
        self.addCleanup(manager.close)
        return manager

    def finish(self, manager, task_id):
        manager.workers[task_id][0].join(3)
        self.assertFalse(manager.workers[task_id][0].is_alive())
        return manager.get(task_id)

    def test_ode_and_both_literature_modes_share_existing_concurrency_limits(self):
        started = threading.Event()

        def runner(request, **kwargs):
            result = kwargs['prepared']
            result.execution_state = State.PREFLIGHTING
            kwargs['state_callback'](result)
            started.set()
            wake = threading.Event()
            while not kwargs['cancellation_requested']():
                wake.wait(.01)
            result.execution_state = State.CANCELLED
            result.return_code = 130
            return result

        manager = self.manager(runner)
        model = manager.start(Request('ode_modeler', 'Inspect candidate', record_session_id='biomass-test'))
        self.assertTrue(started.wait(1))
        for role in ('network_curator', 'boolean_dynamics_modeler',
                     'multicellular_configurator', 'ode_modeler'):
            with self.subTest(role=role), self.assertRaisesRegex(ValueError, 'concurrency'):
                manager.start(Request(role, 'Inspect candidate'))
        reviews = [
            manager.start(Request('literature_reviewer', 'Review edges')),
            manager.start(Request('literature_reviewer', 'Review ODE claims',
                                  review_kind='ode', record_session_id='biomass-test')),
        ]
        for mode in ('edge', 'ode'):
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, 'concurrency'):
                manager.start(Request('literature_reviewer', 'Review claims',
                                      review_kind=mode, record_session_id='biomass-test'))
        self.assertEqual(len(manager.list()), 3)
        for task, mode in ((model, None), (reviews[0], 'edge'), (reviews[1], 'ode')):
            task_id = task['task_id']
            manager.cancel(task_id)
            record = self.finish(manager, task_id)
            self.assertEqual(record['execution_state'], 'cancelled')
            self.assertEqual(record['review_kind'], mode)
            self.assertTrue(record['cancellation_requested'])
            self.assertIsNone(record['handoff'])
            artifact = self.root / record['artifact_dir']
            self.assertTrue((artifact / 'task.txt').is_file())
            events = manager.events(task_id)['events']
            self.assertIn('cancellation_requested', [event['type'] for event in events])
            self.assertEqual(manager.cancel(task_id)['execution_state'], 'cancelled')

    def test_restart_preserves_ode_review_identity_and_partial_artifacts(self):
        store = TaskStore(self.root)
        task_ids = []
        for role, mode in (('ode_modeler', None), ('literature_reviewer', 'ode')):
            task_id = uuid.uuid4().hex
            task_ids.append(task_id)
            artifact = self.root / '.codex-tasks' / task_id
            artifact.mkdir(parents=True)
            (artifact / 'task.txt').write_text('Preserved interrupted task')
            store.create({
                'schema_version': 1, 'task_id': task_id, 'specialist': role,
                'execution_state': 'running', 'created_at': 'now',
                'invocation_id': task_id, 'prompt_sha256': 'hash',
                'record_session_id': 'biomass-test', 'review_kind': mode,
                'artifact_dir': str(artifact.relative_to(self.root)), 'handoff': None,
            })
        runner = mock.Mock(side_effect=AssertionError('Restart must not run a worker'))
        manager = self.manager(runner)
        for task_id, mode in zip(task_ids, (None, 'ode')):
            record = manager.get(task_id)
            self.assertEqual(record['execution_state'], 'failed')
            self.assertEqual(record['review_kind'], mode)
            self.assertEqual(record['record_session_id'], 'biomass-test')
            self.assertIn('automatic resumption is prohibited', record['error'])
            self.assertEqual((self.root / record['artifact_dir'] / 'task.txt').read_text(),
                             'Preserved interrupted task')
            self.assertEqual(manager.events(task_id)['events'][-1]['type'], 'dispatcher.recovery')
        self.assertEqual(manager.workers, {})
        runner.assert_not_called()


if __name__ == '__main__':
    unittest.main()
