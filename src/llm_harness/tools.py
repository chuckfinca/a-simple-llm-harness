from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from typing import Any

from llm_harness.sandbox import run_python

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": (
                "Execute Python code in a sandboxed Docker container. "
                "Returns stdout, stderr, and exit code. "
                "numpy, pandas, and scipy are available."
            ),
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
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": (
                "Evaluate a mathematical expression. Supports basic arithmetic "
                "and math module functions like sqrt, sin, cos, etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": (
                            "The math expression to evaluate, "
                            "e.g. '2 + 2' or 'sqrt(16)'"
                        ),
                    }
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Returns the current UTC time.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
]


def _calculator(expression: str) -> str:
    allowed_names: dict[str, Any] = {
        name: getattr(math, name) for name in dir(math) if not name.startswith("_")
    }
    allowed_names["abs"] = abs
    allowed_names["round"] = round
    try:
        result = eval(expression, {"__builtins__": {}}, allowed_names)  # noqa: S307
    except Exception as exc:
        return json.dumps({"error": str(exc)})
    return json.dumps({"result": result})


def _get_current_time() -> str:
    return json.dumps({"utc": datetime.now(UTC).isoformat()})


def execute_tool(name: str, arguments_json: str) -> str:
    try:
        args: dict[str, Any] = json.loads(arguments_json) if arguments_json else {}
    except json.JSONDecodeError:
        return json.dumps({"error": f"Invalid JSON arguments: {arguments_json}"})

    if name == "run_python":
        return run_python(args.get("code", ""))
    if name == "calculator":
        return _calculator(args.get("expression", ""))
    if name == "get_current_time":
        return _get_current_time()
    return json.dumps({"error": f"Unknown tool: {name}"})
