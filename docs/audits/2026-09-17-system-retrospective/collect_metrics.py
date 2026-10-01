#!/usr/bin/env python3
"""Summarize local operational records without copying prompts or reasoning."""
import collections
import hashlib
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEST = Path(__file__).resolve().parent
SMOKE = {
    "3a980fcde34f44a0a0fb2307c88a5532": "ODE permission-blocked attempt",
    "6d83af6278ea477f8a213ba2505faff0": "ODE two-fixture smoke test",
    "4f426f3937184de89c3b87baf463d558": "Boolean two-fixture smoke test",
}
FIELDS = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens", "reasoning_output_tokens")


def load(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(rows):
    result = {"invocations": len(rows), "with_usage": sum(bool(r["usage_events"]) for r in rows)}
    result["usage_sum"] = {k: sum(r["usage_sum"].get(k, 0) for r in rows) for k in FIELDS}
    result["process_seconds_sum"] = round(sum(r.get("process_elapsed_seconds") or 0 for r in rows), 3)
    result["handoff_status_counts"] = dict(collections.Counter(r["handoff_status"] for r in rows))
    return result


def main():
    rows, seen = [], set()
    for path in sorted(ROOT.glob("runs/**/specialist-invocations/*/provenance.json")):
        p = load(path)
        identity = p.get("invocation_id") or path.parent.name
        if identity in seen:
            raise ValueError(f"Duplicate invocation needs explicit review: {identity}")
        seen.add(identity)
        event_path = path.parent / "events.jsonl"
        uses, types, calls = [], collections.Counter(), collections.Counter()
        result_sizes = []
        parse_errors = 0
        if event_path.exists():
            for line in event_path.read_text().splitlines():
                try:
                    e = json.loads(line)
                except ValueError:
                    parse_errors += 1
                    continue
                types[e.get("type", "unknown")] += 1
                if isinstance(e.get("usage"), dict):
                    uses.append({k: v for k, v in e["usage"].items() if k in FIELDS and isinstance(v, int)})
                item = e.get("item") or {}
                if e.get("type") == "item.started" and isinstance(item, dict) and item.get("type") == "mcp_tool_call":
                    calls[f'{item.get("server", "?")}.{item.get("tool", "?")}'] += 1
                if e.get("type") == "item.completed" and isinstance(item, dict) and item.get("type") == "mcp_tool_call":
                    result_sizes.append({"tool": f'{item.get("server", "?")}.{item.get("tool", "?")}',
                                         "serialized_result_chars": len(json.dumps(item.get("result")))})
        handoff_path = path.parent / "handoff.json"
        h = load(handoff_path) if handoff_path.exists() else {}
        task_id = p.get("dispatcher_task_id")
        task_path = ROOT / ".dispatcher/tasks" / f"{task_id}.json"
        t = load(task_path) if task_id and task_path.exists() else {}
        operational_path = ROOT / ".dispatcher/events" / f"{task_id}.jsonl"
        simulation_calls, active_simulations = [], []
        last_export_finished = None
        if task_id and operational_path.exists():
            for line in operational_path.read_text().splitlines():
                e = json.loads(line)
                tool = e.get("tool_name") or ""
                if tool.endswith(".run_simulation"):
                    if e.get("type") == "mcp_tool_call_started":
                        active_simulations.append(e["timestamp"])
                    elif e.get("type") == "mcp_tool_call_completed" and active_simulations:
                        start = active_simulations.pop(0)
                        duration = (datetime.fromisoformat(e["timestamp"]) - datetime.fromisoformat(start)).total_seconds()
                        simulation_calls.append({"tool": tool, "started_at": start, "finished_at": e["timestamp"], "wall_seconds": duration})
                if tool.endswith(".export_model_bundle") and e.get("type") == "mcp_tool_call_completed":
                    last_export_finished = e["timestamp"]
        rows.append({
            "invocation_id": identity, "dispatcher_task_id": task_id,
            "specialist": p.get("specialist"), "started_at": p.get("started_at"),
            "finished_at": p.get("finished_at"), "process_elapsed_seconds": p.get("process_elapsed_seconds"),
            "process_exit_code": p.get("process_exit_code"), "cancelled": p.get("cancelled"),
            "dispatcher_execution_state": t.get("execution_state"),
            "handoff_status": h.get("status"), "session_id": h.get("session_id"),
            "usage_events": len(uses), "usage_sum": {k: sum(u.get(k, 0) for u in uses) for k in FIELDS},
            "event_types": dict(types), "mcp_calls_started": dict(calls), "parse_errors": parse_errors,
            "serialized_mcp_result_chars": sum(s["serialized_result_chars"] for s in result_sizes),
            "largest_mcp_results": sorted(result_sizes, key=lambda s: s["serialized_result_chars"], reverse=True)[:6],
            "simulation_tool_calls": simulation_calls, "last_model_bundle_export_finished_at": last_export_finished,
            "provenance_path": str(path.relative_to(ROOT)), "provenance_sha256": sha(path),
            "events_sha256": sha(event_path) if event_path.exists() else None,
            "task_bytes": (path.parent / "task.txt").stat().st_size if (path.parent / "task.txt").exists() else None,
            "final_output_bytes": (path.parent / "specialist-output.txt").stat().st_size if (path.parent / "specialist-output.txt").exists() else None,
        })
    tasks = [load(p) for p in sorted((ROOT / ".dispatcher/tasks").glob("*.json"))]
    smoke = [r | {"label": SMOKE[r["dispatcher_task_id"]]} for r in rows if r["dispatcher_task_id"] in SMOKE]
    output = {
        "scope": f"All {len(rows)} invocation provenance records present under runs/ at audit snapshot; includes infrastructure probes, blocked attempts and scientific tasks. Not a scientific success-rate denominator or full account/conversation bill.",
        "method": "Unique invocation_id; sum numeric usage fields from final JSONL usage events; no inference for missing events. Cached input is a subset of input. Reasoning output is reported separately, not added to output. Process durations may overlap and are not end-to-end wall time.",
        "all_recorded_invocations": summarize(rows),
        "by_specialist": {role: summarize([r for r in rows if r["specialist"] == role]) for role in sorted({r["specialist"] for r in rows})},
        "dispatcher_registry": {"tasks": len(tasks), "execution_states": dict(collections.Counter(t["execution_state"] for t in tasks)), "handoff_statuses": dict(collections.Counter(t.get("handoff_status") for t in tasks))},
        "smoke_cohort": summarize(smoke) | {"invocations": smoke},
        "rows": rows,
    }
    (DEST / "metrics.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps({k: output[k] for k in ("all_recorded_invocations", "by_specialist", "dispatcher_registry")}, indent=2))
    print("SMOKE", json.dumps([{k: r[k] for k in ("label", "process_elapsed_seconds", "usage_sum", "handoff_status")} for r in smoke], indent=2))


if __name__ == "__main__":
    main()
