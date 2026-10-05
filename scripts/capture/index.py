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
import math
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

USAGE_COUNTS = {'input_tokens', 'output_tokens', 'cached_input_tokens',
                'cache_creation_input_tokens', 'cache_read_input_tokens', 'tool_calls'}
USAGE_NUMBERS = {'wall_time_seconds', 'cost_usd'}
CATEGORIES = {'captures', 'configs', 'boolean-handoffs', 'ode-handoffs',
              'physicell-handoffs', 'invocation', 'specialist-invocations'}

def validate_usage(usage):
    if not isinstance(usage, dict) or set(usage) - USAGE_COUNTS - USAGE_NUMBERS - {'source'}:
        raise ValueError('usage must contain only supported measurement fields')
    for key, value in usage.items():
        if key == 'source':
            if not isinstance(value, str): raise ValueError('usage source must be text')
        elif value is not None:
            if key in USAGE_COUNTS and (type(value) is not int or value < 0):
                raise ValueError(f'usage {key} must be a nonnegative integer or null')
            if key in USAGE_NUMBERS and (type(value) not in {float, int} or not math.isfinite(value) or value < 0):
                raise ValueError(f'usage {key} must be finite and nonnegative or null')
    return usage

def validate_resource(resource):
    if not isinstance(resource, dict):
        raise ValueError('resource metadata must be an object')
    for key in ('name', 'version', 'source', 'source_sha256'):
        if resource.get(key) is not None and not isinstance(resource[key], str):
            raise ValueError(f'resource {key} must be text or null')
    timestamp = resource.get('cache_timestamp')
    if timestamp is not None:
        if not isinstance(timestamp, str) or datetime.fromisoformat(timestamp.replace('Z', '+00:00')).tzinfo is None:
            raise ValueError('resource cache_timestamp must include timezone')
    return resource

def capture_identity(target, parts):
    """Cross-check explicit recorded identity; the path alone cannot relabel it."""
    specialist = parts[1]
    declared_roles = set()
    for filename in ('invocation.json', 'provenance.json', 'handoff.json', 'capture.json'):
        path = target / filename
        reject_symlinks(path)
        if not path.is_file(): continue
        data = json.loads(path.read_text())
        if not isinstance(data, dict): raise ValueError(f'{filename} must be an object')
        if data.get('session_id') is not None and data['session_id'] != parts[2]:
            raise ValueError(f'{filename} session identity disagrees with capture path')
        role = data.get('specialist')
        if role is not None:
            if not isinstance(role, str): raise ValueError('recorded specialist must be text')
            role = role.replace('_', '-')
            allowed = {parts[1]}
            if parts[3] == 'specialist-invocations' and parts[1] in {'network-curator', 'ode-modeler'}:
                allowed.add('literature-reviewer')
            if role not in allowed:
                raise ValueError('recorded specialist disagrees with capture directory')
            if specialist != parts[1] and specialist != role:
                raise ValueError('conflicting recorded specialist identities')
            declared_roles.add(role)
            if len(declared_roles) > 1:
                raise ValueError('conflicting recorded specialist identities')
            specialist = role
        if data.get('invocation_id') is not None and data['invocation_id'] != parts[4]:
            raise ValueError('recorded invocation ID disagrees with capture directory')
    return specialist

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
        if not isinstance(data, dict) or data.get('schema_version') != 1 or not isinstance(data.get('runs'), list) or any(not isinstance(row, dict) for row in data['runs']):
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
    if len(parts) != 5 or parts[0] != 'runs' or parts[1] not in SPECIALISTS or parts[3] not in CATEGORIES or '..' in parts:
        raise ValueError('capture must be inside a specialist/session/category/capture directory')
    validate_session_id(parts[2]); validate_session_id(parts[-1])
    specialist = capture_identity(target, parts)
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
              'specialist': specialist, 'session_id': parts[2], 'artifacts': artifacts,
              'recorded_at': utc_now(),
              'usage': usage or {'input_tokens': None, 'output_tokens': None,
                                 'tool_calls': None, 'wall_time_seconds': None, 'cost_usd': None,
                                 'source': 'unavailable'},
              'resource': resource or {'name': None, 'version': None, 'cache_timestamp': None,
                                       'source': 'unavailable; backend did not supply resource metadata'}}
    validate_usage(record['usage'])
    validate_resource(record['resource'])
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
