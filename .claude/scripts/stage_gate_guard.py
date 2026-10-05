#!/usr/bin/env python3
"""Claude PreToolUse Agent/Task guard for downstream specialist dispatch."""
import json
import os
from pathlib import Path
import sys

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR", Path(__file__).resolve().parents[2])).resolve()
sys.path.insert(0, str(ROOT))
from scripts.gate import check_task


def main():
    try:
        event = json.load(sys.stdin)
        if not isinstance(event, dict):
            raise ValueError("hook event must be an object")
        if event.get("tool_name") not in {"Agent", "Task"}:
            return 0
        inputs = event.get("tool_input", {})
        if not isinstance(inputs, dict) or not isinstance(inputs.get("subagent_type", ""), str):
            raise ValueError("invalid agent dispatch input")
        role = inputs.get("subagent_type", "").split(":")[-1].replace("-", "_")
        # ODE authoring has its own source/readiness/whole-model approval contract;
        # this hook enforces the two sequential Boolean downstream boundaries.
        if role in {"boolean_dynamics_modeler", "multicellular_configurator"}:
            check_task(ROOT, role, inputs.get("prompt", ""))
        return 0
    except (ValueError, OSError, TypeError, KeyError) as exc:
        print(f"Downstream stage dispatch blocked: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
