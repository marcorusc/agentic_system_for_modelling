#!/usr/bin/env python3
"""Regression tests for the main-session data orchestrator guard hook."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[2]
GUARD = SOURCE_ROOT / ".claude" / "scripts" / "data_orchestrator_guard.py"
SETTINGS = SOURCE_ROOT / ".claude" / "settings.json"
VENDOR_SCRIPT = "vendor/scientific-agent-skills/depmap/scripts/depmap_data.py"


class OrchestratorGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="data-orchestrator-guard-test-")
        base = Path(self.temporary.name).resolve()
        self.root = base / "project"
        self.outside = base / "outside"
        self.outside.mkdir()
        scripts = self.root / "vendor" / "scientific-agent-skills" / "depmap" / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "depmap_data.py").write_text("")
        (self.root / "vendor" / "scientific-agent-skills" / "VENDOR.md").write_text("")
        (self.root / ".venv-data" / "bin").mkdir(parents=True)
        (self.root / ".venv-data" / "bin" / "python").write_text("")
        (self.root / "scripts" / "data").mkdir(parents=True)
        for name in ("vendor_lock.py", "session.py", "fetch.py", "manifest.py", "handoff.py"):
            (self.root / "scripts" / "data" / name).write_text("")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_guard(self, command: object = None, raw: str | None = None, **extra: object):
        payload = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(self.root), **extra}
        environment = os.environ.copy()
        environment["CLAUDE_PROJECT_DIR"] = str(self.root)
        return subprocess.run([sys.executable, str(GUARD)],
                              input=raw if raw is not None else json.dumps(payload),
                              text=True, capture_output=True, env=environment, check=False)

    def assert_denied(self, command: object, **extra: object) -> None:
        result = self.run_guard(command, **extra)
        self.assertEqual(result.returncode, 2, (command, result))
        self.assertIn("Orchestrator blocked: ", result.stderr)
        self.assertIn("data-analyst", result.stderr)
        self.assertEqual(result.stdout, "")

    def assert_allowed(self, command: object, **extra: object) -> None:
        result = self.run_guard(command, **extra)
        self.assertEqual(result.returncode, 0, (command, result.stderr))
        self.assertEqual(result.stderr, "")

    def test_main_session_vendor_execution_denied(self) -> None:
        for command in (
            f"python3 {VENDOR_SCRIPT}",
            f"python3 -E -s {VENDOR_SCRIPT} --gene TP53",
            f"python {VENDOR_SCRIPT}",
            f"/usr/bin/python3.12 ./{VENDOR_SCRIPT}",
            f"python3 {self.root}/{VENDOR_SCRIPT}",
            f"python3 'vendor/scientific-agent-skills/depmap/scripts/depmap_data.py'",
            f"uv run {VENDOR_SCRIPT}",
            f"uv run python {VENDOR_SCRIPT}",
            f"uvx --from x {VENDOR_SCRIPT}",
            f"env PYTHONPATH=. python3 {VENDOR_SCRIPT}",
            f"FOO=1 python3 {VENDOR_SCRIPT}",
            f"timeout 10 python3 {VENDOR_SCRIPT}",
            f"./{VENDOR_SCRIPT}",
            f"{VENDOR_SCRIPT} --help",
            f"{self.root}/{VENDOR_SCRIPT}",
            f"echo hi; python3 {VENDOR_SCRIPT}",
            f"ls && python3 {VENDOR_SCRIPT}",
            f"ls\npython3 {VENDOR_SCRIPT}",
            f"echo $(python3 {VENDOR_SCRIPT})",
            f"echo `python3 {VENDOR_SCRIPT}`",
            f"(python3 {VENDOR_SCRIPT})",
            f"cat x | python3 {VENDOR_SCRIPT}",
            f"find vendor/scientific-agent-skills -name '*.py' -exec python3 {{}} \\;",
            f"echo {VENDOR_SCRIPT} | xargs python3",
            f"bash -c 'python3 {VENDOR_SCRIPT}'",
            f"sh -c \"cd vendor && python3 scientific-agent-skills/depmap/scripts/depmap_data.py\"",
            "python3 -c \"import runpy; runpy.run_path('vendor/scientific-agent-skills/depmap/scripts/depmap_data.py')\"",
            "cd vendor/scientific-agent-skills/depmap/scripts && python3 depmap_data.py",
            "cd vendor; cd scientific-agent-skills/depmap/scripts; python3 depmap_data.py",
            f"python3 vendor/scientific-agent-skills/../scientific-agent-skills/depmap/scripts/depmap_data.py",
            f"python3 vendor/scientific-agent-skills//depmap/scripts/depmap_data.py",
            f"python3 --script={VENDOR_SCRIPT}",
            f"python3 {VENDOR_SCRIPT} 'unbalanced",
            f"if true; then python3 {VENDOR_SCRIPT}; fi",
        ):
            with self.subTest(command=command):
                self.assert_denied(command)

    def test_obfuscated_vendor_execution_denied(self) -> None:
        for command in (
            f"PYTHON3 {VENDOR_SCRIPT}",
            f"python3-dbg {VENDOR_SCRIPT}",
            f"python3 vendor/scientific-agent-{{skills,x}}/depmap/scripts/depmap_data.py",
            "python3 vendor/scientific-agent-skill?/depmap/scripts/depmap_data.py",
            f"sed -n '1e python3 {VENDOR_SCRIPT}' README.md",
            f"awk 'BEGIN{{system(\"python3 {VENDOR_SCRIPT}\")}}'",
            f"pytest {VENDOR_SCRIPT}",
            f"conda run python {VENDOR_SCRIPT}",
            f"python3 -m pytest {VENDOR_SCRIPT}",
            f"cat <<EOF | bash\npython3 {VENDOR_SCRIPT}\nEOF",
            f"python3 VENDOR/Scientific-Agent-Skills/depmap/scripts/depmap_data.py",
            ".VENV-DATA/bin/python x.py",
            f"p=vendor/scientific-agent-skills; python3 $p/depmap/scripts/depmap_data.py",
            f"export P=vendor/scientific-agent-skills && python3 $P/depmap/scripts/depmap_data.py",
            f"git -c alias.x='!python3 {VENDOR_SCRIPT}' x",
        ):
            with self.subTest(command=command):
                self.assert_denied(command)

    def test_copied_vendor_script_execution_denied(self) -> None:
        source = self.root / VENDOR_SCRIPT
        source.write_text("print('vendored')\n")
        copy = self.root / "runs" / "orchestrator" / "copy.py"
        copy.parent.mkdir(parents=True)
        copy.write_bytes(source.read_bytes())
        self.assert_denied("python3 runs/orchestrator/copy.py")
        self.assert_allowed("cat runs/orchestrator/copy.py")
        copy.write_text("print('own analysis')\n")
        self.assert_allowed("python3 runs/orchestrator/copy.py")

    def test_commit_message_text_is_not_execution(self) -> None:
        for command in (
            f"git commit -m \"$(cat <<'EOF'\nrun python3 {VENDOR_SCRIPT}\nEOF\n)\"",
            "git commit -m \"$(cat <<'EOF'\nuse .venv-data/bin/python\nEOF\n)\"",
            "git commit -m 'mention .venv-data in prose'",
            "git add vendor/scientific-agent-skills && python3 scripts/run_tests.py",
        ):
            with self.subTest(command=command):
                self.assert_allowed(command)

    def test_vendor_execution_via_symlink_or_cwd_denied(self) -> None:
        link = self.outside / "renamed.py"
        try:
            link.symlink_to(self.root / VENDOR_SCRIPT)
        except OSError as error:
            self.skipTest(f"symlinks unavailable: {error}")
        self.assert_denied(f"python3 {link}")
        scripts = self.root / "vendor" / "scientific-agent-skills" / "depmap" / "scripts"
        self.assert_denied("python3 depmap_data.py", cwd=str(scripts))
        self.assert_denied("python3 -m depmap_data", cwd=str(scripts))

    def test_venv_data_denied(self) -> None:
        for command in (
            ".venv-data/bin/python -E -s scripts/data/session.py new --purpose x",
            "./.venv-data/bin/python x.py",
            f"{self.root}/.venv-data/bin/python x.py",
            ".venv-data/bin/pip install pandas",
            "source .venv-data/bin/activate && python x.py",
            ". .venv-data/bin/activate",
            ".venv-cellprofiler/bin/cellprofiler -c",
            "VIRTUAL_ENV=.venv-data python3 x.py",
            "uv pip install --python=.venv-data/bin/python pandas",
            "PATH=.venv-data/bin:$PATH python x.py",
            "ls .venv-data",
            "rm -rf .venv-data",
            ".venv-dat?/bin/python x.py",
            "scripts/../.venv-data/bin/python x.py",
        ):
            with self.subTest(command=command):
                self.assert_denied(command)
        self.assert_denied("bin/python x.py", cwd=str(self.root / ".venv-data"))

    def test_git_and_read_commands_on_vendor_allowed(self) -> None:
        for command in (
            "git add vendor/scientific-agent-skills",
            "git diff -- vendor/scientific-agent-skills",
            "git log --oneline -- vendor/scientific-agent-skills/depmap",
            "cat vendor/scientific-agent-skills/VENDOR.md",
            f"cat {VENDOR_SCRIPT}",
            "ls -la vendor/scientific-agent-skills/depmap/scripts",
            "grep -rn TP53 vendor/scientific-agent-skills",
            f"grep -n python3 {VENDOR_SCRIPT}",
            "grep -rn 'python3 scripts/' vendor/scientific-agent-skills",
            f"head -n 20 {VENDOR_SCRIPT}",
            f"sed -n '1,40p' {VENDOR_SCRIPT}",
            f"wc -l {VENDOR_SCRIPT}",
            "python3 -m unittest discover -s tests/data -p 'test_vendor*.py' -v",
            "python3 -m unittest tests.data.test_vendor",
            "git commit -m \"vendor: don't touch\"",
            "git status --short && git diff --stat",
        ):
            with self.subTest(command=command):
                self.assert_allowed(command)

    def test_vendor_lock_verify_allowed(self) -> None:
        self.assert_allowed("python3 scripts/data/vendor_lock.py verify")
        self.assert_allowed("python3 -I scripts/data/vendor_lock.py verify")

    def test_data_analyst_allowed(self) -> None:
        self.assert_allowed(f".venv-data/bin/python -E -s {VENDOR_SCRIPT}",
                            agent_type="data-analyst", agent_id="a1")
        self.assert_allowed(f".venv-data/bin/python -E -s scripts/data/session.py new --purpose x",
                            agent_type="data-analyst", agent_id="agent-7")

    def test_agent_type_without_agent_id_denied(self) -> None:
        for extra in ({"agent_type": "data-analyst"}, {"agent_type": "data-analyst", "agent_id": ""},
                      {"agent_type": "data-analyst", "agent_id": None},
                      {"agent_type": "data-analyst", "agent_id": 7}):
            with self.subTest(extra=extra):
                self.assert_denied(f".venv-data/bin/python -E -s {VENDOR_SCRIPT}", **extra)
                self.assert_denied(f"python3 {VENDOR_SCRIPT}", **extra)

    def test_orchestrator_handoff_build_denied(self) -> None:
        for command in (
            "python3 scripts/data/handoff.py build --session x --status completed --notes n.json",
            "python3 -m scripts.data.handoff build --session x --status completed --notes n.json",
            "python3 scripts/data/handoff.py --help",
        ):
            with self.subTest(command=command):
                self.assert_denied(command)

    def test_main_session_data_tools_denied(self) -> None:
        session = "data-20261112T120000Z-0123abcd"
        for command in (
            "python3 scripts/data/session.py new --purpose x",
            f"python3 scripts/data/fetch.py --session {session} --url http://x --release r",
            f"python3 scripts/data/manifest.py build --session {session}",
            "python3 -I scripts/data/session.py new --purpose x",
            f"python3 {self.root}/scripts/data/fetch.py --session {session} --release r",
            "python3 ./scripts/data/manifest.py build --session x",
            "python3 scripts/data/manifest.py --help",
            "python3 -m scripts.data.session new --purpose x",
            "python3 -m scripts.data.fetch --session x --release r",
            "python3 -m scripts.data.manifest build --session x",
            "uv run scripts/data/session.py new --purpose x",
            "./scripts/data/session.py new --purpose x",
            "scripts/data/fetch.py --session x --release r",
            "cd scripts/data && python3 session.py new --purpose x",
            "p=scripts/data; python3 $p/session.py new --purpose x",
            "echo x | python3 scripts/data/fetch.py --session x --release r",
            "python3 scripts/data/{session,common}.py new --purpose x",
            "python3 SCRIPTS/DATA/SESSION.PY new --purpose x",
        ):
            with self.subTest(command=command):
                self.assert_denied(command)
        self.assert_denied("python3 session.py new --purpose x", cwd=str(self.root / "scripts" / "data"))
        self.assert_denied("python3 manifest.py build --session x", cwd=str(self.root / "scripts" / "data"))
        link = self.outside / "s.py"
        try:
            link.symlink_to(self.root / "scripts" / "data" / "session.py")
        except OSError as error:
            self.skipTest(f"symlinks unavailable: {error}")
        self.assert_denied(f"python3 {link} new --purpose x")

    def test_main_session_verify_tools_allowed(self) -> None:
        session = "data-20261112T120000Z-0123abcd"
        for command in (
            f"python3 scripts/data/manifest.py verify --session {session}",
            f"python3 -m scripts.data.manifest verify --session {session}",
            "python3 scripts/data/vendor_lock.py verify",
            "git add scripts/data/session.py scripts/data/fetch.py",
            "cat scripts/data/manifest.py",
            "grep -n build scripts/data/manifest.py",
            "python3 -m unittest tests.data.test_session tests.data.test_fetch",
        ):
            with self.subTest(command=command):
                self.assert_allowed(command)

    def test_other_agents_denied(self) -> None:
        for agent in ("network-curator", "Data-Analyst", "data-analyst ", ["data-analyst"], None):
            with self.subTest(agent=agent):
                self.assert_denied(f"python3 {VENDOR_SCRIPT}", agent_type=agent, agent_id="a1")

    def test_unrelated_command_allowed(self) -> None:
        for command in ("git status", "python3 scripts/run_tests.py", "ls -la", "echo hello | wc -c",
                        "python3 scripts/state.py show", "uv --version",
                        "git commit -m \"$(cat <<'EOF'\nfeat: it's fine\nEOF\n)\""):
            with self.subTest(command=command):
                self.assert_allowed(command)

    def test_non_bash_tools_ignored(self) -> None:
        payload = {"tool_name": "Read", "tool_input": {"file_path": str(self.root / VENDOR_SCRIPT)}}
        result = self.run_guard(raw=json.dumps(payload))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_malformed_input_denied(self) -> None:
        for raw in ("{oops", "[]", json.dumps({"tool_name": "Bash", "tool_input": "ls"}),
                    json.dumps({"tool_name": "Bash", "tool_input": {"command": 5}}),
                    json.dumps({"tool_name": "Bash", "tool_input": {}})):
            with self.subTest(raw=raw):
                result = self.run_guard(raw=raw)
                self.assertEqual(result.returncode, 2, result)
                self.assertIn("Orchestrator blocked: ", result.stderr)

    def test_settings_registers_hook_and_keeps_existing(self) -> None:
        settings = json.loads(SETTINGS.read_text())
        pre = settings["hooks"]["PreToolUse"]
        commands = {(entry["matcher"], hook["command"]) for entry in pre for hook in entry["hooks"]}
        self.assertIn(("Bash", 'python3 "$CLAUDE_PROJECT_DIR/.claude/scripts/data_orchestrator_guard.py"'),
                      commands)
        self.assertIn(("Agent|Task", 'python3 "$CLAUDE_PROJECT_DIR/.claude/scripts/stage_gate_guard.py"'),
                      commands)
        self.assertIn("SubagentStop", settings["hooks"])


if __name__ == "__main__":
    unittest.main()
