"""Bounded executable discovery and platform diagnostics."""
from __future__ import annotations

import os
import platform
import re
import signal
import shutil
import subprocess
import sys
from pathlib import Path

from scripts.codex.launcher_process import redact_text
from .state import SetupError


def _process_identity(pid: int) -> tuple[int, str] | None:
    """Linux process parent and birth tick; never identify ownership by name."""
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(") ", 1)[1].split()
        return int(fields[1]), fields[19]
    except (OSError, ValueError, IndexError):
        return None


def _owned_descendants(parent: int) -> list[tuple[int, str]]:
    """Snapshot only this subprocess tree, including children in new sessions."""
    found: list[tuple[int, str]] = []
    seen = {parent}
    pending = [parent]
    while pending:
        owner = pending.pop()
        try:
            tasks = list(Path(f"/proc/{owner}/task").iterdir())
        except OSError:
            continue
        for task in tasks:
            try:
                children = [int(value) for value in (task / "children").read_text().split()]
            except (OSError, ValueError):
                continue
            for child in children:
                identity = _process_identity(child)
                if child not in seen and identity is not None and identity[0] == owner:
                    seen.add(child)
                    found.append((child, identity[1]))
                    pending.append(child)
    return found


def _kill_owned_descendants(descendants: list[tuple[int, str]]) -> None:
    for pid, birth_tick in reversed(descendants):
        identity = _process_identity(pid)
        if identity is not None and identity[1] == birth_tick:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def run(argv: list[str], *, cwd: Path | None = None, timeout: int = 30,
        env: dict | None = None) -> subprocess.CompletedProcess:
    try:
        process = subprocess.Popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True,
                                   start_new_session=os.name == "posix")
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            # MCP stdio servers use a new session. Snapshot owned descendants
            # before stopping the parent so they cannot escape by reparenting.
            descendants = _owned_descendants(process.pid) if sys.platform.startswith("linux") else []
            _kill_owned_descendants(descendants)
            # Also stop the original probe/installer group. No name-based or
            # user-wide process matching is permitted here.
            if os.name == "posix":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                process.kill()
            # A transport may start a child in a separate process group that still
            # holds these pipes. Never turn the timeout into an unbounded drain.
            try:
                process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                if process.stdout is not None:
                    process.stdout.close()
                if process.stderr is not None:
                    process.stderr.close()
                process.wait(timeout=2)
            raise
        result = subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise SetupError(f"Could not run {Path(argv[0]).name}: {type(error).__name__}") from error
    if result.returncode:
        detail = redact_text((result.stderr or result.stdout)[-2000:]).strip()
        raise SetupError(f"{Path(argv[0]).name} exited {result.returncode}: {detail}")
    return result


def system_info() -> dict:
    return {"system": platform.system(), "architecture": platform.machine(),
            "wsl": "microsoft" in platform.release().lower(),
            "python": platform.python_version()}


def discover(name: str, override: str | None = None) -> str | None:
    if override:
        raw = str(Path(override).expanduser())
        candidate = Path(shutil.which(raw) or raw).absolute()
        if not candidate.is_file() or not os.access(candidate, os.X_OK):
            raise SetupError(f"Invalid executable for {name}: {candidate}")
        return str(candidate)  # Retain venv and script entry-point paths.
    found = shutil.which(name)
    if found:
        return str(Path(found).absolute())
    for directory in (Path.home()/".local/bin", Path.home()/".npm-global/bin",
                      Path.home()/"miniforge3/bin", Path.home()/"miniconda3/bin"):
        path = directory/name
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    return None


def client_version(name: str, executable: str) -> str:
    result = run([executable, "--version"])
    match = re.search(r"\b(\d+)\.(\d+)\.(\d+)\b", result.stdout + result.stderr)
    if not match:
        raise SetupError(f"Could not determine {name} version")
    version = tuple(map(int, match.groups()))
    if name == "codex" and version < (0, 153, 0):
        raise SetupError("Codex 0.153.0 or newer is required")
    return ".".join(map(str, version))
