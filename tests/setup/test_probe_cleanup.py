"""Probe deadlines and cleanup tested with disposable subprocesses only."""
from __future__ import annotations

import importlib.util
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from scripts.setup_support import detect
from scripts.setup_support.state import SetupError


ROOT = Path(__file__).resolve().parents[2]


def running(pid: int) -> bool:
    try:
        state = Path(f"/proc/{pid}/stat").read_text().rsplit(") ", 1)[1].split()[0]
        return state not in {"Z", "X"}
    except (FileNotFoundError, ProcessLookupError):
        return False


@unittest.skipUnless(sys.platform.startswith("linux"), "Linux/WSL process ownership")
class ProbeCleanupTests(unittest.TestCase):
    def test_watchdog_stops_detached_owned_server_and_preserves_unrelated_process(self):
        with tempfile.TemporaryDirectory() as temporary:
            pids = Path(temporary) / "pids.json"
            server_code = (
                "import json,os,signal,subprocess,sys,time; from pathlib import Path; "
                "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                "helper=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'],start_new_session=True); "
                f"Path({str(pids)!r}).write_text(json.dumps([os.getpid(),helper.pid])); "
                "time.sleep(30)"
            )
            root_code = (
                "import subprocess,sys,time; "
                f"subprocess.Popen([sys.executable,'-c',{server_code!r}],start_new_session=True); "
                "time.sleep(30)"
            )
            unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                                         start_new_session=True)
            owned = []
            try:
                started = time.monotonic()
                with self.assertRaisesRegex(SetupError, "TimeoutExpired"):
                    detect.run([sys.executable, "-c", root_code], timeout=0.5)
                self.assertLess(time.monotonic() - started, 4)
                self.assertTrue(pids.is_file(), "fixture did not start its detached server")
                owned = json.loads(pids.read_text())
                for pid in owned:
                    self.assertFalse(running(pid), f"watchdog left owned PID {pid} running")
                self.assertIsNone(unrelated.poll(), "watchdog stopped an unrelated process")
            finally:
                # Rescue cleanup runs only after assertions; it cannot make a
                # surviving child satisfy the no-survivor regression.
                if pids.is_file():
                    for pid in json.loads(pids.read_text()):
                        if running(pid):
                            os.kill(pid, signal.SIGKILL)
                unrelated.kill()
                unrelated.wait(timeout=2)

    def test_reused_pid_is_never_signalled(self):
        with mock.patch.object(detect, "_process_identity", return_value=(1, "new-birth")), \
             mock.patch.object(detect.os, "kill") as kill:
            detect._kill_owned_descendants([(12345, "old-birth")])
        kill.assert_not_called()

    @unittest.skipUnless(importlib.util.find_spec("mcp") is not None, "existing optional MCP SDK unavailable")
    def test_whole_probe_deadline_reaps_sdk_detached_server_before_watchdog(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            pidfile = directory / "server.pid"
            server = directory / "fake-server"
            server.write_text(
                f"#!{sys.executable}\n"
                "import json, os, sys, time\n"
                "from pathlib import Path\n"
                "Path(os.environ['FIXTURE_PID_FILE']).write_text(str(os.getpid()))\n"
                "page = 0\n"
                "for line in sys.stdin:\n"
                "    request = json.loads(line)\n"
                "    if 'id' not in request: continue\n"
                "    if request['method'] == 'initialize':\n"
                "        result = {'protocolVersion': request['params']['protocolVersion'], "
                "'capabilities': {'tools': {}}, 'serverInfo': {'name': 'fixture', 'version': '1'}}\n"
                "    elif request['method'] == 'tools/list':\n"
                "        time.sleep(0.02)\n"
                "        page += 1\n"
                "        result = {'tools': [], 'nextCursor': str(page)}\n"
                "    else: raise RuntimeError('unexpected method')\n"
                "    print(json.dumps({'jsonrpc':'2.0', 'id':request['id'], 'result':result}), flush=True)\n"
            )
            server.chmod(0o755)
            probe = ROOT / "scripts/setup_support/probe_mcp.py"
            runner = (
                "import asyncio,runpy,sys; "
                f"namespace=runpy.run_path({str(probe)!r}); sys.argv=['probe',{str(server)!r}]; "
                "asyncio.run(namespace['main'](deadline_seconds=0.25))"
            )
            try:
                with self.assertRaises(SetupError) as raised:
                    detect.run([sys.executable, "-c", runner], timeout=8,
                               env={**os.environ, "FIXTURE_PID_FILE": str(pidfile)})
                self.assertNotIn("TimeoutExpired", str(raised.exception), "outer watchdog fired")
                self.assertTrue(pidfile.is_file(), "fake SDK server did not initialize")
                self.assertFalse(running(int(pidfile.read_text())), "SDK teardown left its server running")
            finally:
                if pidfile.is_file() and running(int(pidfile.read_text())):
                    os.kill(int(pidfile.read_text()), signal.SIGKILL)


if __name__ == "__main__":
    unittest.main()
