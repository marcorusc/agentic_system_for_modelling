#!/usr/bin/env python3
"""Main-session PreToolUse Bash guard: data work belongs to the data-analyst.

Registered in .claude/settings.json. The data-analyst subagent (agent_type
``data-analyst``) passes; it is constrained by data_guard.py instead. For any
other caller the command is denied (exit 2) when it

* references ``.venv-data/`` or ``.venv-cellprofiler/`` (any token, including
  ``VAR=path``/``--opt=path``/``a:b`` pieces and glob expansions);
* runs an interpreter (python*, pypy*, ipython*, uv, uvx, a shell, source/eval/exec)
  in a pipeline that also references ``vendor/scientific-agent-skills`` (by path,
  resolved symlink or name), from a cwd inside it, or after ``cd`` into it;
* executes a vendored path directly as a command;
* (R11) runs ``scripts/data/session.py``, ``fetch.py`` or ``manifest.py`` other
  than ``manifest.py verify`` (path, ``-m scripts.data.<tool>``, symlink, cwd,
  ``cd``/variable forms). ``vendor_lock.py verify`` and ``manifest.py verify`` pass.

Only a caller with ``agent_type == "data-analyst"`` and a non-empty ``agent_id``
(R13) is exempt.

Read/maintenance commands on vendored paths (git, cat, ls, grep, head, sed -n,
``python3 -m unittest`` without vendored paths, ``vendor_lock.py verify``) pass.
This is a tripwire against the orchestrator doing data work itself, not a
sandbox: deliberately obfuscated shell (variables, brace expansion) is out of scope.
"""

from __future__ import annotations

import glob
import hashlib
import itertools
import json
import os
import re
import shlex
import sys
from pathlib import Path

VENVS = frozenset({".venv-data", ".venv-cellprofiler"})
VENDOR_NAME = "scientific-agent-skills"
_RUNNERS = (r"(?:python|pypy|ipython)[\w.+-]*|uvx?|pytest|py\.test|coverage|bash|sh|zsh|dash|ksh|fish"
            r"|perl|ruby|node|deno|bun|r|rscript|julia|conda|mamba|micromamba|pixi|pipx|poetry"
            r"|pdm|hatch|rye|nox|tox|jupyter|papermill|eval|exec")
INTERPRETER_RE = re.compile(rf"\A(?:{_RUNNERS})\Z", re.IGNORECASE)
# An interpreter named inside a word (sed `e`, awk system(), bash -c '...', heredoc lines).
EMBEDDED_RE = re.compile(rf"(?:^|[\s;&|(`/\"'!=])(?:{_RUNNERS})(?=$|[\s;&|)`\"'])", re.IGNORECASE)
SOURCING = frozenset({"source", ".", "eval", "exec"})
# Commands that carry a value to later pipelines (variables, cwd).
CARRIERS = frozenset({"cd", "pushd", "export", "declare", "typeset", "local", "readonly", "alias"})
GIT_SHELL_ALIAS_RE = re.compile(r"alias\.[^=]*=\s*!", re.IGNORECASE)
# Commands whose arguments are data, never executed: an interpreter name among
# their arguments (e.g. `grep -n python3 vendor/...`) is not an execution.
NON_EXECUTING = frozenset({
    "grep", "egrep", "fgrep", "rg", "git", "cat", "echo", "printf", "head", "tail", "ls",
    "wc", "diff", "cmp", "less", "more", "file", "stat", "tree", "du", "sort", "uniq", "cut",
    "tr", "jq", "sha256sum", "shasum", "md5sum", "realpath", "readlink", "basename",
    "dirname", "pwd", "which", "type", "test", "[", "true", "false",
})
PUNCTUATION = frozenset("();<>|&")
ASSIGNMENT_RE = re.compile(r"\A[A-Za-z_][A-Za-z0-9_]*=")
CAT_HEREDOC_RE = re.compile(r"\bcat\s+<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
MAX_DEPTH = 4
MAX_GLOB = 2000
MAX_BRACES = 64
MAX_HASHED_BYTES = 8 << 20
DATA_TOOLS = frozenset({"session.py", "fetch.py", "manifest.py", "handoff.py"})
DATA_MODULE_RE = re.compile(r"\Ascripts\.data\.(session|fetch|manifest|handoff)\Z", re.IGNORECASE)
DATA_TEXT_RE = re.compile(r"scripts[./]data[./](?:session|fetch|handoff|manifest(?!\.py\s+verify\b))", re.IGNORECASE)
DELEGATE = ("data work (vendored scientific-agent-skills scripts, .venv-data, .venv-cellprofiler) "
            "is delegated to the data-analyst subagent")


def _strip_cat_heredocs(command: str) -> tuple[str, list[tuple[str, str]]]:
    """Remove `cat <<DELIM` bodies (text, e.g. commit messages); return them for checks."""
    lines, kept, bodies, index = command.split("\n"), [], [], 0
    while index < len(lines):
        line = lines[index]
        kept.append(line)
        index += 1
        for match in CAT_HEREDOC_RE.finditer(line):
            delimiter, body = match.group(2), []
            while index < len(lines) and lines[index].strip() != delimiter:
                body.append(lines[index])
                index += 1
            if index < len(lines):
                kept.append(lines[index])  # keep the delimiter line so the shape is preserved
                index += 1
            bodies.append((line, "\n".join(body)))
    return "\n".join(kept), bodies


def _words(text: str) -> list[str]:
    text = text.replace("\r", "\n").replace("\n", " ; ")
    lexer = shlex.shlex(text, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        return list(lexer)
    except ValueError:  # unbalanced quotes: over-approximate with a quote-blind split
        return [token.replace("'", "").replace('"', "")
                for token in re.findall(r"[^\s;|&()<>]+|[;|&()<>]+", text)]


def _pipelines(tokens: list[str]) -> list[list[list[tuple[str, bool]]]]:
    """Group words into pipelines of simple commands; mark redirection targets."""
    pipelines, pipeline, command, redirect = [], [], [], False
    for token in tokens:
        if token and set(token) <= PUNCTUATION:
            if token in ("|", "|&"):
                if command:
                    pipeline.append(command)
                command = []
            elif ("<" in token or ">" in token) and not set(token) & set(";|()"):
                redirect = True
            else:
                if command:
                    pipeline.append(command)
                if pipeline:
                    pipelines.append(pipeline)
                pipeline, command, redirect = [], [], False
            continue
        command.append((token, redirect))
        redirect = False
    if command:
        pipeline.append(command)
    if pipeline:
        pipelines.append(pipeline)
    return pipelines


def _braces(word: str) -> list[str]:
    """Expand simple (non-nested) `{a,b}` brace alternatives, bounded."""
    variants, done = [word], []
    while variants and len(done) + len(variants) <= MAX_BRACES:
        current = variants.pop()
        match = re.search(r"\{([^{}]*,[^{}]*)\}", current)
        if match is None:
            done.append(current)
            continue
        variants.extend(current[:match.start()] + option + current[match.end():]
                        for option in match.group(1).split(","))
    return done + variants


def _pieces(word: str, cwd: Path) -> list[str]:
    pieces = [piece for variant in _braces(word)
              for piece in [variant, *[part for part in re.split(r"[=:]", variant) if part]]]
    expanded = []
    for piece in pieces:
        if glob.has_magic(piece):
            try:
                expanded.extend(itertools.islice(glob.iglob(piece, root_dir=cwd), MAX_GLOB))
            except (OSError, ValueError):
                pass
    return pieces + expanded


def _within(path: Path, parent: Path) -> bool:
    """Case-insensitive containment (case-insensitive filesystems alias names)."""
    path, parent = str(path).casefold(), str(parent).casefold()
    return path == parent or path.startswith(parent.rstrip("/") + "/")


def _locations(piece: str, cwd: Path) -> list[Path]:
    lexical = Path(os.path.normpath(cwd / piece))
    try:
        return [lexical, (cwd / piece).resolve()]
    except (OSError, ValueError, RuntimeError):
        return [lexical]


class Guard:
    def __init__(self, root: Path, cwd: Path):
        self.root, self.cwd = root, cwd
        self.vendor = root / "vendor" / VENDOR_NAME
        self.venvs = [root / name for name in sorted(VENVS)]
        self.data_dir = root / "scripts" / "data"
        self._vendor_hashes: set[str] | None = None

    def vendor_hashes(self) -> set[str]:
        if self._vendor_hashes is None:
            self._vendor_hashes = {hashlib.sha256(path.read_bytes()).hexdigest()
                                   for path in self.vendor.rglob("*.py")
                                   if path.is_file() and path.stat().st_size > 0}
        return self._vendor_hashes

    def is_vendor_copy(self, word: str) -> bool:
        """A regular .py file whose bytes equal a vendored script (copy or hardlink)."""
        try:
            path = self.cwd / word
            if (path.suffix.lower() != ".py" or not path.is_file()
                    or not 0 < path.stat().st_size <= MAX_HASHED_BYTES):
                return False
            return hashlib.sha256(path.read_bytes()).hexdigest() in self.vendor_hashes()
        except (OSError, ValueError):
            return False

    def is_venv(self, word: str) -> bool:
        for piece in _pieces(word, self.cwd):
            if VENVS & {part.casefold() for part in Path(piece).parts}:
                return True
            if any(_within(location, venv) for location in _locations(piece, self.cwd)
                   for venv in self.venvs):
                return True
        return False

    def data_tool(self, word: str) -> str | None:
        """The scripts/data entry point a word names (path, symlink or -m module)."""
        match = DATA_MODULE_RE.match(word)
        if match:
            return match.group(1).lower() + ".py"
        for piece in _pieces(word, self.cwd):
            for location in _locations(piece, self.cwd):
                for name in DATA_TOOLS:
                    if str(location).casefold() == str(self.data_dir / name).casefold():
                        return name
        return None

    def is_data_dir(self, word: str) -> bool:
        if any("scripts/data" in variant.casefold() for variant in _braces(word)):
            return True
        return any(_within(location, self.data_dir) for piece in _pieces(word, self.cwd)
                   for location in _locations(piece, self.cwd))

    @staticmethod
    def _mutating(tool: str | None, following: list[str]) -> bool:
        """R11: every data tool except `manifest.py verify` creates or changes session state."""
        return tool is not None and not (tool == "manifest.py" and following[:1] == ["verify"])

    def is_vendor(self, word: str) -> bool:
        if any(VENDOR_NAME in variant.casefold() for variant in _braces(word)):
            return True
        return any(_within(location, self.vendor) for piece in _pieces(word, self.cwd)
                   for location in _locations(piece, self.cwd))

    def check(self, command: str, depth: int = 0) -> None:
        text, bodies = _strip_cat_heredocs(command)
        any_interpreter = carried_vendor = carried_data = named_tool = False
        in_vendor = _within(self.cwd, self.vendor)
        for pipeline in _pipelines(_words(text)):
            interpreter = vendor = data_use = False
            for simple in pipeline:
                words = [word for word, target in simple if not target]
                argv = list(itertools.dropwhile(ASSIGNMENT_RE.match, words))
                name = os.path.basename(argv[0]) if argv else ""
                if argv and self.is_vendor(argv[0]):
                    raise ValueError(f"{argv[0]!r} executes a vendored script directly")
                if argv and self._mutating(self.data_tool(argv[0]), argv[1:]):
                    raise ValueError(f"{argv[0]!r} executes a data-session tool directly")
                for index, word in enumerate(words):
                    following = words[index + 1:]
                    if self._mutating(self.data_tool(word), following):
                        data_use = True
                    base = os.path.basename(word).casefold()
                    if base in DATA_TOOLS and self._mutating(base, following):
                        named_tool = True
                    if (not argv or name in CARRIERS) and self.is_data_dir(word):
                        carried_data = True
                if name in SOURCING or (name == "git" and any(GIT_SHELL_ALIAS_RE.search(w) for w in argv)):
                    interpreter = True
                if name not in NON_EXECUTING and any(
                        INTERPRETER_RE.match(os.path.basename(word)) or EMBEDDED_RE.search(word)
                        for word in argv):
                    interpreter = True
                for word, _ in simple:
                    if self.is_venv(word):
                        raise ValueError(f"{word!r} references the data environment")
                    if self.is_vendor(word):
                        vendor = True
                        if not argv or name in CARRIERS:
                            carried_vendor = True
                    if depth < MAX_DEPTH and ("$(" in word or "`" in word):
                        self.check(word.replace("`", " ; "), depth + 1)
            if interpreter and not vendor:
                vendor = any(self.is_vendor_copy(word) for simple in pipeline for word, _ in simple)
            if interpreter and (vendor or in_vendor):
                raise ValueError("an interpreter would run vendored scientific-agent-skills code")
            if interpreter and data_use:
                raise ValueError("the main session may not run scripts/data session.py, fetch.py "
                                 "or manifest.py build (only manifest.py verify)")
            any_interpreter = any_interpreter or interpreter
        if any_interpreter and carried_data and named_tool:
            raise ValueError("an interpreter would run a scripts/data session tool after `cd`/a variable")
        if any_interpreter and carried_vendor:
            raise ValueError("an interpreter would run after `cd`/a variable pointing at "
                             "vendored scientific-agent-skills")
        for line, body in bodies:
            folded = body.casefold()
            if EMBEDDED_RE.search(line) and (VENDOR_NAME in folded or any(venv in folded for venv in VENVS)
                                            or DATA_TEXT_RE.search(body)):
                raise ValueError("a heredoc feeding an interpreter references data work")


def main() -> int:
    try:
        event = json.load(sys.stdin)
        if not isinstance(event, dict):
            raise ValueError("hook event must be a JSON object")
        if event.get("tool_name") not in (None, "Bash"):
            return 0
        agent_id = event.get("agent_id")
        if event.get("agent_type") == "data-analyst" and isinstance(agent_id, str) and agent_id.strip():
            return 0  # R13: a real data-analyst subagent, constrained by its own data_guard.py hooks
        request = event.get("tool_input")
        if not isinstance(request, dict) or not isinstance(request.get("command"), str):
            raise ValueError("tool_input.command must be a string")
        root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2]).resolve()
        cwd = event.get("cwd")
        cwd = Path(cwd).resolve() if isinstance(cwd, str) and os.path.isabs(cwd) else root
        Guard(root, cwd).check(request["command"])
    except Exception as error:  # noqa: BLE001 - every failure must block (exit 2)
        print(f"Orchestrator blocked: {error}; {DELEGATE}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
