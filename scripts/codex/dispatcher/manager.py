"""Own bounded workers and cancellation; never select a scientific stage."""
from __future__ import annotations

import fcntl
import hashlib
import threading
import uuid
from pathlib import Path

from scripts.codex.launcher_config import PROJECT_ROOT
from scripts.codex.launcher_process import redact_text
from scripts.codex.launcher_provenance import utc_now
from scripts.codex.specialist_runtime import executor
from scripts.codex.specialist_runtime.lifecycle import TERMINAL
from scripts.codex.specialist_runtime.models import SpecialistInvocationRequest, ExecutionState
from .store import TaskStore


class TaskManager:
    def __init__(self, project_root: Path = PROJECT_ROOT, *, runner=executor.execute, prepare=executor.prepare):
        self.store = TaskStore(project_root)
        self.runner, self.prepare = runner, prepare
        self.lock = threading.RLock()
        self.workers: dict[str, tuple[threading.Thread, threading.Event]] = {}
        self.closed = False
        # Only one manager can own this registry, including across MCP processes.
        lock_path = self.store.contained(self.store.root / "manager.lock")
        self.lease = lock_path.open("a+")
        try:
            fcntl.flock(self.lease.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.lease.close()
            raise ValueError("another dispatcher owns this project") from None
        try:
            self.store.recover()
        except BaseException:
            self.lease.close()
            raise

    def _relative(self, path: Path | None) -> str | None:
        return str(self.store.contained(path).relative_to(self.store.project_root)) if path else None

    def start(self, request: SpecialistInvocationRequest) -> dict:
        if not isinstance(request, SpecialistInvocationRequest):
            raise ValueError("typed invocation request required")
        with self.lock:
            if self.closed:
                raise ValueError("dispatcher is shutting down")
            active = [self.store.read(task_id) for task_id, (thread, _) in self.workers.items() if thread.is_alive()]
            literature = request.specialist == "literature_reviewer"
            matching = sum((r["specialist"] == "literature_reviewer") == literature for r in active)
            if matching >= (2 if literature else 1):
                raise ValueError("dispatcher concurrency limit reached")
            task_id = uuid.uuid4().hex
            prepared = self.prepare(request)
            record = self.store.create({
                "schema_version": 1, "task_id": task_id, "specialist": request.specialist,
                "execution_state": "queued", "created_at": utc_now(), "started_at": None,
                "finished_at": None, "invocation_id": prepared.invocation_id,
                "record_session_id": request.record_session_id,
                "approved_tools": list(request.approved_tools), "allow_web_search": request.allow_web_search,
                "prompt_sha256": hashlib.sha256(request.task.encode("utf-8")).hexdigest(),
                "artifact_dir": self._relative(prepared.artifact_dir), "event_stream": None,
                "current_activity": None, "last_event_sequence": 0, "return_code": None,
                "handoff_status": None, "handoff": None, "error": None,
                "cancellation_requested": False,
            })
            self._event(task_id, {"type": "task_accepted", "summary": "Task accepted"})
            cancellation = threading.Event()
            worker = threading.Thread(target=self._work, args=(task_id, request, prepared, cancellation), daemon=True)
            self.workers[task_id] = (worker, cancellation)
            try:
                worker.start()
            except BaseException:
                self.store.update(task_id, execution_state="failed", error="Failed to start worker", finished_at=utc_now())
                self.workers.pop(task_id)
                raise
            return {k: record[k] for k in ("task_id", "specialist", "execution_state", "created_at")} | {"poll_after_seconds": 2}

    def _event(self, task_id: str, event: dict) -> None:
        with self.lock:
            event = self.store.append_event(task_id, event)
            changes = {"last_event_sequence": event["sequence"]}
            if "active_tools" in event:
                changes["current_activity"] = {"kind": "mcp_tool_call", "names": event["active_tools"]} if event["active_tools"] else None
            self.store.update(task_id, **changes)

    def _work(self, task_id, request, prepared, cancellation):
        def update(result):
            with self.lock:
                current = self.store.read(task_id)
                state = result.execution_state.value
                # Publish a handoff only on fully recorded technical success.
                successful = result.execution_state == ExecutionState.SUCCEEDED
                if current["execution_state"] != state:
                    self._event(task_id, {"type": "dispatcher.lifecycle", "summary": state})
                self.store.update(task_id, execution_state=state,
                    started_at=result.started_at, finished_at=result.finished_at,
                    artifact_dir=self._relative(result.artifact_dir), event_stream=self._relative(result.event_stream),
                    return_code=result.return_code, error=result.handoff_error,
                    handoff=result.handoff if successful else None,
                    handoff_status=result.handoff.get("status") if successful and result.handoff else None)
        try:
            result = self.runner(request, prepared=prepared, state_callback=update,
                                 event_callback=lambda event: self._event(task_id, event),
                                 cancellation_requested=cancellation.is_set, dispatcher_task_id=task_id)
            if result.execution_state not in TERMINAL:
                raise ValueError("runtime returned a nonterminal result")
            update(result)
        except Exception as error:
            with self.lock:
                record = self.store.read(task_id)
                if ExecutionState(record["execution_state"]) not in TERMINAL:
                    self.store.update(task_id, execution_state="failed", finished_at=utc_now(),
                                      error=redact_text(str(error)), handoff=None, handoff_status=None)
        finally:
            with self.lock:
                self.store.update(task_id, current_activity=None)

    def get(self, task_id: str) -> dict:
        return self.store.read(task_id)

    def list(self, limit: int = 50) -> list[dict]:
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError("task limit must be between 1 and 200")
        records = sorted(self.store.list(), key=lambda row: row.get("created_at", ""), reverse=True)
        return [{k: v for k, v in row.items() if k != "handoff"} for row in records[:limit]]

    def events(self, task_id: str, after_sequence: int = 0, limit: int = 50) -> dict:
        return self.store.events(task_id, after_sequence, limit)

    def cancel(self, task_id: str) -> dict:
        with self.lock:
            record = self.get(task_id)
            if ExecutionState(record["execution_state"]) in TERMINAL:
                return record
            if task_id not in self.workers:
                raise ValueError("task has no managed worker")
            self.workers[task_id][1].set()
            self.store.update(task_id, cancellation_requested=True)
            self._event(task_id, {"type": "cancellation_requested", "summary": "Cancellation requested"})
            return self.get(task_id)

    def close(self) -> None:
        with self.lock:
            self.closed = True
            workers = list(self.workers.values())
            for _, signal in workers:
                signal.set()
        for thread, _ in workers:
            thread.join(timeout=10)
        if any(thread.is_alive() for thread, _ in workers):
            raise RuntimeError("dispatcher still owns active workers; lease retained")
        self.lease.close()
