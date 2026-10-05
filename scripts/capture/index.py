"""Verified, append-only capture index; unavailable measurements remain null.

Publication precedes indexing. After an index failure the complete capture is
preserved; `--recover-capture` verifies and indexes it without recopying artifacts.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.capture.artifact_capture import reject_symlinks
from scripts.codex.launcher_config import validate_session_id
from scripts.codex.ode_artifacts import safe_file

SPECIALISTS = {'network-curator', 'boolean-dynamics-modeler', 'multicellular-configurator', 'ode-modeler'}

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def utc_now():
    return datetime.now(timezone.utc).isoformat()

@contextmanager
def locked_index(project):
    root = project / 'runs'
    reject_symlinks(root)
    root.mkdir(parents=True, exist_ok=True)
    lock = root / '.index.capture.lock'
    reject_symlinks(lock)
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError('index lock must be a regular file')
        fcntl.flock(fd, fcntl.LOCK_EX)
        index = root / 'index.json'
        reject_symlinks(index)
        data = json.loads(index.read_text()) if index.exists() else {'schema_version': 1, 'runs': []}
        if data.get('schema_version') != 1 or not isinstance(data.get('runs'), list):
            raise ValueError('unsupported or malformed runs index')
        yield data
        data['updated'] = utc_now()
        with tempfile.NamedTemporaryFile(mode='w', dir=root, prefix='.index-', delete=False) as handle:
            temporary = Path(handle.name)
            try:
                json.dump(data, handle, indent=2, allow_nan=False)
                handle.write('\n'); handle.flush(); os.fsync(handle.fileno())
                reject_symlinks(index)
                os.replace(temporary, index)
            finally:
                temporary.unlink(missing_ok=True)
    finally:
        os.close(fd)

def register_capture(project: Path, target: Path, *, usage=None, resource=None):
    project = project.resolve(strict=True)
    reject_symlinks(target)
    relative = target.absolute().relative_to(project)
    parts = relative.parts
    if len(parts) < 5 or parts[0] != 'runs' or parts[1] not in SPECIALISTS or '..' in parts:
        raise ValueError('capture must be inside a specialist/session/category/capture directory')
    validate_session_id(parts[2]); validate_session_id(parts[-1])
    artifacts = []
    for path in sorted(target.rglob('*')):
        reject_symlinks(path)
        if path.is_file():
            safe_file(project, path.relative_to(project).as_posix())
            artifacts.append({'path': path.relative_to(project).as_posix(), 'sha256': digest(path)})
    if not artifacts:
        raise ValueError('cannot index an empty capture')
    if resource is None and (target / 'resource.json').is_file():
        resource = json.loads((target / 'resource.json').read_text())
    if usage is None and (target / 'invocation.json').is_file():
        usage = json.loads((target / 'invocation.json').read_text()).get('usage')
    if usage is None and (target / 'provenance.json').is_file():
        usage = json.loads((target / 'provenance.json').read_text()).get('usage')
    record = {'record_type': 'capture', 'capture_path': relative.as_posix(),
              'specialist': parts[1], 'session_id': parts[2], 'artifacts': artifacts,
              'recorded_at': utc_now(),
              'usage': usage or {'input_tokens': None, 'output_tokens': None,
                                 'tool_calls': None, 'wall_time_seconds': None, 'cost_usd': None,
                                 'source': 'unavailable'},
              'resource': resource or {'name': None, 'version': None, 'cache_timestamp': None,
                                       'source': 'unavailable; backend did not supply resource metadata'}}
    with locked_index(project) as data:
        existing = [r for r in data['runs'] if r.get('capture_path') == relative.as_posix()]
        if existing:
            if len(existing) != 1 or existing[0]['artifacts'] != artifacts:
                raise ValueError('indexed capture changed; refusing to replace provenance')
            return existing[0]
        data['runs'].append(record)
    return record

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--recover-capture', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(register_capture(args.project, args.recover_capture.absolute()), indent=2))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f'Index recovery failed: {error}\n')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
