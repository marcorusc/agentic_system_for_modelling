"""Read installed distribution metadata and bytes without importing backends."""
import hashlib
from importlib import metadata
import json
from pathlib import Path
import sys


def inspect():
    prefix = Path(sys.prefix).resolve()
    result = {}
    for name in ("mcp-biomodelling-servers", "nekomata"):
        dist = metadata.distribution(name)
        if not dist.files:
            raise ValueError(f"Missing installed file inventory: {name}")
        files = {}
        for entry in dist.files:
            if str(entry).endswith(".pyc"):
                continue
            path = Path(dist.locate_file(entry)).absolute()
            relative = path.resolve().relative_to(prefix).as_posix()
            if any(p.is_symlink() for p in (path, *path.parents) if p != prefix and prefix in p.parents):
                raise ValueError(f"Symlink in backend distribution: {name}")
            if relative in files:
                raise ValueError(f"Duplicate installed file: {relative}")
            files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        result[name] = {"version": dist.version, "direct_url": json.loads(dist.read_text("direct_url.json") or "{}"),
                        "files": files}
    return result


if __name__ == "__main__":
    print(json.dumps(inspect(), sort_keys=True))
