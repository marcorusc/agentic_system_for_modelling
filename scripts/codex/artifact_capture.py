"""Atomic capture publication for cooperating POSIX recorder invocations.

A persistent per-target flock serializes the existence check and directory rename.
The lock must never be unlinked: replacing its inode would split concurrent locks.
Only complete staging directories receive the final capture name. Process crashes
can leave hidden staging directories and lock files; they cannot expose a partial
capture. This is not a power-loss durability guarantee or protection against a
noncooperating process mutating the destination tree during publication.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import stat
import tempfile
from typing import Iterator


def reject_symlinks(path: Path) -> None:
    """Reject existing and dangling symlinks in a path or any of its ancestors."""
    if any(component.is_symlink() for component in (path, *path.parents)):
        raise ValueError('artifact path contains a symlink')


def publish_capture(stage: Path, target: Path) -> None:
    """Atomically publish a complete stage without replacing another recorder."""
    lock = target.parent / f'.{target.name}.capture.lock'
    reject_symlinks(lock)
    flags = os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC
    descriptor = os.open(lock, flags, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError('capture lock must be a regular file')
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        reject_symlinks(lock)
        reject_symlinks(target)
        if os.path.lexists(target):
            raise ValueError('capture already exists; use a new capture ID')
        # The stage and target share a parent/filesystem. All writes and hash
        # checks finish before this single namespace operation.
        os.rename(stage, target)
    finally:
        os.close(descriptor)


@contextmanager
def staged_capture(project: Path, target: Path) -> Iterator[Path]:
    """Yield private staging space and publish it only after the caller succeeds."""
    project = project.resolve(strict=True)
    target = target.absolute()
    relative = target.relative_to(project)
    if not relative.parts or '..' in relative.parts:
        raise ValueError('capture target must be inside the project')
    reject_symlinks(target)
    if os.path.lexists(target):
        raise ValueError('capture already exists; use a new capture ID')
    target.parent.mkdir(parents=True, exist_ok=True)
    reject_symlinks(target.parent)
    with tempfile.TemporaryDirectory(
        prefix=f'.{target.name}.staging-', dir=target.parent
    ) as temporary:
        stage = Path(temporary)
        yield stage
        publish_capture(stage, target)
