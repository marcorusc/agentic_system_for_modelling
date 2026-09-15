#!/usr/bin/env python3
"""Copy an explicit BioMASS artifact inventory into an immutable project capture."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.codex.launcher_config import validate_session_id
from scripts.codex.ode_artifacts import SHA, digest, safe_file


def record(project: Path, server_root: Path, session_id: str, capture_id: str, entries: list) -> dict:
    validate_session_id(session_id)
    validate_session_id(capture_id)
    project = project.resolve(strict=True)
    # Source is the explicitly selected installation, never inferred from chat or CWD.
    source = server_root.absolute() / 'artifacts' / session_id
    for component in (source, *source.parents):
        if component.is_symlink():
            raise ValueError('source artifact root contains a symlink')
    if not isinstance(entries, list) or not entries:
        raise ValueError('provide a nonempty array of explicitly returned server artifacts')
    prepared = []
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict) or entry.get('session_id') != session_id:
            raise ValueError('artifact session identity mismatch')
        path = Path(entry['path'])
        if not path.is_absolute():
            raise ValueError('server artifact path must be absolute')
        relative = path.relative_to(source).as_posix()
        file = safe_file(source, relative)
        if relative == 'capture.json':
            raise ValueError('capture.json is reserved for recording provenance')
        if relative in seen:
            raise ValueError('duplicate artifact')
        seen.add(relative)
        expected = entry.get('sha256')
        if not isinstance(expected, str) or not SHA.fullmatch(expected) or digest(file) != expected:
            raise ValueError('server artifact hash mismatch')
        prepared.append((file, relative, expected))
    target = project / 'runs/ode-modeler' / session_id / 'captures' / capture_id
    for parent in (target, *target.parents):
        if parent == project:
            break
        if parent.is_symlink():
            raise ValueError('destination contains a symlink')
    if target.exists():
        raise ValueError('capture already exists; use a new capture ID')
    target.parent.mkdir(parents=True, exist_ok=True)
    # Publish only after every copy is verified; original files remain untouched.
    with tempfile.TemporaryDirectory(prefix='.capture-', dir=target.parent) as temporary:
        stage = Path(temporary)
        output = []
        for source_file, relative, expected in prepared:
            destination = stage / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            with source_file.open('rb') as src, destination.open('xb') as dst:
                import shutil
                shutil.copyfileobj(src, dst)
            if digest(destination) != expected:
                raise ValueError('artifact changed while copying')
            output.append({'path': (target / relative).relative_to(project).as_posix(), 'sha256': expected})
        provenance = {'session_id': session_id, 'capture_id': capture_id,
                      'source_artifacts': entries, 'artifacts': output}
        (stage / 'capture.json').write_text(json.dumps(provenance, indent=2) + '\n')
        # Reserve the target without replacing any concurrent capture.
        target.mkdir(exist_ok=False)
        for child in stage.iterdir():
            os.rename(child, target / child.name)
    return provenance


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--server-root', required=True, type=Path)
    p.add_argument('--session-id', required=True)
    p.add_argument('--capture-id', required=True)
    p.add_argument('--inventory', required=True, type=Path)
    a = p.parse_args()
    try:
        result = record(Path(__file__).resolve().parents[2], a.server_root, a.session_id,
                        a.capture_id, json.loads(a.inventory.read_text()))
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f'ODE artifact recording failed: {error}', file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
