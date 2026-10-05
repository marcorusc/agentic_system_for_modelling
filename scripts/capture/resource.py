"""Preserve explicitly supplied database resource metadata; never infer versions."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
from scripts.capture.artifact_capture import reject_symlinks

def record_resource(stage: Path, metadata_file: Path | None):
    if metadata_file is None:
        return None
    reject_symlinks(metadata_file)
    original = metadata_file.read_bytes()
    metadata = json.loads(original)
    if not isinstance(metadata, dict): raise ValueError('resource metadata must be an object')
    for key in ('name', 'version'):
        if metadata.get(key) is not None and (not isinstance(metadata[key], str) or not metadata[key].strip()):
            raise ValueError(f'resource {key} must be a nonempty string or null')
    timestamp = metadata.get('cache_timestamp')
    if timestamp is not None:
        if not isinstance(timestamp, str) or datetime.fromisoformat(timestamp.replace('Z', '+00:00')).tzinfo is None:
            raise ValueError('resource cache_timestamp must include timezone')
    result = {key: metadata.get(key) for key in ('name', 'version', 'cache_timestamp')}
    result.update({'source': str(metadata_file.absolute()), 'source_sha256': hashlib.sha256(original).hexdigest()})
    (stage / 'resource.original.json').write_bytes(original)
    (stage / 'resource.json').write_text(json.dumps(result, indent=2) + '\n')
    return result
