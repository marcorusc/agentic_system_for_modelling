"""Researcher-provided sources cited by a mapping.json or seeds.json.

A source is any file the researcher placed under inputs/ (a paper, a table, an
image, raw omics, an archive). It is NEVER parsed here: a source is declared as
{id, path, sha256} and cited as {source, locator}, where the locator is free text
("Fig. 3B", "Table S2, KRAS G12D row"). What makes a source usable is the
researcher's approval of the translation (the mapping or seeds file) that cites it.

Rules: the path is repository-relative, canonical, under inputs/, free of symlinks
and a regular file (a folder is cited through a file in it or an archive of it);
the sha256 is the lowercase hex digest of the file now; ids are safe identifiers
unique among the declared sources; every declared source is cited at least once.
"""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path, PurePosixPath
from typing import Callable

from scripts import state
from scripts.data.common import reject_symlinks

INPUTS = "inputs"
SHA256 = re.compile(r"[0-9a-f]{64}")
SOURCE_KEYS = {"id", "path", "sha256"}
REF_KEYS = {"source", "locator"}


def source_file(root: Path, rel) -> Path:
    """The regular file a source path names; ValueError unless it is a plain file under inputs/."""
    root = Path(root)
    if not isinstance(rel, str) or not rel or "\\" in rel or rel.startswith("/"):
        raise ValueError(f"source path must be a repository-relative path under {INPUTS}/, not {rel!r}")
    pure = PurePosixPath(rel)
    bad = state.unsafe_cell_char(rel)
    if bad is not None:
        raise ValueError(f"source path {rel!r} contains a forbidden character {bad!r} ('|' or a control, line- or "
                         "paragraph-separator character); rename the file")
    if pure.as_posix() != rel or ".." in pure.parts or pure.parts[0] != INPUTS:
        raise ValueError(f"source path must be a canonical repository-relative path under {INPUTS}/, not {rel!r}")
    if len(pure.parts) < 2:
        raise ValueError(f"{rel} is a folder; cite a file in it or an archive of it")
    path = root / rel
    reject_symlinks(path, root)
    try:
        mode = os.lstat(path).st_mode
    except FileNotFoundError:
        raise ValueError(f"missing source file: {rel}") from None
    if stat.S_ISDIR(mode):
        raise ValueError(f"{rel} is a folder; cite a file in it or an archive of it")
    if not stat.S_ISREG(mode):
        raise ValueError(f"{rel} must be a regular file")
    path.resolve().relative_to(root.resolve())
    return path


def entry(root: Path, source_id: str, rel: str) -> dict:
    """A declaration {id, path, sha256} for a draft; the sha256 is computed now."""
    if not isinstance(source_id, str) or not state.ID.fullmatch(source_id):
        raise ValueError(f"source id {source_id!r} must be a safe identifier")
    return {"id": source_id, "path": rel, "sha256": state.digest(source_file(root, rel))}


def check_locator(locator) -> str | None:
    """The problem with a locator, or None."""
    if not isinstance(locator, str) or not locator.strip():
        return "locator must be non-empty text (e.g. 'Fig. 3B', 'Table S2, KRAS G12D row')"
    bad = state.unsafe_cell_char(locator)
    if bad is not None:
        # Locators and paths are quoted in VALIDATION_PLAN.md table cells ("Required evidence").
        return f"locator cannot contain {bad!r} ('|' or a control, line- or paragraph-separator character)"
    return None


def is_ref(value) -> bool:
    return isinstance(value, dict) and set(value) == REF_KEYS


class Sources:
    """Declared sources and their citations; problems go to `error`."""

    def __init__(self, root: Path, error: Callable[[str], None]):
        self.root = Path(root)
        self.error = error
        self.declared: dict[str, dict] = {}
        self.cited: dict[str, int] = {}

    def declare(self, items, label: str) -> None:
        if not isinstance(items, list):
            self.error(f"{label} must be a list of {{id, path, sha256}}")
            return
        for n, item in enumerate(items):
            here = f"{label}[{n}]"
            if not isinstance(item, dict) or set(item) != SOURCE_KEYS:
                self.error(f"{here} must have exactly id, path, sha256")
                continue
            sid = item["id"]
            if not isinstance(sid, str) or not state.ID.fullmatch(sid):
                self.error(f"{here}: source id {sid!r} must be a safe identifier")
                continue
            if sid in self.declared:
                self.error(f"{here}: duplicate source id {sid}")
                continue
            self.declared[sid] = item
            self.cited[sid] = 0
            try:
                path = source_file(self.root, item["path"])
            except (ValueError, OSError) as exc:
                self.error(f"{here}: {exc}")
                continue
            if not isinstance(item["sha256"], str) or not SHA256.fullmatch(item["sha256"]):
                self.error(f"{here}: sha256 must be a lowercase hex sha256")
            elif state.digest(path) != item["sha256"]:
                self.error(f"{here}: {item['path']} does not match its sha256")

    def ref(self, label: str, ref) -> None:
        """Validate one {source, locator} citation and count it."""
        if not is_ref(ref):
            self.error(f"{label}: a source citation must be {{source, locator}}")
            return
        sid = ref["source"]
        if not isinstance(sid, str) or sid not in self.declared:
            self.error(f"{label}: source {sid} is not declared")
        else:
            self.cited[sid] += 1
        problem = check_locator(ref["locator"])
        if problem:
            self.error(f"{label}: {problem}")

    def uncited(self) -> None:
        for sid, count in self.cited.items():
            if not count:
                self.error(f"source {sid} is never cited")
