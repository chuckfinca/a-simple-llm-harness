from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from llm_harness.sandbox import run_python as _docker_run_python
from llm_harness.types import SandboxFunc

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": "Execute Python code in a sandboxed container.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python source code to execute",
                    }
                },
                "required": ["code"],
            },
        },
    },
]


def execute_tool(
    name: str,
    arguments_json: str,
    *,
    workspace: Path | None = None,
    scratch_dir: Path | None = None,
    sandbox_fn: SandboxFunc | None = None,
) -> str:
    try:
        args: dict[str, Any] = json.loads(arguments_json) if arguments_json else {}
    except json.JSONDecodeError:
        return json.dumps({"error": f"Invalid JSON arguments: {arguments_json}"})

    if name == "run_python":
        fn = sandbox_fn or _docker_run_python
        return fn(args.get("code", ""), workspace=workspace, scratch_dir=scratch_dir)
    return json.dumps({"error": f"Unknown tool: {name}"})
