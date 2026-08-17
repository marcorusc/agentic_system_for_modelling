#!/usr/bin/env python3
"""Git-backed lifecycle operations for a single biological model repository."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


class LifecycleError(RuntimeError):
    """A user-correctable lifecycle error."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def timestamp_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")


def run_git(
    root: Path,
    *args: str,
    check: bool = True,
    text: bool = True,
    capture_output: bool = True,
) -> subprocess.CompletedProcess[Any]:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        text=text,
        capture_output=capture_output,
    )
    if check and result.returncode != 0:
        stderr = result.stderr.strip() if text and result.stderr else ""
        raise LifecycleError(
            f"git {' '.join(args)} failed" + (f": {stderr}" if stderr else "")
        )
    return result


def repository_root() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=False,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise LifecycleError("Run this command inside the model Git repository.")
    return Path(result.stdout.strip()).resolve()


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise LifecycleError(f"Required lifecycle file is missing: {path}") from error
    except json.JSONDecodeError as error:
        raise LifecycleError(f"Invalid JSON in {path}: {error}") from error


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def validate_relative_path(root: Path, value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise LifecycleError(f"Unsafe lifecycle path in config: {value!r}")
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise LifecycleError(f"Lifecycle path escapes the repository: {value!r}") from error
    return resolved


def load_config(root: Path) -> dict[str, Any]:
    config = load_json(root / ".model" / "config.json")
    if config.get("schema_version") != 1:
        raise LifecycleError("Unsupported .model/config.json schema version.")
    for key in (
        "state_roots",
        "state_directories",
        "preserved_paths",
        "lifecycle_infrastructure",
    ):
        values = config.get(key)
        if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
            raise LifecycleError(f".model/config.json field {key!r} must be a string list.")
        for value in values:
            validate_relative_path(root, value)
    reset_files = config.get("reset_files")
    if not isinstance(reset_files, dict):
        raise LifecycleError(".model/config.json field 'reset_files' must be an object.")
    for destination, template in reset_files.items():
        validate_relative_path(root, destination)
        template_path = validate_relative_path(root, template)
        if not template_path.is_file():
            raise LifecycleError(f"Reset template is missing: {template}")
    return config


def state_roots(config: dict[str, Any]) -> list[str]:
    return list(dict.fromkeys(config["state_roots"]))


def ensure_no_git_operation(root: Path) -> None:
    git_dir_text = run_git(root, "rev-parse", "--git-dir").stdout.strip()
    git_dir = (
        (root / git_dir_text).resolve()
        if not Path(git_dir_text).is_absolute()
        else Path(git_dir_text)
    )
    blockers = [
        git_dir / "MERGE_HEAD",
        git_dir / "CHERRY_PICK_HEAD",
        git_dir / "REVERT_HEAD",
        git_dir / "rebase-apply",
        git_dir / "rebase-merge",
    ]
    if any(path.exists() for path in blockers):
        raise LifecycleError("Finish the active Git merge, rebase, cherry-pick, or revert first.")


def ensure_index_clean(root: Path) -> None:
    result = run_git(root, "diff", "--cached", "--quiet", check=False)
    if result.returncode == 1:
        raise LifecycleError(
            "The Git index already contains staged changes. Commit or unstage them before "
            "running a model lifecycle command; the command will not mix them into its commit."
        )
    if result.returncode not in (0, 1):
        raise LifecycleError("Unable to inspect the Git index.")


def ensure_git_identity(root: Path) -> None:
    result = run_git(root, "var", "GIT_AUTHOR_IDENT", check=False)
    if result.returncode != 0:
        raise LifecycleError(
            "Git author identity is not configured. Set user.name and user.email before "
            "creating model archives."
        )


def ensure_infrastructure_committed(root: Path, config: dict[str, Any]) -> None:
    paths = config["lifecycle_infrastructure"]
    for relative in paths:
        result = run_git(root, "ls-files", "--", relative)
        if not result.stdout.strip():
            raise LifecycleError(
                f"Lifecycle infrastructure is not committed: {relative}. Commit the "
                "lifecycle implementation before creating or replacing model state."
            )
    result = run_git(root, "status", "--porcelain", "--", *paths)
    if result.stdout.strip():
        raise LifecycleError(
            "Lifecycle infrastructure has uncommitted changes. Commit them before running "
            "a mutating model command so every archive remains reproducible."
        )


def ensure_no_ignored_state(root: Path, roots: list[str]) -> None:
    result = run_git(
        root,
        "ls-files",
        "--others",
        "--ignored",
        "--exclude-standard",
        "--",
        *roots,
    )
    ignored = [line for line in result.stdout.splitlines() if line.strip()]
    if ignored:
        preview = "\n  - ".join(ignored[:20])
        extra = f"\n  ... and {len(ignored) - 20} more" if len(ignored) > 20 else ""
        raise LifecycleError(
            "Ignored files exist inside model-state paths and Git cannot recover them after "
            f"a reset:\n  - {preview}{extra}\nMove them to inputs/, unignore them, or "
            "archive them explicitly before continuing."
        )


def ensure_no_state_symlinks(root: Path, roots: list[str]) -> None:
    for relative in roots:
        path = validate_relative_path(root, relative)
        if path.is_symlink():
            raise LifecycleError(f"Model-state root must not be a symlink: {relative}")
        if not path.is_dir():
            continue
        for directory, directory_names, file_names in os.walk(path, followlinks=False):
            directory_path = Path(directory)
            for name in [*directory_names, *file_names]:
                candidate = directory_path / name
                if candidate.is_symlink():
                    shown = candidate.relative_to(root).as_posix()
                    raise LifecycleError(f"Model-state paths must not contain symlinks: {shown}")


def preflight(root: Path, config: dict[str, Any]) -> None:
    ensure_no_git_operation(root)
    ensure_index_clean(root)
    ensure_git_identity(root)
    ensure_infrastructure_committed(root, config)
    roots = state_roots(config)
    ensure_no_ignored_state(root, roots)
    ensure_no_state_symlinks(root, roots)


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower()
    if not slug:
        raise LifecycleError("Archive name must contain at least one letter or number.")
    if len(slug) > 64:
        slug = slug[:64].rstrip("-")
    return slug


def tag_exists(root: Path, tag: str) -> bool:
    result = run_git(
        root,
        "rev-parse",
        "--verify",
        "--quiet",
        f"refs/tags/{tag}",
        check=False,
    )
    return result.returncode == 0


def git_blob_digest(root: Path, object_id: str) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    process = subprocess.Popen(
        ["git", "cat-file", "blob", object_id],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdout is not None
    try:
        for chunk in iter(lambda: process.stdout.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    finally:
        process.stdout.close()
    stderr = process.stderr.read().decode(errors="replace") if process.stderr else ""
    return_code = process.wait()
    if return_code != 0:
        raise LifecycleError(f"Unable to read Git blob {object_id}: {stderr.strip()}")
    return size, digest.hexdigest()


def build_manifest(
    root: Path,
    roots: list[str],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    result = run_git(root, "ls-files", "--stage", "-z", "--", *roots)
    files = []
    for record in result.stdout.split("\0"):
        if not record:
            continue
        metadata_part, relative = record.split("\t", 1)
        mode, object_id, stage = metadata_part.split()
        if stage != "0":
            raise LifecycleError(f"Unmerged model-state path cannot be archived: {relative}")
        if mode == "120000":
            raise LifecycleError(f"Symlinked model-state path cannot be archived: {relative}")
        size, digest = git_blob_digest(root, object_id)
        files.append(
            {
                "path": relative,
                "size": size,
                "sha256": digest,
                "git_blob": object_id,
            }
        )
    return {"schema_version": 1, **metadata, "files": files}


def stage_and_commit(root: Path, paths: list[str], message: str) -> str:
    run_git(root, "add", "-A", "--", *paths)
    staged = run_git(root, "diff", "--cached", "--quiet", check=False)
    if staged.returncode == 0:
        raise LifecycleError("No lifecycle changes were available to commit.")
    if staged.returncode != 1:
        raise LifecycleError("Unable to inspect staged lifecycle changes.")
    run_git(root, "commit", "-m", message)
    return run_git(root, "rev-parse", "HEAD").stdout.strip()


def unstage_paths(root: Path, paths: list[str]) -> None:
    for relative in paths:
        run_git(root, "restore", "--staged", "--", relative, check=False)


def archive_state(
    root: Path,
    config: dict[str, Any],
    *,
    display_name: str,
    kind: str,
    summary: str,
) -> dict[str, Any]:
    preflight(root, config)
    slug = slugify(display_name)
    prefix = "model/archive" if kind == "archive" else "model/recovery"
    tag = f"{prefix}/{slug}"
    if tag_exists(root, tag):
        raise LifecycleError(f"Archive tag already exists: {tag}")

    registry_path = root / ".model" / "archives.json"
    state_path = root / ".model" / "state.json"
    registry_bytes = registry_path.read_bytes()
    state_bytes = state_path.read_bytes()
    registry = load_json(registry_path)
    state = load_json(state_path)
    created_at = utc_now()
    manifest_relative = f".model/manifests/{kind}/{slug}.json"
    manifest_path = root / manifest_relative
    if manifest_path.exists():
        raise LifecycleError(f"Archive manifest already exists: {manifest_relative}")

    entry = {
        "name": display_name,
        "slug": slug,
        "kind": kind,
        "tag": tag,
        "created_at": created_at,
        "attempt_id": state.get("current", {}).get("attempt_id"),
        "summary": summary,
        "manifest": manifest_relative,
    }
    registry.setdefault("archives", []).append(entry)
    state["last_archive" if kind == "archive" else "last_recovery"] = {
        "tag": tag,
        "created_at": created_at,
    }

    commit_paths = [
        *state_roots(config),
        ".model/state.json",
        ".model/archives.json",
        manifest_relative,
    ]
    try:
        write_json(registry_path, registry)
        write_json(state_path, state)
        run_git(root, "add", "-A", "--", *state_roots(config))
        manifest = build_manifest(
            root,
            state_roots(config),
            {
                key: entry[key]
                for key in (
                    "name",
                    "slug",
                    "kind",
                    "tag",
                    "created_at",
                    "attempt_id",
                    "summary",
                )
            },
        )
        write_json(manifest_path, manifest)
        commit = stage_and_commit(root, commit_paths, f"model({kind}): {slug}")
    except Exception:
        unstage_paths(root, commit_paths)
        registry_path.write_bytes(registry_bytes)
        state_path.write_bytes(state_bytes)
        manifest_path.unlink(missing_ok=True)
        raise

    try:
        run_git(root, "tag", "-a", tag, "-m", f"{kind.title()}: {display_name}")
    except Exception as error:
        raise LifecycleError(
            f"Created commit {commit}, but could not create tag {tag}. The commit is intact; "
            f"create the tag manually after resolving the Git error. Details: {error}"
        ) from error

    return {**entry, "commit": commit}


def clear_directory(root: Path, relative: str, *, preserve_gitkeep: bool) -> None:
    directory = validate_relative_path(root, relative)
    if directory.is_symlink():
        raise LifecycleError(f"Refusing to clear symlinked directory: {relative}")
    directory.mkdir(parents=True, exist_ok=True)
    for child in list(directory.iterdir()):
        if preserve_gitkeep and child.name == ".gitkeep" and child.is_file():
            continue
        if child.is_symlink() or child.is_file():
            child.unlink()
        elif child.is_dir():
            shutil.rmtree(child)


def reset_to_templates(root: Path, config: dict[str, Any]) -> None:
    for relative in config["state_directories"]:
        clear_directory(root, relative, preserve_gitkeep=True)
    for destination, template in config["reset_files"].items():
        destination_path = validate_relative_path(root, destination)
        template_path = validate_relative_path(root, template)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(template_path, destination_path)


def ref_has_path(root: Path, ref: str, relative: str) -> bool:
    result = run_git(
        root,
        "cat-file",
        "-e",
        f"{ref}:{Path(relative).as_posix()}",
        check=False,
    )
    return result.returncode == 0


def extract_archive(root: Path, ref: str, roots: list[str]) -> None:
    included = [relative for relative in roots if ref_has_path(root, ref, relative)]
    for relative in roots:
        path = validate_relative_path(root, relative)
        if path.is_symlink():
            raise LifecycleError(f"Refusing to replace symlinked model-state path: {relative}")
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            clear_directory(root, relative, preserve_gitkeep=False)

    if not included:
        return

    git_dir_text = run_git(root, "rev-parse", "--git-dir").stdout.strip()
    git_dir = (
        (root / git_dir_text).resolve()
        if not Path(git_dir_text).is_absolute()
        else Path(git_dir_text)
    )
    descriptor, archive_name = tempfile.mkstemp(
        prefix="model-restore-",
        suffix=".tar",
        dir=git_dir,
    )
    os.close(descriptor)
    archive_path = Path(archive_name)
    try:
        run_git(
            root,
            "archive",
            "--format=tar",
            "-o",
            str(archive_path),
            ref,
            "--",
            *included,
        )
        allowed_roots = [PurePosixPath(relative) for relative in roots]
        with tarfile.open(archive_path, "r") as archive:
            for member in archive.getmembers():
                member_path = PurePosixPath(member.name)
                if member_path.is_absolute() or ".." in member_path.parts:
                    raise LifecycleError(f"Unsafe path in model archive: {member.name}")
                if not any(
                    member_path == allowed or allowed in member_path.parents
                    for allowed in allowed_roots
                ):
                    raise LifecycleError(f"Unexpected path in model archive: {member.name}")
                if member.issym() or member.islnk():
                    raise LifecycleError(
                        f"Symlinks are not supported in model archives: {member.name}"
                    )
                target = validate_relative_path(root, member.name)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    source = archive.extractfile(member)
                    if source is None:
                        raise LifecycleError(f"Unable to read archived file: {member.name}")
                    with source, target.open("wb") as destination:
                        shutil.copyfileobj(source, destination)
    finally:
        archive_path.unlink(missing_ok=True)


def restore_state_from_ref(root: Path, config: dict[str, Any], ref: str) -> None:
    extract_archive(root, ref, state_roots(config))
    for destination, template in config["reset_files"].items():
        destination_path = validate_relative_path(root, destination)
        if not destination_path.exists():
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(validate_relative_path(root, template), destination_path)
    for relative in config["state_directories"]:
        validate_relative_path(root, relative).mkdir(parents=True, exist_ok=True)


def restore_lifecycle_state_file(root: Path, ref: str) -> None:
    result = run_git(root, "show", f"{ref}:.model/state.json", text=False)
    (root / ".model" / "state.json").write_bytes(result.stdout)


def recovery_name(action: str) -> str:
    return f"before-{action}-{timestamp_slug()}"


def commit_transition(root: Path, config: dict[str, Any], message: str) -> str:
    return stage_and_commit(
        root,
        [*state_roots(config), ".model/state.json"],
        message,
    )


def restart_model(root: Path, config: dict[str, Any], *, confirmed: bool) -> None:
    preflight(root, config)
    if not confirmed:
        print("MODEL RESTART PREVIEW")
        print("A recovery archive will be committed and tagged before any files change.")
        print("The following model-state roots will then be reset:")
        for relative in state_roots(config):
            print(f"  - {relative}")
        print("Preserved paths include: " + ", ".join(config["preserved_paths"]))
        print("Run again with --yes only after the user confirms this plan.")
        return

    recovery = archive_state(
        root,
        config,
        display_name=recovery_name("restart"),
        kind="recovery",
        summary="Automatic recovery point created before model restart.",
    )
    state_path = root / ".model" / "state.json"
    try:
        reset_to_templates(root, config)
        state = load_json(state_path)
        state["current"] = {
            "attempt_id": f"attempt-{timestamp_slug()}",
            "started_at": utc_now(),
            "source": "restart",
            "restored_from": None,
        }
        write_json(state_path, state)
        commit = commit_transition(root, config, "model(restart): start from templates")
    except Exception:
        unstage_paths(root, [*state_roots(config), ".model/state.json"])
        restore_state_from_ref(root, config, recovery["tag"])
        restore_lifecycle_state_file(root, recovery["tag"])
        raise

    print(f"Restarted model state at commit {commit[:12]}.")
    print(f"Recovery archive: {recovery['tag']}")
    print("Start a fresh Claude context with /clear before modelling the new attempt.")


def resolve_archive(root: Path, value: str) -> dict[str, Any]:
    registry = load_json(root / ".model" / "archives.json")
    matches = [
        entry
        for entry in registry.get("archives", [])
        if value in {entry.get("name"), entry.get("slug"), entry.get("tag")}
    ]
    if not matches:
        for prefix in ("model/archive", "model/recovery"):
            tag = f"{prefix}/{value}"
            if tag_exists(root, tag):
                return {
                    "name": value,
                    "slug": value,
                    "kind": prefix.rsplit("/", 1)[-1],
                    "tag": tag,
                }
        raise LifecycleError(f"No model archive matches {value!r}. Run /model-list --all.")
    if len(matches) > 1:
        raise LifecycleError(f"Archive name is ambiguous: {value!r}. Use the full tag.")
    entry = matches[0]
    if not tag_exists(root, entry["tag"]):
        raise LifecycleError(f"Archive registry entry has no Git tag: {entry['tag']}")
    return entry


def verify_archive_manifest(
    root: Path,
    config: dict[str, Any],
    entry: dict[str, Any],
) -> None:
    manifest_relative = entry.get("manifest")
    if not isinstance(manifest_relative, str):
        raise LifecycleError(
            f"Archive {entry['tag']} has no registered integrity manifest and cannot be "
            "restored automatically."
        )
    validate_relative_path(root, manifest_relative)
    result = run_git(
        root,
        "show",
        f"{entry['tag']}:{PurePosixPath(manifest_relative)}",
        check=False,
        text=False,
    )
    if result.returncode != 0:
        raise LifecycleError(f"Archive manifest is missing from {entry['tag']}.")
    try:
        manifest = json.loads(result.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise LifecycleError(f"Archive manifest is invalid in {entry['tag']}.") from error
    if manifest.get("schema_version") != 1 or manifest.get("tag") != entry["tag"]:
        raise LifecycleError(f"Archive manifest metadata does not match {entry['tag']}.")

    expected: dict[str, dict[str, Any]] = {}
    for item in manifest.get("files", []):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise LifecycleError(f"Archive manifest contains an invalid file entry: {entry['tag']}.")
        relative = item["path"]
        validate_relative_path(root, relative)
        if relative in expected:
            raise LifecycleError(f"Archive manifest repeats model-state path: {relative}.")
        expected[relative] = item

    tree = run_git(
        root,
        "ls-tree",
        "-r",
        "-z",
        "--full-tree",
        entry["tag"],
        "--",
        *state_roots(config),
    )
    actual: dict[str, tuple[str, str]] = {}
    for record in tree.stdout.split("\0"):
        if not record:
            continue
        metadata_part, relative = record.split("\t", 1)
        mode, object_type, object_id = metadata_part.split()
        if object_type != "blob" or mode == "120000":
            raise LifecycleError(f"Unsupported archived model-state object: {relative}.")
        actual[relative] = (mode, object_id)

    if expected.keys() != actual.keys():
        missing = sorted(actual.keys() - expected.keys())
        extra = sorted(expected.keys() - actual.keys())
        details = []
        if missing:
            details.append("unmanifested: " + ", ".join(missing[:10]))
        if extra:
            details.append("missing from tag: " + ", ".join(extra[:10]))
        raise LifecycleError(
            f"Archive manifest file set does not match {entry['tag']} ({'; '.join(details)})."
        )

    for relative, (_, object_id) in actual.items():
        item = expected[relative]
        size, digest = git_blob_digest(root, object_id)
        if (
            item.get("git_blob") != object_id
            or item.get("size") != size
            or item.get("sha256") != digest
        ):
            raise LifecycleError(f"Archive integrity check failed for {relative}.")


def restore_model(
    root: Path,
    config: dict[str, Any],
    value: str,
    *,
    confirmed: bool,
) -> None:
    preflight(root, config)
    target = resolve_archive(root, value)
    verify_archive_manifest(root, config, target)
    if not confirmed:
        print("MODEL RESTORE PREVIEW")
        print(f"Target: {target['name']} ({target['tag']})")
        print("A recovery archive of the current model will be created first.")
        print(
            "Only model-state roots will be replaced; project infrastructure and inputs "
            "are preserved."
        )
        print("Run again with --yes only after the user confirms this plan.")
        return

    recovery = archive_state(
        root,
        config,
        display_name=recovery_name("restore"),
        kind="recovery",
        summary=f"Automatic recovery point created before restoring {target['tag']}.",
    )
    state_path = root / ".model" / "state.json"
    try:
        restore_state_from_ref(root, config, target["tag"])
        state = load_json(state_path)
        state["current"] = {
            "attempt_id": f"restore-{target['slug']}-{timestamp_slug()}",
            "started_at": utc_now(),
            "source": "archive",
            "restored_from": target["tag"],
        }
        write_json(state_path, state)
        commit = commit_transition(root, config, f"model(restore): {target['slug']}")
    except Exception:
        unstage_paths(root, [*state_roots(config), ".model/state.json"])
        restore_state_from_ref(root, config, recovery["tag"])
        restore_lifecycle_state_file(root, recovery["tag"])
        raise

    print(f"Restored {target['tag']} at commit {commit[:12]}.")
    print(f"Previous current state recovery: {recovery['tag']}")
    print(
        "MCP session IDs are historical references; specialists must reconstruct runtime "
        "state from handoffs."
    )
    print("Start a fresh Claude context with /clear before continuing the restored model.")


def list_models(root: Path, *, include_recovery: bool, as_json: bool) -> None:
    state = load_json(root / ".model" / "state.json")
    registry = load_json(root / ".model" / "archives.json")
    entries = [
        dict(entry)
        for entry in registry.get("archives", [])
        if include_recovery or entry.get("kind") == "archive"
    ]
    for entry in entries:
        result = run_git(
            root,
            "rev-parse",
            "--short",
            f"{entry['tag']}^{{commit}}",
            check=False,
        )
        entry["commit"] = result.stdout.strip() if result.returncode == 0 else None
        entry["available"] = result.returncode == 0
    payload = {"current": state.get("current"), "archives": entries}
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    current = payload["current"] or {}
    print("CURRENT MODEL")
    print(f"  attempt: {current.get('attempt_id', 'unknown')}")
    print(f"  source: {current.get('source', 'unknown')}")
    print(f"  restored from: {current.get('restored_from') or '-'}")
    print("\nARCHIVES" + (" AND RECOVERY POINTS" if include_recovery else ""))
    if not entries:
        print("  (none)")
        return
    for entry in entries:
        marker = "archive" if entry.get("kind") == "archive" else "recovery"
        available = entry.get("commit") or "missing-tag"
        print(f"  {entry.get('name')} [{marker}] {available}")
        print(f"    tag: {entry.get('tag')}")
        if entry.get("summary"):
            print(f"    {entry['summary']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List current and archived model states.")
    list_parser.add_argument("--all", action="store_true", help="Include recovery points.")
    list_parser.add_argument("--json", action="store_true", help="Emit JSON.")

    archive_parser = subparsers.add_parser("archive", help="Create a named model archive.")
    archive_parser.add_argument("name", help="Archive name; quote names containing spaces.")
    archive_parser.add_argument("--summary", default="", help="Short scientific summary.")

    restart_parser = subparsers.add_parser("restart", help="Reset model state to templates.")
    restart_parser.add_argument("--yes", action="store_true", help="Confirm the previewed reset.")

    restore_parser = subparsers.add_parser("restore", help="Restore a named model archive.")
    restore_parser.add_argument("name", help="Archive name, slug, or full tag.")
    restore_parser.add_argument("--yes", action="store_true", help="Confirm the previewed restore.")
    return parser


def main() -> int:
    try:
        arguments = build_parser().parse_args()
        root = repository_root()
        config = load_config(root)
        if arguments.command == "list":
            list_models(root, include_recovery=arguments.all, as_json=arguments.json)
        elif arguments.command == "archive":
            result = archive_state(
                root,
                config,
                display_name=arguments.name,
                kind="archive",
                summary=arguments.summary,
            )
            print(f"Archived model state as {result['tag']} at {result['commit'][:12]}.")
        elif arguments.command == "restart":
            restart_model(root, config, confirmed=arguments.yes)
        elif arguments.command == "restore":
            restore_model(root, config, arguments.name, confirmed=arguments.yes)
        return 0
    except LifecycleError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
