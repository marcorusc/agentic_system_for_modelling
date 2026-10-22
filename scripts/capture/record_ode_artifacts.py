#!/usr/bin/env python3
"""Copy an explicit BioMASS artifact inventory into an immutable project capture."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.capture.artifact_capture import boolean_artifact_root, reject_symlinks, staged_capture
from scripts.codex.launcher_config import validate_session_id
from scripts.codex.ode_artifacts import SHA, digest, safe_file


def record(project: Path, server_root: Path | None, session_id: str, capture_id: str, entries: list, *,
           invocation_provenance: dict | None = None, artifact_root: Path | None = None) -> dict:
    validate_session_id(session_id)
    validate_session_id(capture_id)
    project = project.resolve(strict=True)
    # Source is the explicitly selected storage, never inferred from chat or CWD:
    # a legacy installation's artifacts/, or the per-server root 2.5.0 writes to
    # (MCP_BIOMODELLING_ARTIFACT_ROOT/BioMASS, default ~/.cache/mcp-biomodelling/artifacts/BioMASS).
    source = boolean_artifact_root(server_root, artifact_root) / session_id
    reject_symlinks(source)
    if not isinstance(entries, list) or not entries:
        raise ValueError('provide a nonempty array of explicitly returned server artifacts')
    entries = copy.deepcopy(entries)
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
        if Path(relative).parts[0] == 'capture.json':
            raise ValueError('capture.json is reserved for recording provenance')
        if relative in seen:
            raise ValueError('duplicate artifact')
        seen.add(relative)
        expected = entry.get('sha256')
        if not isinstance(expected, str) or not SHA.fullmatch(expected) or digest(file) != expected:
            raise ValueError('server artifact hash mismatch')
        if 'size_bytes' in entry and (type(entry['size_bytes']) is not int or file.stat().st_size != entry['size_bytes']):
            raise ValueError('server artifact byte count mismatch')
        prepared.append((file, relative, expected))
    target = project / 'runs/ode-modeler' / session_id / 'captures' / capture_id
    with staged_capture(project, target) as stage:
        output = []
        for source_file, relative, expected in prepared:
            # Recheck path safety immediately before reading the source again.
            safe_file(source, relative)
            destination = stage / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            with source_file.open('rb') as src, destination.open('xb') as dst:
                shutil.copyfileobj(src, dst)
            if digest(destination) != expected:
                raise ValueError('artifact changed while copying')
            output.append({'path': (target / relative).relative_to(project).as_posix(), 'sha256': expected})
        provenance = {'session_id': session_id, 'capture_id': capture_id,
                      'source_artifacts': entries, 'artifacts': output}
        if invocation_provenance is not None:
            for reference in invocation_provenance['records']:
                if digest(safe_file(project, reference['path'])) != reference['sha256']:
                    raise ValueError('invocation record changed before capture publication')
            provenance['invocation'] = invocation_provenance
        (stage / 'capture.json').write_text(json.dumps(provenance, indent=2) + '\n', encoding='utf-8')
    from scripts.capture.index import register_capture
    register_capture(project, target)
    return provenance


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    roots = parser.add_mutually_exclusive_group(required=True)
    roots.add_argument('--server-root', type=Path, help='Legacy installation containing artifacts/')
    roots.add_argument('--artifact-root', type=Path, help='Explicit per-server artifact directory containing session directories')
    parser.add_argument('--session-id', required=True)
    parser.add_argument('--capture-id', required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--inventory', type=Path)
    source.add_argument('--invocation', type=Path, help='Recorded successful ODE invocation; verify catalogue ownership before capture')
    arguments = parser.parse_args()
    try:
        project = Path(__file__).resolve().parents[2]
        provenance = None
        if arguments.invocation:
            from scripts.codex.ode_capture_inventory import verified_inventory
            entries, provenance = verified_inventory(project, arguments.invocation, arguments.session_id)
        else:
            entries = json.loads(arguments.inventory.read_text(encoding='utf-8'))
        result = record(project, arguments.server_root, arguments.session_id, arguments.capture_id,
                        entries, invocation_provenance=provenance, artifact_root=arguments.artifact_root)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f'ODE artifact recording failed: {error}', file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
