#!/usr/bin/env python3
"""Preview or remove disposable Codex task prompts after provenance verification."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_TASK_DIR = Path(".codex-tasks")
LEGACY_TASK_DIR = Path(".codex/tasks")
LEGACY_ROOT_TASK = re.compile(r"^\.codex-task-[A-Za-z0-9][A-Za-z0-9._-]*\.txt$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class RecordedTask:
    prompt_sha256: str
    task_text: str
    location: str


def normalized_task_text(text: str) -> str:
    """Match the normalization used by run_specialist.py when recording tasks."""

    return text.rstrip() + "\n"


def prompt_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _project_relative(project_root: Path, path: Path) -> Path | None:
    try:
        return path.relative_to(project_root)
    except ValueError:
        return None


def is_disposable_task_path(project_root: Path, candidate: Path) -> bool:
    """Recognize only the canonical spool and two documented legacy layouts."""

    project = project_root.resolve(strict=True)
    try:
        lexical = candidate if candidate.is_absolute() else project / candidate
        relative = lexical.relative_to(project)
    except ValueError:
        return False
    if relative.parent == CANONICAL_TASK_DIR and relative.suffix == ".txt":
        return True
    if relative.parent == LEGACY_TASK_DIR and relative.suffix == ".txt":
        return True
    return relative.parent == Path(".") and LEGACY_ROOT_TASK.fullmatch(relative.name) is not None


def discover_task_sources(project_root: Path) -> list[Path]:
    project = project_root.resolve(strict=True)
    candidates = list(project.glob(".codex-task-*.txt"))
    for directory in (project / CANONICAL_TASK_DIR, project / LEGACY_TASK_DIR):
        if directory.is_dir() and not directory.is_symlink():
            candidates.extend(directory.glob("*.txt"))
    return sorted(set(candidates), key=lambda path: path.as_posix())


def _load_record(provenance_text: str, task_text: str, location: str) -> RecordedTask | None:
    try:
        provenance = json.loads(provenance_text)
    except json.JSONDecodeError:
        return None
    if not isinstance(provenance, dict):
        return None
    digest = provenance.get("prompt_sha256")
    if not isinstance(digest, str) or SHA256.fullmatch(digest) is None:
        return None
    return RecordedTask(digest, task_text, location)


def working_tree_records(project_root: Path) -> list[RecordedTask]:
    project = project_root.resolve(strict=True)
    runs = project / "runs"
    if not runs.is_dir() or runs.is_symlink():
        return []
    records: list[RecordedTask] = []
    for provenance_path in runs.rglob("provenance.json"):
        if "specialist-invocations" not in provenance_path.parts:
            continue
        if provenance_path.is_symlink() or not provenance_path.is_file():
            continue
        invocation = provenance_path.parent
        task_path = invocation / "task.txt"
        if task_path.is_symlink() or not task_path.is_file():
            continue
        try:
            invocation.resolve(strict=True).relative_to(runs.resolve(strict=True))
            record = _load_record(
                provenance_path.read_text(encoding="utf-8"),
                task_path.read_text(encoding="utf-8"),
                invocation.relative_to(project).as_posix(),
            )
        except (OSError, UnicodeError, ValueError):
            continue
        if record is not None:
            records.append(record)
    return records


def _git(project_root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *arguments],
        cwd=project_root,
        text=True,
        capture_output=True,
        check=False,
    )


def git_history_records(project_root: Path) -> list[RecordedTask]:
    """Read recorded tasks from reachable commits without changing the worktree."""

    project = project_root.resolve(strict=True)
    history = _git(
        project,
        "log",
        "--all",
        "--format=%H",
        "--",
        ":(glob)runs/**/specialist-invocations/*/provenance.json",
    )
    if history.returncode != 0:
        return []
    commits = list(dict.fromkeys(line for line in history.stdout.splitlines() if line))
    records: list[RecordedTask] = []
    seen: set[tuple[str, str]] = set()
    for commit in commits:
        tree = _git(project, "ls-tree", "-r", "--name-only", commit, "--", "runs")
        if tree.returncode != 0:
            continue
        provenance_paths = [
            path
            for path in tree.stdout.splitlines()
            if path.endswith("/provenance.json")
            and "/specialist-invocations/" in path
        ]
        for provenance_path in provenance_paths:
            invocation = provenance_path.removesuffix("/provenance.json")
            task_path = f"{invocation}/task.txt"
            key = (commit, invocation)
            if key in seen:
                continue
            provenance = _git(project, "show", f"{commit}:{provenance_path}")
            task = _git(project, "show", f"{commit}:{task_path}")
            if provenance.returncode != 0 or task.returncode != 0:
                continue
            record = _load_record(
                provenance.stdout,
                task.stdout,
                f"git:{commit[:12]}:{invocation}",
            )
            if record is not None:
                records.append(record)
                seen.add(key)
    return records


def recorded_tasks(project_root: Path, *, include_git_history: bool = True) -> list[RecordedTask]:
    records = working_tree_records(project_root)
    if include_git_history:
        records.extend(git_history_records(project_root))
    unique: dict[tuple[str, str, str], RecordedTask] = {}
    for record in records:
        unique[(record.prompt_sha256, record.task_text, record.location)] = record
    return list(unique.values())


def verify_source(source: Path, records: Iterable[RecordedTask]) -> tuple[RecordedTask | None, str]:
    if source.is_symlink() or not source.is_file():
        return None, "not a regular non-symlink file"
    try:
        source_text = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        return None, f"could not read UTF-8 task: {error}"
    digest = prompt_digest(source_text)
    normalized = normalized_task_text(source_text)
    digest_matches = [record for record in records if record.prompt_sha256 == digest]
    for record in digest_matches:
        if record.task_text == normalized:
            return record, "verified"
    if digest_matches:
        return None, "provenance hash matched but recorded task content did not"
    return None, "no recorded invocation has this prompt hash"


def _remove_empty_spool(project_root: Path, source_parent: Path) -> None:
    project = project_root.resolve(strict=True)
    allowed = {project / CANONICAL_TASK_DIR, project / LEGACY_TASK_DIR}
    if source_parent in allowed and source_parent.is_dir() and not source_parent.is_symlink():
        try:
            source_parent.rmdir()
        except OSError:
            pass


def cleanup_task_sources(
    project_root: Path,
    *,
    apply: bool,
    include_git_history: bool = True,
    sources: Sequence[Path] | None = None,
) -> dict[str, Any]:
    project = project_root.resolve(strict=True)
    records = recorded_tasks(project, include_git_history=include_git_history)
    candidates = list(sources) if sources is not None else discover_task_sources(project)
    verified: list[dict[str, str]] = []
    deleted: list[str] = []
    unmatched: list[dict[str, str]] = []
    for source in candidates:
        absolute = source if source.is_absolute() else project / source
        relative = _project_relative(project, absolute)
        display = relative.as_posix() if relative is not None else str(source)
        if not is_disposable_task_path(project, absolute):
            unmatched.append({"path": display, "reason": "path is not an approved task spool"})
            continue
        record, reason = verify_source(absolute, records)
        if record is None:
            unmatched.append({"path": display, "reason": reason})
            continue
        verified.append({"path": display, "recorded_at": record.location})
        if apply:
            try:
                absolute.unlink()
            except OSError as error:
                unmatched.append({"path": display, "reason": f"verified but deletion failed: {error}"})
                continue
            deleted.append(display)
            _remove_empty_spool(project, absolute.parent)
    return {
        "schema_version": 1,
        "mode": "apply" if apply else "preview",
        "records_checked": len(records),
        "verified": verified,
        "deleted": deleted,
        "unmatched": unmatched,
    }


def consume_recorded_task(
    *,
    project_root: Path,
    source: Path | None,
    invocation_dir: Path,
) -> dict[str, Any] | None:
    """Delete one recognized source only after its exact invocation was recorded."""

    if source is None:
        return None
    project = project_root.resolve(strict=True)
    absolute = source if source.is_absolute() else project / source
    if not is_disposable_task_path(project, absolute):
        return {"path": str(source), "status": "retained", "reason": "not a disposable task path"}
    provenance = invocation_dir / "provenance.json"
    task = invocation_dir / "task.txt"
    try:
        record = _load_record(
            provenance.read_text(encoding="utf-8"),
            task.read_text(encoding="utf-8"),
            invocation_dir.relative_to(project).as_posix(),
        )
    except (OSError, UnicodeError, ValueError) as error:
        return {"path": str(source), "status": "retained", "reason": f"record verification failed: {error}"}
    if record is None:
        return {"path": str(source), "status": "retained", "reason": "recorded provenance is incomplete"}
    matched, reason = verify_source(absolute, [record])
    if matched is None:
        return {"path": str(source), "status": "retained", "reason": reason}
    try:
        absolute.unlink()
        _remove_empty_spool(project, absolute.parent)
    except OSError as error:
        return {"path": str(source), "status": "retained", "reason": f"deletion failed: {error}"}
    relative = absolute.relative_to(project).as_posix()
    return {"path": relative, "status": "deleted", "recorded_at": record.location}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="delete only task sources verified against recorded invocations",
    )
    parser.add_argument(
        "--no-git-history",
        action="store_true",
        help="check only invocation records in the current working tree",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    report = cleanup_task_sources(
        PROJECT_ROOT,
        apply=arguments.apply,
        include_git_history=not arguments.no_git_history,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
