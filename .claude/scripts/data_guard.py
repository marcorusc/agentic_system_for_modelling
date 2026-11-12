#!/usr/bin/env python3
"""Agent-scoped PreToolUse guard for the data-analyst specialist.

CLI: ``data_guard.py bash|write`` reads the hook event on stdin. A violation
prints ``Data analyst <tool> blocked: <reason>`` to stderr and exits 2; any
unexpected failure also exits 2 (fail closed), because other non-zero exit
codes would let the tool call proceed.

The active data session is bound only from this invocation's transcript: the
last line of an error-free Bash result whose command is itself an allowed
``session.py new`` invocation. Assistant prose never binds a session.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
try:
    from scripts.data.common import RUNS_ROOT, SESSION_RE, project_root, reject_symlinks
except Exception as _import_error:  # pragma: no cover - fail closed as a hook
    if __name__ == "__main__":
        print(f"Data analyst tool blocked: cannot load guard helpers: {_import_error}", file=sys.stderr)
        raise SystemExit(2)
    raise

AGENT_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,128}")
CREATED_RE = re.compile(r"Data session created: (\S+) \(snapshot sha256=([0-9a-f]{64})\)")
# Shell syntax rejected anywhere in the raw command, quoted or not (R2).
FORBIDDEN = frozenset(";|&<>$`\\\n\r")
# Expansion syntax that bash acts on only outside quotes.
UNQUOTED_FORBIDDEN = frozenset("*?[]{}~()#!")
PROTECTED_NAMES = frozenset({"identity.json", "manifest.json", "integrity.json", "sources.jsonl"})
# Recorder-owned invocation records (runs/data-analyst/<id>/invocation/...).
PROTECTED_DIR = "invocation"
INTERPRETER = Path(".venv-data/bin/python")
SESSION_FLAG_SCRIPTS = frozenset({"fetch.py", "manifest.py"})
# R12: the only scripts/data entry points the agent may run.
DATA_SCRIPTS = frozenset({"session.py", "fetch.py", "manifest.py"})
ALLOWED_FORMS = ("only `.venv-data/bin/python -E -s <script> [args]`, `ls` and `head` "
                 "single commands are allowed")


def _check_characters(command: str) -> None:
    if "$(" in command:
        raise ValueError("command substitution `$(` is not allowed")
    quote = None
    for char in command:
        if not (char == "\t" or " " <= char <= "~"):
            raise ValueError(f"character {char!r} is not allowed (printable ASCII only)")
        if char in FORBIDDEN:
            raise ValueError(f"shell metacharacter {char!r} is not allowed")
        if quote is None:
            if char in "'\"":
                quote = char
            elif char in UNQUOTED_FORBIDDEN:
                raise ValueError(f"unquoted shell expansion character {char!r} is not allowed")
        elif char == quote:
            quote = None
    if quote is not None:
        raise ValueError("unbalanced quotes")


def _base(root: Path, cwd: Path | None) -> Path:
    if cwd is None:
        return root
    cwd = Path(cwd)
    if not cwd.is_absolute():
        raise ValueError("hook cwd must be absolute")
    return cwd.resolve()


def _canonical(base: Path, token: str) -> Path:
    """Absolute, lexically normal path; `..` is refused rather than interpreted."""
    path = Path(token)
    path = path if path.is_absolute() else base / path
    if ".." in path.parts:
        raise ValueError(f"'..' is not allowed in {token!r}")
    return path


def _check_read_paths(args: list[str], root: Path, base: Path) -> None:
    options_done = False
    for token in args:
        if not options_done and token == "--":
            options_done = True
            continue
        if not options_done and token.startswith("-"):
            continue
        resolved = (base / token).resolve()
        if not resolved.is_relative_to(root):
            raise ValueError(f"path {token!r} resolves outside the project")


def _check_session_flag(args: list[str], active: str) -> None:
    values = []
    for index, token in enumerate(args):
        if not token.startswith("--") or token == "--":
            continue
        name, equals, value = token.partition("=")
        if "--session".startswith(name) and len(name) > 2:
            if name != "--session":
                raise ValueError("abbreviated --session options are not allowed")
            if not equals:
                if index + 1 >= len(args):
                    raise ValueError("--session requires a value")
                value = args[index + 1]
            values.append(value)
    if len(values) != 1:
        raise ValueError("exactly one --session option is required")
    if values[0] != active:
        raise ValueError(f"--session must be the active data session {active}")


def _script_kind(path: Path, root: Path, active: str | None) -> str:
    parts = path.relative_to(root).parts
    if len(parts) == 3 and parts[:2] == ("scripts", "data"):
        if parts[2] not in DATA_SCRIPTS:
            raise ValueError("only scripts/data/session.py, fetch.py or manifest.py may be run")
        return "data"
    if len(parts) == 5 and parts[:2] == ("vendor", "scientific-agent-skills") and parts[3] == "scripts":
        return "vendor"
    if (len(parts) == 5 and active is not None and parts[:3] == ("runs", "data-analyst", active)
            and parts[3] == "scripts"):
        return "session"
    raise ValueError("script must be runs/data-analyst/<active>/scripts/*.py, "
                     "vendor/scientific-agent-skills/*/scripts/*.py or "
                     "scripts/data/{session,fetch,manifest}.py")


def _classify(command: str, root: Path, active: str | None, cwd: Path | None = None) -> str:
    """Validate a Bash command; return 'read', 'session-new' or 'python'."""
    if not isinstance(command, str):
        raise ValueError("command must be a string")
    if active is not None and (not isinstance(active, str) or SESSION_RE.fullmatch(active) is None):
        raise ValueError("invalid active data session id")
    root = Path(root)
    base = _base(root, cwd)
    _check_characters(command)
    argv = shlex.split(command)
    if not argv:
        raise ValueError("empty command")
    if argv[0] in ("ls", "head"):
        _check_read_paths(argv[1:], root, base)
        return "read"
    if "/" not in argv[0] or _canonical(base, argv[0]) != root / INTERPRETER:
        raise ValueError(f"{argv[0]!r} is not allowed; {ALLOWED_FORMS}")
    interpreter = root / INTERPRETER
    reject_symlinks(interpreter.parent, root)  # bin/python itself is a venv symlink
    if argv[1:3] != ["-E", "-s"] or len(argv) < 4:
        raise ValueError("the data interpreter must be invoked as `.venv-data/bin/python -E -s <script>`")
    token = argv[3]
    if token.startswith("-"):
        raise ValueError(f"interpreter option {token!r} is not allowed; a script path must follow -E -s")
    script = _canonical(base, token)
    reject_symlinks(script, root)
    if script.resolve() != script or not script.is_file():
        raise ValueError(f"script {token!r} must be an existing regular file without symlinks")
    if script.suffix != ".py" or script.name == ".py":
        raise ValueError(f"script {token!r} must be a .py file")
    kind = _script_kind(script, root, active)
    is_session_script = kind == "data" and script.name == "session.py"
    if active is None:
        if is_session_script and argv[4:5] == ["new"]:
            return "session-new"
        raise ValueError("no active data session: only `session.py new`, ls and head are allowed")
    if is_session_script:
        raise ValueError(f"data session {active} already exists in this invocation; "
                         "a second session.py new is not allowed")
    if kind == "data" and script.name in SESSION_FLAG_SCRIPTS:
        _check_session_flag(argv[4:], active)
    return "python"


def check_bash(command: str, root: Path, active: str | None, *, cwd: Path | None = None) -> None:
    """Raise ValueError(reason) unless the command is on the data-analyst allowlist."""
    _classify(command, root, active, cwd)


def check_write(file_path: str, root: Path, active: str | None) -> None:
    """Raise ValueError(reason) unless Write targets the active session directory."""
    if active is None:
        raise ValueError("no active data session; Write is allowed only inside runs/data-analyst/<active>/")
    if not isinstance(active, str) or SESSION_RE.fullmatch(active) is None:
        raise ValueError("invalid active data session id")
    if not isinstance(file_path, str) or not file_path:
        raise ValueError("file_path must be a non-empty string")
    root = Path(root)
    path = Path(file_path)
    if not path.is_absolute():
        raise ValueError("file_path must be absolute")
    if ".." in path.parts:
        raise ValueError("'..' is not allowed in file_path")
    session = root / RUNS_ROOT / active
    try:
        relative = path.relative_to(session)
    except ValueError:
        raise ValueError(f"Write is allowed only inside {RUNS_ROOT / active}/") from None
    if not relative.parts:
        raise ValueError("file_path must name a file inside the session directory")
    if relative.parts[0].casefold().rstrip(". ") == PROTECTED_DIR:
        raise ValueError(f"{PROTECTED_DIR}/ is protected and is written only by the SubagentStop recorder")
    reject_symlinks(path, root)
    if not session.is_dir():
        raise ValueError(f"data session directory {RUNS_ROOT / active} does not exist")
    if path.resolve() != path:
        raise ValueError("file_path must be canonical")
    # Case-folded and stripped of trailing dots/spaces, which some filesystems ignore.
    if path.name.casefold().rstrip(". ") in PROTECTED_NAMES:
        raise ValueError(f"{path.name} is protected and is written only by scripts/data tools")
    if path.exists():
        if not path.is_file():
            raise ValueError("file_path exists and is not a regular file")
        if path.stat().st_nlink > 1:
            raise ValueError("file_path is a hard link to another file")


def _result_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(block["text"] for block in content
                         if isinstance(block, dict) and block.get("type") == "text"
                         and isinstance(block.get("text"), str))
    return ""


def _is_session_new(command: str, root: Path, base: Path) -> bool:
    try:
        return _classify(command, root, None, base) == "session-new"
    except ValueError:
        return False


def transcript_data_session(transcript: Path, *, root: Path | None = None) -> tuple[str, str] | None:
    """Return (session_id, snapshot_digest) created in this transcript, or None.

    Only Bash tool_use blocks whose command is an allowed `session.py new`, and the
    last line of their error-free tool_result, count. Raises ValueError when more
    than one session was created or the transcript is malformed.
    """
    root = Path(root).resolve() if root is not None else project_root().resolve()
    calls: set[str] = set()
    sessions: dict[str, str] = {}
    for line in Path(transcript).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if not isinstance(event, dict):
            raise ValueError("transcript events must be objects")
        message = event.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue  # string content is prose; it never binds a session
        cwd = event.get("cwd")
        base = Path(cwd).resolve() if isinstance(cwd, str) and os.path.isabs(cwd) else root
        for block in content:
            if not isinstance(block, dict):
                raise ValueError("transcript blocks must be objects")
            if block.get("type") == "tool_use" and block.get("name") == "Bash":
                identity, request = block.get("id"), block.get("input")
                if not isinstance(identity, str) or not identity:
                    continue
                command = request.get("command") if isinstance(request, dict) else None
                if isinstance(command, str) and _is_session_new(command, root, base):
                    calls.add(identity)
                else:
                    calls.discard(identity)
            elif (block.get("type") == "tool_result" and block.get("tool_use_id") in calls
                  and block.get("is_error") is not True):
                lines = _result_text(block.get("content")).rstrip().splitlines()
                match = CREATED_RE.fullmatch(lines[-1]) if lines else None
                if match is None:
                    continue
                session, digest = match.groups()
                if SESSION_RE.fullmatch(session) is None:
                    raise ValueError(f"invalid data session id in transcript: {session!r}")
                if sessions.setdefault(session, digest) != digest:
                    raise ValueError(f"conflicting snapshot digests for {session}")
    if len(sessions) > 1:
        raise ValueError(f"more than one data session created in this invocation: {sorted(sessions)}")
    return next(iter(sessions.items()), None)


def _event_transcript(event: dict) -> str | None:
    """agent_transcript_path, else the subagent transcript derived from agent_id, else
    transcript_path. PreToolUse events from a subagent carry the main session's
    transcript_path plus agent_id; the subagent's own transcript is
    ``<transcript_path without .jsonl>/subagents/agent-<agent_id>.jsonl``."""
    if "agent_transcript_path" in event:
        return event["agent_transcript_path"]
    main = event.get("transcript_path")
    if "agent_id" in event:
        agent_id = event["agent_id"]
        if not isinstance(agent_id, str) or AGENT_ID_RE.fullmatch(agent_id) is None:
            return None
        if not isinstance(main, str) or not main.endswith(".jsonl"):
            return None
        return str(Path(main[: -len(".jsonl")]) / "subagents" / f"agent-{agent_id}.jsonl")
    return main


def bound_session(event: dict, root: Path) -> str | None:
    """R10: bind only from this invocation's own transcript (see _event_transcript);
    a missing/unreadable transcript is no session."""
    path = _event_transcript(event)
    if not isinstance(path, str) or not path:
        return None
    try:
        bound = transcript_data_session(Path(path), root=root)
    except OSError:
        return None
    return bound[0] if bound else None


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    tool = {"bash": "Bash", "write": "Write"}.get(argv[0]) if len(argv) == 1 else None
    try:
        if tool is None:
            raise ValueError("usage: data_guard.py bash|write")
        root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or project_root()).resolve(strict=True)
        event = json.load(sys.stdin)
        if not isinstance(event, dict):
            raise ValueError("hook event must be a JSON object")
        if event.get("tool_name") != tool:
            raise ValueError(f"expected a {tool} tool call")
        request = event.get("tool_input")
        if not isinstance(request, dict):
            raise ValueError("tool_input must be a JSON object")
        active = bound_session(event, root)
        if tool == "Bash":
            command = request.get("command")
            if not isinstance(command, str):
                raise ValueError("tool_input.command must be a string")
            cwd = event.get("cwd")
            check_bash(command, root, active, cwd=Path(cwd) if isinstance(cwd, str) and cwd else None)
        else:
            check_write(request.get("file_path"), root, active)
    except Exception as error:  # noqa: BLE001 - every failure must block (exit 2)
        print(f"Data analyst {tool or 'tool'} blocked: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
