#!/usr/bin/env python3
"""Filesystem-only publication failure probe against an ODE-specialist snapshot.

Usage: python3 reproduce_capture_failure.py /path/to/ODE-specialist/snapshot
All test input and output files are temporary. No modelling server is invoked.
"""
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from unittest import mock


def main():
    source_tree = Path(sys.argv[1]).resolve(strict=True)
    sys.path.insert(0, str(source_tree))
    import scripts.codex.record_ode_artifacts as recorder

    with tempfile.TemporaryDirectory(prefix="capture-atomicity-probe-") as temporary:
        base = Path(temporary)
        project = base / "project"
        project.mkdir()
        server = base / "server"
        source = server / "artifacts/session"
        source.mkdir(parents=True)
        entries = []
        for name in ("a.txt", "b.txt"):
            file = source / name
            file.write_text(name)
            entries.append({"path": str(file), "session_id": "session",
                            "sha256": hashlib.sha256(file.read_bytes()).hexdigest()})
        rename = recorder.os.rename
        calls = 0

        def interrupted(old, new):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected failure during publication")
            return rename(old, new)

        error = None
        try:
            with mock.patch.object(recorder.os, "rename", side_effect=interrupted):
                recorder.record(project, server, "session", "capture", entries)
        except OSError as problem:
            error = str(problem)
        target = project / "runs/ode-modeler/session/captures/capture"
        partial = sorted(file.name for file in target.iterdir()) if target.exists() else []
        retry_error = None
        try:
            recorder.record(project, server, "session", "capture", entries)
        except ValueError as problem:
            retry_error = str(problem)
        print(json.dumps({
            "scope": "synthetic filesystem-only failure injection; no modelling tool",
            "injected_error": error, "target_exists": target.exists(),
            "partial_files": partial, "retry_error": retry_error,
            "source_files_preserved": all(Path(entry["path"]).exists() for entry in entries),
        }, indent=2))


if __name__ == "__main__":
    main()
