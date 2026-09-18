from __future__ import annotations

import contextlib
import io
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from scripts import run_tests
from scripts.codex import launcher_config


class TestRunnerTests(unittest.TestCase):
    def test_failure_is_propagated_and_both_suites_run(self) -> None:
        with mock.patch.object(run_tests, "run_suite", side_effect=[1, 0, 0]) as command:
            self.assertEqual(run_tests.main(), 1)
        self.assertEqual(command.call_count, 3)
        self.assertEqual(command.call_args_list, [mock.call(suite) for suite in run_tests.SUITES])

    def test_unsupported_python_is_rejected_before_running_tests(self) -> None:
        with mock.patch.object(run_tests.sys, "version_info", (3, 10)), \
             mock.patch.object(run_tests, "run_suite") as command:
            self.assertEqual(run_tests.main(), 2)
            command.assert_not_called()

    @unittest.skipUnless(run_tests.os.name == "posix", "POSIX process-group cleanup")
    def test_timeout_signals_only_the_suite_process_group(self) -> None:
        process = mock.Mock(pid=98765)
        process.wait.side_effect = [subprocess.TimeoutExpired("suite", 120), -9]
        with mock.patch.object(run_tests.subprocess, "Popen") as popen, \
             mock.patch.object(run_tests.os, "killpg") as killpg, \
             contextlib.redirect_stderr(io.StringIO()) as errors:
            popen.return_value.__enter__.return_value = process
            self.assertEqual(run_tests.run_suite("fixture"), 124)
        self.assertIn("test completion was not verified", errors.getvalue())
        self.assertTrue(popen.call_args.kwargs["start_new_session"])
        self.assertEqual(popen.call_args.kwargs["cwd"], run_tests.ROOT)
        killpg.assert_called_once_with(process.pid, run_tests.signal.SIGKILL)
        self.assertEqual(process.wait.call_count, 2)

    def test_real_stalled_suite_fails_and_next_suite_runs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stalled, healthy = root/"stalled", root/"healthy"
            stalled.mkdir(); healthy.mkdir()
            (stalled/"test_stall.py").write_text(
                "import time, unittest\n"
                "class Stalled(unittest.TestCase):\n"
                "    def test_stall(self): time.sleep(60)\n"
            )
            marker = root/"next-suite-ran"
            (healthy/"test_healthy.py").write_text(
                "import unittest\nfrom pathlib import Path\n"
                "class Healthy(unittest.TestCase):\n"
                f"    def test_runs(self): Path({str(marker)!r}).touch()\n"
            )
            started = time.monotonic()
            with mock.patch.object(run_tests, "SUITES", (str(stalled), str(healthy))), \
                 mock.patch.object(run_tests, "SUITE_TIMEOUT_SECONDS", 3), \
                 contextlib.redirect_stderr(io.StringIO()) as errors, \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(run_tests.main(), 1)
            self.assertIn("timed out after 3 seconds", errors.getvalue())
            self.assertTrue(marker.exists(), "remaining suite was not executed")
            self.assertLess(time.monotonic() - started, 15)

    def test_transport_loading_reports_the_minimum_python_version(self) -> None:
        with mock.patch.object(launcher_config.sys, "version_info", (3, 10)):
            with self.assertRaisesRegex(ValueError, "Python 3.11"):
                launcher_config.require_supported_python()
