"""Read-only artifact validation primitives; all paths are project-relative."""
from __future__ import annotations
import csv
import hashlib
import json
import math
from pathlib import Path


def artifact(root: Path, value: str) -> tuple[Path, dict]:
    path = Path(value)
    if path.is_absolute() or '..' in path.parts or not value:
        raise ValueError('input path must be project-relative without traversal')
    resolved = (root / path).resolve(strict=True)
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError('input escapes project')
    if not resolved.is_file():
        raise ValueError('input must be a regular file')
    return resolved, {'path': path.as_posix(), 'sha256': hashlib.sha256(resolved.read_bytes()).hexdigest()}


def load_json_yaml(path: Path) -> dict:
    """Read the documented JSON-compatible YAML subset without external packages."""
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ValueError(f'duplicate configuration key: {key}')
            out[key] = value
        return out
    result = json.loads(path.read_text(), object_pairs_hook=unique,
                        parse_constant=lambda x: (_ for _ in ()).throw(ValueError(f'non-finite value: {x}')))
    if not isinstance(result, dict):
        raise ValueError('configuration must be an object')
    return result


def load_series(path: Path):
    with path.open(newline='') as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames
        if not fields or 'Time' not in fields or len(set(fields)) != len(fields):
            raise ValueError('CSV requires unique columns including Time')
        rows = list(reader)
    if not rows:
        raise ValueError('CSV is empty')
    if any(set(row) != set(fields) or any(v is None for v in row.values()) for row in rows):
        raise ValueError('CSV rows must match the header')
    series = {key: [float(row[key]) for row in rows] for key in fields}
    if any(not math.isfinite(x) for values in series.values() for x in values):
        raise ValueError('CSV values must be finite')
    times = series.pop('Time')
    if times[0] < 0 or any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError('Time must be nonnegative and strictly increasing')
    if any(not 0 <= x <= 1 for values in series.values() for x in values):
        raise ValueError('node values must lie in [0,1]')
    return times, series


def number(value, label, *, positive=False):
    if type(value) not in (int, float) or not math.isfinite(value) or (positive and value <= 0):
        raise ValueError(f'{label} must be a finite' + (' positive' if positive else '') + ' number')
    return value
