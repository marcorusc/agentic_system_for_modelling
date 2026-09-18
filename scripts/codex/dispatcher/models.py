"""Strict public MCP inputs. Callers cannot choose commands, profiles or paths."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ModelStart(StrictInput):
    task: str = Field(min_length=1, max_length=64000)
    record_session_id: str | None = None
    approved_tools: list[str] = Field(default_factory=list)


class LiteratureStart(StrictInput):
    task: str = Field(min_length=1, max_length=64000)
    record_session_id: str | None = None
    allow_web_search: bool = False
    review_kind: Literal["edge", "ode"] = "edge"

    @model_validator(mode="after")
    def require_ode_session(self) -> "LiteratureStart":
        if self.review_kind == "ode" and self.record_session_id is None:
            raise ValueError("ODE literature review requires record_session_id")
        return self


class TaskQuery(StrictInput):
    task_id: str = Field(pattern=r"^[a-f0-9]{32}$")


class EventQuery(TaskQuery):
    after_sequence: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=200)


class ListQuery(StrictInput):
    limit: int = Field(default=50, ge=1, le=200)
