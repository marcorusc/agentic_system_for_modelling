"""Atomic file-backed operational records, isolated from scientific state."""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from pathlib import Path

from scripts.codex.launcher_process import sanitize_json_value
from scripts.codex.specialist_runtime.models import ExecutionState
from scripts.codex.specialist_runtime.lifecycle import TERMINAL, validate_transition
from scripts.codex.launcher_provenance import utc_now
from scripts.codex.launcher_config import SPECIALISTS

TASK_ID = re.compile(r"^[a-f0-9]{32}$")


class TaskStore:
    def __init__(self, project_root: Path):
        self.project_root = project_root.resolve(strict=True)
        self.root = self.project_root / ".dispatcher"
        self.lock = threading.RLock()
        self.sequences: dict[str, int] = {}
        self.contained(self.root)
        (self.root / "tasks").mkdir(parents=True, exist_ok=True)
        (self.root / "events").mkdir(exist_ok=True)
        self.contained(self.root / "tasks")
        self.contained(self.root / "events")

    def contained(self, path: Path) -> Path:
        if path.is_symlink():
            raise ValueError("dispatcher paths must not be symlinks")
        resolved = path.resolve()
        if not resolved.is_relative_to(self.project_root):
            raise ValueError("dispatcher path escapes project")
        return resolved

    def path(self, task_id: str, kind: str = "tasks") -> Path:
        if not isinstance(task_id, str) or not TASK_ID.fullmatch(task_id):
            raise ValueError("invalid task ID")
        extension = ".json" if kind == "tasks" else ".jsonl"
        return self.contained(self.root / kind / (task_id + extension))

    def _validate(self, record: dict, task_id: str) -> None:
        if not isinstance(record, dict) or record.get("schema_version") != 1:
            raise ValueError("unsupported or corrupt task schema")
        if record.get("task_id") != task_id or record.get("specialist") not in SPECIALISTS:
            raise ValueError("task identity mismatch")
        ExecutionState(record["execution_state"])
        for field in ("created_at", "invocation_id", "prompt_sha256"):
            if not isinstance(record.get(field), str):
                raise ValueError(f"invalid task field: {field}")
        for field in ("artifact_dir", "event_stream"):
            if record.get(field):
                self.contained(self.project_root / record[field])

    def _write(self, record: dict) -> None:
        task_id = record["task_id"]
        self._validate(record, task_id)
        target = self.path(task_id)
        fd, temporary = tempfile.mkstemp(prefix=".task-", dir=target.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(sanitize_json_value(record), handle, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
            directory_fd = os.open(target.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def create(self, record: dict) -> dict:
        with self.lock:
            if self.path(record["task_id"]).exists():
                raise ValueError("task already exists")
            self._write(record)
            return self.read(record["task_id"])

    def read(self, task_id: str) -> dict:
        with self.lock:
            path = self.path(task_id)
            if not path.is_file():
                raise ValueError("unknown task ID")
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
                self._validate(record, task_id)
            except (OSError, ValueError, KeyError, TypeError) as error:
                raise ValueError("corrupt task record") from error
            return record

    def update(self, task_id: str, **changes) -> dict:
        with self.lock:
            record = self.read(task_id)
            if any(field in changes for field in ("task_id", "schema_version", "specialist", "invocation_id")):
                raise ValueError("immutable task identity")
            if "execution_state" in changes and changes["execution_state"] != record["execution_state"]:
                validate_transition(record["execution_state"], changes["execution_state"])
            record.update(changes)
            self._write(record)
            return record

    def list(self) -> list[dict]:
        records = []
        with self.lock:
            for path in sorted((self.root / "tasks").glob("*.json")):
                try:
                    records.append(self.read(path.stem))
                except ValueError:
                    records.append({"task_id": path.stem if TASK_ID.fullmatch(path.stem) else None,
                                    "execution_state": "failed", "error": "corrupt task record"})
        return records

    def recover(self) -> None:
        for record in self.list():
            if "schema_version" in record and ExecutionState(record["execution_state"]) not in TERMINAL:
                self.update(record["task_id"], execution_state="failed", finished_at=utc_now(),
                            current_activity=None, error="Dispatcher restarted during active execution; automatic resumption is prohibited")
                self.append_event(record["task_id"], {"type": "dispatcher.recovery", "summary": "Interrupted task marked failed; partial artifacts preserved"})

    def append_event(self, task_id: str, event: dict) -> dict:
        with self.lock:
            path = self.path(task_id, "events")
            if task_id not in self.sequences:
                self.sequences[task_id] = self._last_sequence(path)
            sequence = self.sequences[task_id] + 1
            # Caller supplies only operational data; discard all extra event fields.
            allowed = {k: event[k] for k in ("type", "summary", "tool_name", "active_tools", "mcp_enabled") if k in event}
            record = sanitize_json_value(dict(allowed, sequence=sequence, timestamp=utc_now()))
            with path.open("a", encoding="utf-8") as handle:
                os.chmod(path, 0o600)
                handle.write(json.dumps(record) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            self.sequences[task_id] = sequence
            return record

    def _last_sequence(self, path: Path) -> int:
        if not path.exists():
            return 0
        last = 0
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                event = json.loads(line)
                if event["sequence"] != last + 1:
                    raise ValueError("corrupt operational event sequence")
                last += 1
        return last

    def events(self, task_id: str, after_sequence: int = 0, limit: int = 50) -> dict:
        if type(after_sequence) is not int or after_sequence < 0:
            raise ValueError("after_sequence must be a nonnegative integer")
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError("event limit must be between 1 and 200")
        with self.lock:
            record = self.read(task_id)
            path = self.path(task_id, "events")
            events = []
            if path.exists():
                with path.open(encoding="utf-8") as handle:
                    for line in handle:
                        event = json.loads(line)
                        if event["sequence"] > after_sequence:
                            events.append(sanitize_json_value(event))
                            if len(events) == limit:
                                break
            return {"task_id": task_id, "execution_state": record["execution_state"],
                    "events": events, "next_sequence": events[-1]["sequence"] if events else after_sequence}
