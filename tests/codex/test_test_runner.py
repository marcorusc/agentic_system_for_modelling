from __future__ import annotations

import unittest
from unittest import mock

from scripts import run_tests
from scripts.codex import launcher_config


class TestRunnerTests(unittest.TestCase):
    def test_failure_is_propagated_and_both_suites_run(self) -> None:
        with mock.patch.object(run_tests.subprocess, "run", side_effect=[
            mock.Mock(returncode=1), mock.Mock(returncode=0), mock.Mock(returncode=0)
        ]) as command:
            self.assertEqual(run_tests.main(), 1)
        self.assertEqual(command.call_count, 3)
        self.assertEqual([call.kwargs["cwd"] for call in command.call_args_list],
                         [run_tests.ROOT, run_tests.ROOT, run_tests.ROOT])

    def test_unsupported_python_is_rejected_before_running_tests(self) -> None:
        with mock.patch.object(run_tests.sys, "version_info", (3, 10)), \
             mock.patch.object(run_tests.subprocess, "run") as command:
            self.assertEqual(run_tests.main(), 2)
            command.assert_not_called()

    def test_transport_loading_reports_the_minimum_python_version(self) -> None:
        with mock.patch.object(launcher_config.sys, "version_info", (3, 10)):
            with self.assertRaisesRegex(ValueError, "Python 3.11"):
                launcher_config.require_supported_python()
