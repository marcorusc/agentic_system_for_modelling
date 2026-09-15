"""Bounded executable discovery and platform diagnostics."""
from __future__ import annotations

import os
import platform
import re
import signal
import shutil
import subprocess
from pathlib import Path

from scripts.codex.launcher_process import redact_text
from .state import SetupError


def run(argv: list[str], *, cwd: Path | None = None, timeout: int = 30,
        env: dict | None = None) -> subprocess.CompletedProcess:
    try:
        process = subprocess.Popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True,
                                   start_new_session=os.name == "posix")
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            # Stop the entire probe/installer group, including its stdio server.
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
