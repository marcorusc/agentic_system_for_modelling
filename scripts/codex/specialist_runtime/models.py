"""Internal invocation contract; scientific handoff status is a separate field."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from scripts.codex.launcher_config import SPECIALISTS, validate_approved_tools, validate_session_id


class ExecutionState(str, Enum):
    QUEUED = "queued"
    PREFLIGHTING = "preflighting"
    RUNNING = "running"
    VALIDATING = "validating"
    RECORDING = "recording"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class SpecialistInvocationRequest:
    specialist: str
    task: str
    record_session_id: str | None = None
    approved_tools: tuple[str, ...] = ()
    allow_web_search: bool = False
    provenance_transport: str = "native-wsl"

    def __post_init__(self) -> None:
        if not isinstance(self.specialist, str) or self.specialist not in SPECIALISTS:
            raise ValueError("unknown specialist")
        if not isinstance(self.task, str) or not self.task.strip() or "\x00" in self.task:
            raise ValueError("task must be nonempty text without NUL")
        if self.record_session_id is not None:
            if not isinstance(self.record_session_id, str):
                raise ValueError("session ID must be text")
            validate_session_id(self.record_session_id)
        if not isinstance(self.approved_tools, (tuple, list)) or any(
            not isinstance(tool, str) for tool in self.approved_tools
        ):
            raise ValueError("approved tools must be a sequence of exact names")
        object.__setattr__(self, "approved_tools", tuple(validate_approved_tools(
            self.specialist, list(self.approved_tools)
        )))
        if not isinstance(self.allow_web_search, bool):
            raise ValueError("allow_web_search must be a boolean")
        if self.allow_web_search and self.specialist != "literature_reviewer":
            raise ValueError("web search is valid only for literature_reviewer")
        if self.provenance_transport not in ("native-wsl", "windows-wsl"):
            raise ValueError("unknown provenance transport")


@dataclass
class SpecialistExecutionResult:
    invocation_id: str
    started_at: str
    execution_state: ExecutionState = ExecutionState.QUEUED
    return_code: int | None = None
    handoff: dict[str, Any] | None = None
    handoff_error: str | None = None
    artifact_dir: Path | None = None
    event_stream: Path | None = None
    finished_at: str | None = None
