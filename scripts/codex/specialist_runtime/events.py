"""Project raw Codex events into operational observations, without reasoning."""
from scripts.codex.launcher_process import sanitize_json_value, _mcp_tool_name


def operational_event(event: dict, active_tools: dict[str, str]) -> dict | None:
    kind = event.get("type")
    item = event.get("item") or {}
    if not isinstance(item, dict):
        item = {}
    item_type = item.get("type")
    outcome = {"item.started": "started", "item.completed": "completed", "item.failed": "failed"}.get(kind)
    if outcome and item_type in ("mcp_tool_call", "command_execution", "web_search"):
        if item.get("error") or item.get("status") in ("failed", "error"):
            outcome = "failed"
        name = _mcp_tool_name(item) if item_type == "mcp_tool_call" else None
        label = {"mcp_tool_call": "MCP tool call", "command_execution": "Command execution", "web_search": "Web search"}[item_type]
        result = {"type": f"{item_type}_{outcome}", "summary": f"{label} {outcome}" + (f": {name}" if name else ""), "tool_name": name}
    elif kind in ("thread.started", "turn.started", "turn.completed", "turn.failed", "error"):
        result = {"type": kind, "summary": kind.replace(".", " ")}
    else:
        return None
    result["active_tools"] = list(active_tools.values())
    return sanitize_json_value(result)
