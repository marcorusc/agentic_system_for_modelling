#!/usr/bin/env python3
"""Regression tests for the data-analyst Bash/Write guard hook."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[2]
GUARD = SOURCE_ROOT / ".claude" / "scripts" / "data_guard.py"

ACTIVE = "data-20261112T120000Z-0123abcd"
OTHER = "data-20261112T130000Z-89abcdef"
DIGEST = "a" * 64
PY = ".venv-data/bin/python -E -s"
NEW = f"{PY} scripts/data/session.py new --purpose test"


def load_guard():
    spec = importlib.util.spec_from_file_location("data_guard_under_test", GUARD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def tool_use(identity: str, command: str) -> dict:
    return {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": identity, "name": "Bash", "input": {"command": command}}]}}


def tool_result(identity: str, content: object, is_error: bool = False) -> dict:
    return {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": identity, "content": content, "is_error": is_error}]}}


def created(session: str = ACTIVE, digest: str = DIGEST) -> str:
    return f"Data session created: {session} (snapshot sha256={digest})"


class GuardFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.guard = load_guard()
        self.temporary = tempfile.TemporaryDirectory(prefix="data-guard-test-")
        base = Path(self.temporary.name).resolve()
        self.root = base / "project"
        self.outside = base / "outside"
        self.outside.mkdir()
        (self.outside / "evil.py").write_text("print('x')\n")
        root = self.root
        (root / ".venv-data" / "bin").mkdir(parents=True)
        python = root / ".venv-data" / "bin" / "python"
        try:
            python.symlink_to(sys.executable)  # venv interpreters are symlinks
        except OSError:
            python.write_text("")
        for name in ("session.py", "fetch.py", "manifest.py", "common.py"):
            (root / "scripts" / "data").mkdir(parents=True, exist_ok=True)
            (root / "scripts" / "data" / name).write_text("")
        (root / "scripts" / "data" / "notes.txt").write_text("")
        vendor = root / "vendor" / "scientific-agent-skills" / "depmap" / "scripts"
        vendor.mkdir(parents=True)
        (vendor / "depmap_data.py").write_text("")
        (root / "vendor" / "scientific-agent-skills" / "VENDOR.md").write_text("")
        for session in (ACTIVE, OTHER):
            scripts = root / "runs" / "data-analyst" / session / "scripts"
            scripts.mkdir(parents=True)
            (scripts / "analysis.py").write_text("")
            (scripts / "analysis.sh").write_text("")
            (root / "runs" / "data-analyst" / session / "outputs").mkdir()
        (root / "README.md").write_text("")
        self.session = root / "runs" / "data-analyst" / ACTIVE

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def allowed(self, command: str, active: str | None = ACTIVE, **kwargs) -> None:
        try:
            self.guard.check_bash(command, self.root, active, **kwargs)
        except ValueError as error:  # pragma: no cover - failure path
            self.fail(f"{command!r} unexpectedly denied: {error}")

    def denied(self, command: str, active: str | None = ACTIVE, contains: str = "") -> None:
        with self.assertRaises(ValueError, msg=command) as caught:
            self.guard.check_bash(command, self.root, active)
        self.assertIn(contains, str(caught.exception))

    def symlink(self, link: Path, target: Path) -> None:
        try:
            link.symlink_to(target, target_is_directory=target.is_dir())
        except OSError as error:
            self.skipTest(f"symlinks unavailable: {error}")


class BashAllowlistTests(GuardFixture):
    def test_python_session_script_allowed(self) -> None:
        self.allowed(f"{PY} runs/data-analyst/{ACTIVE}/scripts/analysis.py --top 5")
        self.allowed(f"{PY} {self.session}/scripts/analysis.py")
        self.allowed(f"./.venv-data/bin/python -E -s ./runs/data-analyst/{ACTIVE}/scripts/analysis.py")
        self.allowed(f"{self.root}/.venv-data/bin/python -E -s runs/data-analyst/{ACTIVE}/scripts/analysis.py")
        self.allowed(f"  {PY}   runs/data-analyst/{ACTIVE}/scripts/analysis.py  ")
        self.allowed(f"{PY} 'runs/data-analyst/{ACTIVE}/scripts/analysis.py' --label \"a * b (c)\"")

    def test_vendor_script_allowed(self) -> None:
        self.allowed(f"{PY} vendor/scientific-agent-skills/depmap/scripts/depmap_data.py --gene TP53")

    def test_scripts_data_allowed_with_matching_session(self) -> None:
        self.allowed(f"{PY} scripts/data/manifest.py build --session {ACTIVE} --skills depmap")
        self.allowed(f"{PY} scripts/data/manifest.py verify --session={ACTIVE}")
        self.allowed(f"{PY} scripts/data/fetch.py --session {ACTIVE} --url https://x.org/a.csv --release r1")

    def test_other_session_script_denied(self) -> None:
        self.denied(f"{PY} runs/data-analyst/{OTHER}/scripts/analysis.py")
        self.denied(f"{PY} runs/data-analyst/{ACTIVE}/outputs/analysis.py")
        self.denied(f"{PY} runs/data-analyst/{ACTIVE}/scripts/../../{OTHER}/scripts/analysis.py")
        self.denied(f"{PY} scripts/data/../../vendor/scientific-agent-skills/depmap/scripts/depmap_data.py")
        self.denied(f"{PY} {self.outside}/evil.py")
        self.denied(f"{PY} vendor/scientific-agent-skills/depmap/scripts/missing.py")
        self.denied(f"{PY} vendor/scientific-agent-skills/VENDOR.md")
        self.denied(f"{PY} runs/data-analyst/{ACTIVE}/scripts/analysis.sh")
        self.denied(f"{PY} scripts/data/notes.txt")

    def test_symlinked_script_denied(self) -> None:
        scripts = self.session / "scripts"
        self.symlink(scripts / "link.py", self.outside / "evil.py")
        self.denied(f"{PY} runs/data-analyst/{ACTIVE}/scripts/link.py", contains="symlink")
        self.symlink(scripts / "vendored.py",
                     self.root / "vendor/scientific-agent-skills/depmap/scripts/depmap_data.py")
        self.denied(f"{PY} runs/data-analyst/{ACTIVE}/scripts/vendored.py", contains="symlink")
        self.symlink(self.root / "runs" / "data-analyst" / "alias", self.session)
        self.denied(f"{PY} runs/data-analyst/alias/scripts/analysis.py")

    def test_quoted_substitution_denied(self) -> None:
        self.denied(f'{PY} runs/data-analyst/{ACTIVE}/scripts/analysis.py "$(rm -rf x)"')
        self.denied(f"{PY} runs/data-analyst/{ACTIVE}/scripts/analysis.py '$(rm -rf x)'")
        self.denied(f"{PY} runs/data-analyst/{ACTIVE}/scripts/analysis.py `rm -rf x`")
        self.denied(f"{PY} runs/data-analyst/{ACTIVE}/scripts/analysis.py $HOME")

    def test_pipe_and_redirect_denied(self) -> None:
        script = f"{PY} runs/data-analyst/{ACTIVE}/scripts/analysis.py"
        for suffix in ("| cat", "> out.txt", "< in.txt", "2>&1", "; rm -rf x", "&& ls", "|| ls", "&",
                       "\nls", "\rls", '"; ls"', "'|'"):
            with self.subTest(suffix=suffix):
                self.denied(f"{script} {suffix}")

    def test_shell_expansion_characters_denied(self) -> None:
        for command in ("ls *", "ls ~", "ls ~root", "ls {a,b}", "ls [a]b", "ls ?", "ls #x",
                        "ls (x)", "ls \\/etc", "ls !x", "ls a\x00b", "ls a\tb\x0bc", "ls café",
                        "ls ;", f"{PY} runs/data-analyst/{ACTIVE}/scripts/analysis.py *.csv"):
            with self.subTest(command=command):
                self.denied(command)

    def test_quoted_shell_characters_allowed(self) -> None:
        self.allowed("ls 'a*b' \"{x}\" '~' \"#x\"")
        self.allowed(f'{NEW} --derived-from "" ', active=None)

    def test_minus_I_denied(self) -> None:
        script = f"runs/data-analyst/{ACTIVE}/scripts/analysis.py"
        for command in (f"{PY} -I {script}", f".venv-data/bin/python -I {script}",
                        f".venv-data/bin/python -I -E -s {script}", f".venv-data/bin/python -E {script}",
                        f".venv-data/bin/python -s -E {script}", f".venv-data/bin/python {script}",
                        f"{PY} -c 'print(1)'", f"{PY} -m pip install x", f"{PY}",
                        f".venv-data/bin/python -Es {script}", f"{PY} -- {script}"):
            with self.subTest(command=command):
                self.denied(command)

    def test_system_python_denied(self) -> None:
        script = f"runs/data-analyst/{ACTIVE}/scripts/analysis.py"
        for interpreter in ("python3", "python", "/usr/bin/python3", sys.executable,
                            str(Path(sys.executable).resolve()), ".venv-data/bin/python3",
                            "venv-data/bin/python", ".venv-data/bin/../bin/python",
                            f"{self.outside}/.venv-data/bin/python", "uv run python"):
            with self.subTest(interpreter=interpreter):
                self.denied(f"{interpreter} -E -s {script}")

    def test_symlinked_venv_directory_denied(self) -> None:
        (self.root / ".venv-data" / "bin" / "python").unlink()
        (self.root / ".venv-data" / "bin").rmdir()
        (self.outside / "bin").mkdir()
        self.symlink(self.root / ".venv-data" / "bin", self.outside / "bin")
        self.denied(f"{PY} runs/data-analyst/{ACTIVE}/scripts/analysis.py", contains="symlink")

    def test_env_prefix_and_other_executables_denied(self) -> None:
        for command in (f"PYTHONPATH=x {PY} runs/data-analyst/{ACTIVE}/scripts/analysis.py",
                        f"env {PY} runs/data-analyst/{ACTIVE}/scripts/analysis.py",
                        "cat README.md", "rm -rf runs", "bash -c ls", "/bin/ls", "./ls", "tail README.md",
                        "", "   ", "ls 'unterminated"):
            with self.subTest(command=command):
                self.denied(command)

    def test_ls_and_head_inside_root_allowed(self) -> None:
        self.allowed("ls")
        self.allowed("ls -la runs/data-analyst")
        self.allowed(f"ls {self.root}/vendor")
        self.allowed("head -n 5 README.md")
        self.allowed("head -- README.md")

    def test_ls_outside_root_denied(self) -> None:
        for command in ("ls /etc", "ls ..", "ls ../outside", "head /etc/passwd", "ls -- /etc",
                        "ls README.md /etc", "head -n 5 /etc/passwd", "ls runs/../../outside",
                        "ls -- -x/../../../etc"):
            with self.subTest(command=command):
                self.denied(command)
        self.symlink(self.root / "escape", self.outside)
        self.denied("ls escape")
        self.denied("head escape/evil.py")

    def test_relative_paths_resolve_against_event_cwd(self) -> None:
        self.allowed("ls data-analyst", cwd=self.root / "runs")
        with self.assertRaises(ValueError):
            self.guard.check_bash("ls README.md", self.root, ACTIVE, cwd=self.outside)
        with self.assertRaises(ValueError):
            self.guard.check_bash(f"{PY} runs/data-analyst/{ACTIVE}/scripts/analysis.py",
                                  self.root, ACTIVE, cwd=self.outside)

    def test_only_session_new_before_session(self) -> None:
        self.allowed(NEW, active=None)
        self.allowed(f"{NEW} --derived-from {OTHER}", active=None)
        self.allowed("ls runs", active=None)
        self.allowed("head README.md", active=None)
        for command in (f"{PY} scripts/data/session.py --help",
                        f"{PY} scripts/data/session.py",
                        f"{PY} vendor/scientific-agent-skills/depmap/scripts/depmap_data.py",
                        f"{PY} scripts/data/fetch.py --session {ACTIVE} --release r",
                        f"{PY} scripts/data/manifest.py build --session {ACTIVE}",
                        f"{PY} runs/data-analyst/{ACTIVE}/scripts/analysis.py"):
            with self.subTest(command=command):
                self.denied(command, active=None)

    def test_second_session_denied(self) -> None:
        self.denied(NEW, contains="already")
        self.denied(f"{PY} scripts/data/session.py --help")

    def test_fetch_with_wrong_session_denied(self) -> None:
        fetch = f"{PY} scripts/data/fetch.py"
        for args in (f"--session {OTHER} --release r", f"--session={OTHER} --release r",
                     "--release r", f"--sess {ACTIVE} --release r", f"--s={ACTIVE} --release r",
                     f"--session {ACTIVE} --session {OTHER} --release r",
                     f"--session {ACTIVE} --se {OTHER} --release r", "--session", "--session="):
            with self.subTest(args=args):
                self.denied(f"{fetch} {args}")
        self.denied(f"{PY} scripts/data/manifest.py build --session {OTHER}")
        self.denied(f"{PY} scripts/data/manifest.py verify")


class WriteGuardTests(GuardFixture):
    def write_allowed(self, path: Path | str) -> None:
        try:
            self.guard.check_write(str(path), self.root, ACTIVE)
        except ValueError as error:  # pragma: no cover - failure path
            self.fail(f"{path} unexpectedly denied: {error}")

    def write_denied(self, path: Path | str, active: str | None = ACTIVE, contains: str = "") -> None:
        with self.assertRaises(ValueError, msg=str(path)) as caught:
            self.guard.check_write(str(path), self.root, active)
        self.assertIn(contains, str(caught.exception))

    def test_write_inside_session_allowed(self) -> None:
        self.write_allowed(self.session / "scripts" / "analysis2.py")
        self.write_allowed(self.session / "outputs" / "table.csv")
        self.write_allowed(self.session / "proposals" / "new" / "nested" / "p.md")
        self.write_allowed(self.session / "report.md")

    def test_write_identity_denied(self) -> None:
        for name in ("identity.json", "manifest.json", "integrity.json", "sources.jsonl",
                     "outputs/manifest.json", "Identity.JSON", "raw/SOURCES.JSONL", "identity.json.",
                     "manifest.json "):
            with self.subTest(name=name):
                self.write_denied(self.session / name, contains="protected")

    def test_write_through_symlink_denied(self) -> None:
        self.symlink(self.session / "linked", self.outside)
        self.write_denied(self.session / "linked" / "x.csv", contains="symlink")
        self.symlink(self.session / "outputs" / "file.csv", self.outside / "evil.py")
        self.write_denied(self.session / "outputs" / "file.csv", contains="symlink")
        self.symlink(self.root / "runs" / "data-analyst" / "alias", self.session)
        self.write_denied(self.root / "runs" / "data-analyst" / "alias" / "x.csv")

    def test_write_to_hardlinked_file_denied(self) -> None:
        protected = self.root / "MODEL_SPEC.md"
        protected.write_text("spec\n")
        target = self.session / "outputs" / "alias.md"
        try:
            os.link(protected, target)
        except OSError as error:
            self.skipTest(f"hard links unavailable: {error}")
        self.write_denied(target, contains="hard link")

    def test_symlinked_session_root_denied(self) -> None:
        base = self.root / "runs" / "data-analyst"
        target = self.outside / ACTIVE
        (base / ACTIVE).rename(target)
        self.symlink(base / ACTIVE, target)
        self.write_denied(base / ACTIVE / "outputs" / "x.csv", contains="symlink")

    def test_write_outside_session_denied(self) -> None:
        for path in (self.root / "runs" / "data-analyst" / OTHER / "outputs" / "x.csv",
                     self.root / "runs" / "data-analyst" / "x.csv",
                     self.root / "README.md",
                     self.session,
                     self.session / ".." / OTHER / "outputs" / "x.csv",
                     self.session / "outputs" / ".." / "outputs" / "x.csv",
                     f"runs/data-analyst/{ACTIVE}/outputs/x.csv",
                     self.outside / "x.csv",
                     ""):
            with self.subTest(path=path):
                self.write_denied(path)
        self.write_denied(self.session / "outputs" / "x.csv", active=None)
        self.write_denied(self.session / "outputs" / "x.csv", active="../evil")


class TranscriptBindingTests(GuardFixture):
    def transcript(self, *events: object) -> Path:
        path = self.root / "transcript.jsonl"
        path.write_text("".join(json.dumps(event) + "\n" for event in events))
        return path

    def bind(self, *events: object):
        return self.guard.transcript_data_session(self.transcript(*events), root=self.root)

    def test_transcript_binds_session(self) -> None:
        self.assertEqual(self.bind(tool_use("t1", NEW), tool_result("t1", created() + "\n")),
                         (ACTIVE, DIGEST))
        self.assertEqual(self.bind(tool_use("t1", NEW),
                                   tool_result("t1", [{"type": "text", "text": "noise\n" + created()}])),
                         (ACTIVE, DIGEST))
        self.assertIsNone(self.bind())

    def test_transcript_binding_ignores_prose(self) -> None:
        prose = {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "text", "text": created()}]}}
        user = {"type": "user", "message": {"role": "user", "content": created()}}
        self.assertIsNone(self.bind(prose, user))

    def test_transcript_ignores_errors_other_commands_and_non_final_lines(self) -> None:
        self.assertIsNone(self.bind(tool_use("t1", NEW), tool_result("t1", created(), is_error=True)))
        self.assertIsNone(self.bind(tool_use("t1", NEW), tool_result("t1", created() + "\nmore")))
        script = f"{PY} runs/data-analyst/{ACTIVE}/scripts/analysis.py"
        self.assertIsNone(self.bind(tool_use("t1", script), tool_result("t1", created())))
        self.assertIsNone(self.bind(tool_use("t1", "python3 scripts/data/session.py new --purpose x"),
                                    tool_result("t1", created())))
        self.assertIsNone(self.bind(tool_use("t1", NEW + " ; echo"), tool_result("t1", created())))
        self.assertIsNone(self.bind(tool_use("t1", NEW), tool_result("t2", created())))
        self.assertIsNone(self.bind(tool_result("t1", created()), tool_use("t1", NEW)))
        other_tool = tool_use("t1", NEW)
        other_tool["message"]["content"][0]["name"] = "Write"
        self.assertIsNone(self.bind(other_tool, tool_result("t1", created())))

    def test_transcript_two_sessions_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.bind(tool_use("t1", NEW), tool_result("t1", created()),
                      tool_use("t2", NEW), tool_result("t2", created(OTHER)))

    def test_transcript_duplicate_event_is_one_session(self) -> None:
        events = (tool_use("t1", NEW), tool_result("t1", created()))
        self.assertEqual(self.bind(*events, *events), (ACTIVE, DIGEST))

    def test_transcript_malformed_raises(self) -> None:
        for bad in ("../../etc", "data-x"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.bind(tool_use("t1", NEW), tool_result("t1", created(bad)))
        path = self.root / "transcript.jsonl"
        path.write_text("{not json\n")
        with self.assertRaises(ValueError):
            self.guard.transcript_data_session(path, root=self.root)
        path.write_text("[]\n")
        with self.assertRaises(ValueError):
            self.guard.transcript_data_session(path, root=self.root)


class CliTests(GuardFixture):
    def run_cli(self, mode: str, payload: object, raw: str | None = None) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["CLAUDE_PROJECT_DIR"] = str(self.root)
        return subprocess.run([sys.executable, str(GUARD), mode],
                              input=raw if raw is not None else json.dumps(payload),
                              text=True, capture_output=True, env=environment, check=False)

    def transcript(self, name: str, *events: object) -> str:
        path = self.root / name
        path.write_text("".join(json.dumps(event) + "\n" for event in events))
        return str(path)

    def bash(self, command: str, **extra: object) -> dict:
        return {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(self.root), **extra}

    def write(self, path: Path, **extra: object) -> dict:
        return {"tool_name": "Write", "tool_input": {"file_path": str(path), "content": "x"}, **extra}

    def assert_blocked(self, result, tool: str, message: str = "") -> None:
        self.assertEqual(result.returncode, 2, result)
        self.assertIn(f"Data analyst {tool} blocked: ", result.stderr)
        self.assertIn(message, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_cli_binds_from_agent_transcript_first(self) -> None:
        bound = self.transcript("agent.jsonl", tool_use("t1", NEW), tool_result("t1", created()))
        empty = self.transcript("main.jsonl")
        script = f"{PY} runs/data-analyst/{ACTIVE}/scripts/analysis.py"
        result = self.run_cli("bash", self.bash(script, agent_transcript_path=bound, transcript_path=empty))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_blocked(self.run_cli("bash", self.bash(script, agent_transcript_path=empty,
                                                           transcript_path=bound)), "Bash")
        result = self.run_cli("bash", self.bash(script, transcript_path=bound))
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.run_cli("write", self.write(self.session / "outputs" / "x.csv", transcript_path=bound))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_cli_missing_transcript_means_no_session(self) -> None:
        for extra in ({}, {"transcript_path": str(self.root / "missing.jsonl")}, {"transcript_path": 5}):
            with self.subTest(extra=extra):
                self.assertEqual(self.run_cli("bash", self.bash(NEW, **extra)).returncode, 0)
                self.assertEqual(self.run_cli("bash", self.bash("ls", **extra)).returncode, 0)
                self.assert_blocked(self.run_cli("bash", self.bash(
                    f"{PY} runs/data-analyst/{ACTIVE}/scripts/analysis.py", **extra)), "Bash")
                self.assert_blocked(self.run_cli("write", self.write(
                    self.session / "outputs" / "x.csv", **extra)), "Write", "no active data session")

    def test_cli_ambiguous_binding_denies_everything(self) -> None:
        path = self.transcript("agent.jsonl", tool_use("t1", NEW), tool_result("t1", created()),
                               tool_use("t2", NEW), tool_result("t2", created(OTHER)))
        self.assert_blocked(self.run_cli("bash", self.bash("ls", agent_transcript_path=path)), "Bash")
        broken = self.transcript("broken.jsonl")
        Path(broken).write_text("{oops\n")
        self.assert_blocked(self.run_cli("bash", self.bash("ls", agent_transcript_path=broken)), "Bash")

    def test_cli_denials_and_malformed_input(self) -> None:
        self.assert_blocked(self.run_cli("bash", self.bash("cat README.md")), "Bash", "not allowed")
        self.assert_blocked(self.run_cli("write", self.write(self.root / "README.md")), "Write")
        self.assert_blocked(self.run_cli("bash", None, raw="{not json"), "Bash")
        self.assert_blocked(self.run_cli("bash", ["list"]), "Bash")
        self.assert_blocked(self.run_cli("bash", {"tool_name": "Bash", "tool_input": {}}), "Bash")
        self.assert_blocked(self.run_cli("bash", {"tool_name": "Bash", "tool_input": "ls"}), "Bash")
        self.assert_blocked(self.run_cli("bash", {"tool_name": "Write", "tool_input": {"command": "ls"}}), "Bash")
        self.assert_blocked(self.run_cli("write", {"tool_name": "Write", "tool_input": {"file_path": 3}}), "Write")
        result = self.run_cli("read", self.bash("ls"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("Data analyst", result.stderr)


if __name__ == "__main__":
    unittest.main()
