#!/usr/bin/env python3
"""Confirm a backend manifest is the exact original behind a project capture.

Backend 2.5.0 binds curation_file history companions to original absolute
paths, so a downstream specialist imports the original server manifest rather
than the relocated capture. Run this before dispatching that import: it checks
the manifest bytes against the capture's original.handoff.json and the hash and
path recorded in relocation.json, and that every payload file the manifest
references still has its recorded size and SHA-256. Read-only; it never
imports a model, calls a server or grants approval.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

PAYLOAD_KEYS = ("bnet_file", "network_file", "curation_file", "bnd_file", "cfg_file", "parent_manifest")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(project: Path, capture: Path, manifest: Path) -> dict:
    project = project.resolve(strict=True)
    capture = capture.resolve(strict=True)
    if capture.parts[:len(project.parts) + 1] != (*project.parts, "runs") or not capture.is_dir():
        raise ValueError("capture must be a directory under the project's runs/")
    relocation = json.loads((capture / "relocation.json").read_text())
    captured = (capture / "original.handoff.json").read_bytes()
    if not isinstance(relocation, dict):
        raise ValueError("relocation.json must be an object")
    manifest = manifest.absolute()
    raw = manifest.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if raw != captured or digest != relocation.get("original_manifest_sha256"):
        raise ValueError("manifest bytes differ from the captured original")
    recorded = relocation.get("source_manifest_path", relocation.get("source_manifest"))
    if not isinstance(recorded, str) or Path(recorded) != manifest:
        raise ValueError(f"manifest is not the recorded source manifest {recorded}")
    data = json.loads(raw)
    checked = []
    for key in PAYLOAD_KEYS:
        ref = data.get(key)
        if ref is None:
            continue
        if not isinstance(ref, dict) or not isinstance(ref.get("path"), str):
            raise ValueError(f"{key} reference has no path")
        path = Path(ref["path"])
        if not path.is_file():
            raise ValueError(f"{key} payload is missing: {path}")
        if path.stat().st_size != ref.get("size_bytes") or _sha256(path) != ref.get("sha256"):
            raise ValueError(f"{key} payload changed since export: {path}")
        checked.append(key)
    return {"passed": True, "manifest": str(manifest), "sha256": digest,
            "capture": capture.relative_to(project).as_posix(), "payloads_checked": checked}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--capture", type=Path, required=True, help="Capture directory containing relocation.json")
    parser.add_argument("--manifest", type=Path, required=True, help="Original backend manifest to be imported")
    args = parser.parse_args(argv)
    try:
        result = verify(args.project, args.capture, args.manifest)
    except (OSError, ValueError, TypeError) as error:
        result = {"passed": False, "errors": [str(error)]}
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    raise SystemExit(main())
