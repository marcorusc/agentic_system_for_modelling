#!/usr/bin/env python3
"""Start the stdio server using explicit, ignored workstation settings."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def launch_configuration(root: Path = ROOT) -> tuple[str, dict[str, str]]:
    environment = os.environ.copy()
    installer = root / '.setup/local.json'
    settings = json.loads(installer.read_text()) if installer.exists() else {}
    if not isinstance(settings, dict):
        raise ValueError('invalid installer settings')
    local = root / '.setup/dispatcher.local.json'
    overrides = json.loads(local.read_text()) if local.exists() else {}
    if not isinstance(overrides, dict) or set(overrides) - {'python_executable', 'codex_home'}:
        raise ValueError('invalid local dispatcher settings')
    prefix = settings.get('env_prefix')
    python = overrides.get('python_executable', str(Path(prefix)/'bin/python') if prefix else sys.executable)
    if not isinstance(python, str) or not Path(python).is_absolute() or not Path(python).is_file():
        raise ValueError('configure a valid absolute python_executable in .setup/dispatcher.local.json')
    codex_home = overrides.get('codex_home', settings.get('codex_home'))
    if codex_home is not None:
        if not isinstance(codex_home, str) or not Path(codex_home).is_absolute() or not Path(codex_home).is_dir():
            raise ValueError('configured dispatcher codex_home must be an existing absolute directory')
        environment['CODEX_HOME'] = codex_home
    return python, environment


def main() -> None:
    python, environment = launch_configuration()
    os.chdir(ROOT)
    os.execve(python, [python, '-m', 'scripts.codex.dispatcher.server'], environment)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError) as error:
        print(f'Dispatcher startup failed: {error}', file=sys.stderr)
        raise SystemExit(2)
