from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from llm_harness.sandbox import run_file_tool, run_python

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
            "name": "list_files",
            "description": (
                "List files in the workspace directory. Returns file paths "
                "and sizes. Supports filtering by filename pattern. Use this "
                "to discover available files before reading or searching."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Subdirectory to list, relative to workspace root. "
                            "Defaults to '.' (entire workspace)."
                        ),
                    },
                    "pattern": {
                        "type": "string",
                        "description": (
                            "Regex pattern to filter filenames. "
                            "Only files whose path matches are returned. "
                            "Example: 'judiciary' to find files with judiciary in the name."
                        ),
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": (
                "Search file contents using exact regex matching. Returns "
                "matching lines with file paths and line numbers. Matches "
                "whole words by default. Capped at 30 results. NOTE: This "
                "will NOT find synonyms or related terms. To search for a "
                "concept, search for each variant separately (e.g., "
                "'judge', 'judicial', 'judiciary' as separate calls)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": (
                            "Regex pattern to search for (case-insensitive). "
                            "Matched as whole words by default."
                        ),
                    },
                    "glob": {
                        "type": "string",
                        "description": (
                            "Comma-separated file globs to search. "
                            "Defaults to '*.md,*.txt'."
                        ),
                    },
                    "whole_words": {
                        "type": "boolean",
                        "description": (
                            "Match whole words only using word boundaries. "
                            "Defaults to true. Set to false for substring matching."
                        ),
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read a file from the workspace. Returns file content with line "
                "count. For large files, use offset and limit to paginate. "
                "Prefer search_files first to find relevant files."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path relative to workspace root",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Line number to start reading from (0-based). Defaults to 0.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of lines to read. Omit to read entire file.",
                    },
                },
                "required": ["path"],
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


def execute_tool(
    name: str, arguments_json: str, *, workspace: Path | None = None
) -> str:
    try:
        args: dict[str, Any] = json.loads(arguments_json) if arguments_json else {}
    except json.JSONDecodeError:
        return json.dumps({"error": f"Invalid JSON arguments: {arguments_json}"})

    if name == "run_python":
        return run_python(args.get("code", ""))
    if name in ("list_files", "search_files", "read_file"):
        if workspace is None:
            return json.dumps({"error": "Workspace not configured"})
        return run_file_tool(name, args, workspace)
    if name == "calculator":
        return _calculator(args.get("expression", ""))
    if name == "get_current_time":
        return _get_current_time()
    return json.dumps({"error": f"Unknown tool: {name}"})
