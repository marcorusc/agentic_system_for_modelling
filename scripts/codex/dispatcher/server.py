"""Official MCP SDK v2 stdio adapter around the shared task manager."""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager

from mcp.server import Server
from mcp import stdio_server
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool, ToolAnnotations
from pydantic import ValidationError

from scripts.codex.launcher_process import redact_text, sanitize_json_value
from scripts.codex.specialist_runtime.models import SpecialistInvocationRequest
from .manager import TaskManager
from .models import ModelStart, LiteratureStart, TaskQuery, EventQuery, ListQuery

START_ROLES = {
    "start_network_curator": "network_curator",
    "start_literature_reviewer": "literature_reviewer",
    "start_boolean_dynamics_modeler": "boolean_dynamics_modeler",
    "start_multicellular_configurator": "multicellular_configurator",
    "start_ode_modeler": "ode_modeler",
}
INPUTS = {name: LiteratureStart if role == "literature_reviewer" else ModelStart
          for name, role in START_ROLES.items()} | {
    "get_specialist_task": TaskQuery,
    "get_specialist_events": EventQuery,
    "list_specialist_tasks": ListQuery,
    "cancel_specialist_task": TaskQuery,
}
DESCRIPTIONS = {
    **{name: f"Start one bounded, isolated {role} invocation; returns promptly with a task ID."
       for name, role in START_ROLES.items()},
    "get_specialist_task": "Read technical execution state and the validated handoff after success.",
    "get_specialist_events": "Read sanitized operational progress after a sequence number; excludes reasoning.",
    "list_specialist_tasks": "List recent operational task records without raw logs or handoff bodies.",
    "cancel_specialist_task": "Request cancellation of this managed task; preserve partial artifacts and sessions.",
}


def invoke(manager: TaskManager, name: str, arguments: dict) -> dict:
    if name not in INPUTS:
        raise ValueError("unknown dispatcher tool")
    values = INPUTS[name].model_validate(arguments).model_dump()
    if name in START_ROLES:
        return manager.start(SpecialistInvocationRequest(
            specialist=START_ROLES[name], task=values["task"],
            record_session_id=values["record_session_id"],
            approved_tools=tuple(values.get("approved_tools", [])),
            allow_web_search=values.get("allow_web_search", False),
            review_kind=values.get("review_kind")))
    if name == "get_specialist_task":
        return manager.get(**values)
    if name == "get_specialist_events":
        return manager.events(**values)
    if name == "list_specialist_tasks":
        return {"tasks": manager.list(**values)}
    return manager.cancel(**values)


def create_server(manager_factory=TaskManager) -> Server:
    @asynccontextmanager
    async def lifespan(server):
        manager = manager_factory()
        try:
            yield manager
        finally:
            await asyncio.to_thread(manager.close)

    async def list_tools(ctx, params):
        return ListToolsResult(tools=[Tool(
            name=name, description=DESCRIPTIONS[name],
            input_schema=model.model_json_schema(),
            annotations=ToolAnnotations(read_only_hint=name.startswith(("get_", "list_")),
                                        destructive_hint=False,
                                        idempotent_hint=not name.startswith("start_"),
                                        open_world_hint=name.startswith("start_")),
        ) for name, model in INPUTS.items()])

    async def call_tool(ctx, params):
        try:
            payload = await asyncio.to_thread(invoke, ctx.lifespan_context, params.name, params.arguments or {})
            payload = sanitize_json_value(payload)
            return CallToolResult(content=[TextContent(type="text", text=json.dumps(payload))],
                                  structured_content=payload)
        except ValidationError as error:
            # Exclude caller input from diagnostics (may contain private task text).
            message = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}"
                                for e in error.errors(include_input=False))
        except (OSError, ValueError) as error:
            message = redact_text(str(error))
        return CallToolResult(is_error=True, content=[TextContent(type="text", text=message)])

    return Server("specialist_dispatcher", version="1.0.0", lifespan=lifespan,
                  on_list_tools=list_tools, on_call_tool=call_tool)


async def main() -> None:
    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
