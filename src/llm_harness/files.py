from __future__ import annotations

import functools
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

MAX_READ_CHARS = 8000
MAX_SEARCH_RESULTS = 30
WORKSPACE = Path("/workspace")
TRACE_PREFIX = "__TOOL_CALL__:"


def _resolve_within_workspace(workspace: Path, relative_path: str) -> Path | None:
    resolved = (workspace / relative_path).resolve()
    if not resolved.is_relative_to(workspace):
        return None
    return resolved


# ---------------------------------------------------------------------------
# Logging decorator — writes structured JSON to stderr so the harness
# can reconstruct per-function traces from a single run_python call.
# ---------------------------------------------------------------------------

F = TypeVar("F", bound=Callable[..., str])


def _log_call(fn: F) -> F:
    @functools.wraps(fn)
    def wrapper(*args: object, **kwargs: object) -> str:
        result = fn(*args, **kwargs)
        result_chars = len(result) if isinstance(result, str) else 0
        entry = {"name": fn.__name__, "args": kwargs or {}, "result_chars": result_chars}
        print(f"{TRACE_PREFIX}{json.dumps(entry)}", file=sys.stderr)
        return result
    return wrapper  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Private implementations (take explicit workspace)
# ---------------------------------------------------------------------------

def _list_files(workspace: Path, path: str = ".", pattern: str = "") -> str:
    target = _resolve_within_workspace(workspace, path)
    if target is None:
        return json.dumps({"error": f"Invalid path: {path}"})
    if not target.is_dir():
        return json.dumps({"error": f"Not a directory: {path}"})

    if pattern:
        try:
            name_filter = re.compile(pattern, re.IGNORECASE)
        except re.error as exc:
            return json.dumps({"error": f"Invalid pattern: {exc}"})
    else:
        name_filter = None

    entries = []
    for item in sorted(target.rglob("*")):
        if not item.is_file():
            continue
        relative = str(item.relative_to(workspace))
        if name_filter and not name_filter.search(relative):
            continue
        entries.append(
            {
                "path": relative,
                "size": item.stat().st_size,
            }
        )

    return json.dumps({"files": entries, "count": len(entries)})


def _read_file(
    workspace: Path, path: str, offset: int = 0, limit: int | None = None
) -> str:
    target = _resolve_within_workspace(workspace, path)
    if target is None:
        return json.dumps({"error": f"Invalid path: {path}"})
    if not target.is_file():
        return json.dumps({"error": f"Not a file: {path}"})

    try:
        lines = target.read_text(errors="replace").splitlines(keepends=True)
    except Exception as exc:
        return json.dumps({"error": str(exc)})

    total_lines = len(lines)
    selected = lines[offset:] if limit is None else lines[offset : offset + limit]
    content = "".join(selected)

    if len(content) > MAX_READ_CHARS:
        content = (
            content[:MAX_READ_CHARS] + f"\n\n... (truncated at {MAX_READ_CHARS} chars)"
        )

    return json.dumps(
        {
            "path": path,
            "content": content,
            "total_lines": total_lines,
            "offset": offset,
            "lines_returned": len(selected),
        }
    )


def _search_files(
    workspace: Path, pattern: str, glob: str = "*.md,*.txt", whole_words: bool = True
) -> str:
    if whole_words:
        pattern = rf"\b(?:{pattern})\b"

    try:
        compiled = re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        return json.dumps({"error": f"Invalid regex: {exc}"})

    extensions = {ext.strip() for ext in glob.split(",")}
    matches: list[dict[str, str | int]] = []
    total_matches = 0

    for ext in sorted(extensions):
        for filepath in sorted(workspace.rglob(ext)):
            if not filepath.is_file():
                continue
            try:
                lines = filepath.read_text(errors="replace").splitlines()
            except Exception:  # noqa: S112 — skip unreadable files (binary, permissions)
                continue

            relative = str(filepath.relative_to(workspace))
            for line_num, line in enumerate(lines, 1):
                if compiled.search(line):
                    total_matches += 1
                    if len(matches) < MAX_SEARCH_RESULTS:
                        matches.append(
                            {
                                "file": relative,
                                "line": line_num,
                                "text": line.strip()[:200],
                            }
                        )

    result = {
        "matches": matches,
        "total_matches": total_matches,
        "truncated": total_matches > MAX_SEARCH_RESULTS,
    }
    if total_matches > MAX_SEARCH_RESULTS:
        result["message"] = (
            f"Showing {MAX_SEARCH_RESULTS} of {total_matches} matches. "
            "Try a more specific pattern."
        )
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Public API — convenience wrappers with hardcoded workspace.
# These are what the model imports: `from tools import list_files, ...`
# ---------------------------------------------------------------------------

@_log_call
def list_files(path: str = ".", *, pattern: str = "") -> str:
    """List files in the workspace. Returns JSON with file paths and sizes.

    Args:
        path: Subdirectory to list, relative to workspace root. Defaults to ".".
        pattern: Regex to filter filenames (case-insensitive). Example: "judiciary".
    """
    return _list_files(WORKSPACE, path, pattern)


@_log_call
def read_file(path: str, *, offset: int = 0, limit: int | None = None) -> str:
    """Read a file from the workspace. Returns JSON with content and line count.

    Args:
        path: File path relative to workspace root.
        offset: Line number to start from (0-based). Defaults to 0.
        limit: Max lines to read. Omit to read entire file.
    """
    return _read_file(WORKSPACE, path, offset=offset, limit=limit)


@_log_call
def search_files(pattern: str, *, glob: str = "*.md,*.txt", whole_words: bool = True) -> str:
    """Search file contents with regex. Returns JSON with matching lines, capped at 30 results.

    Use | for variants: "judge|judicial|judiciary".

    Args:
        pattern: Regex pattern (case-insensitive, whole-word by default).
        glob: Comma-separated file globs. Defaults to "*.md,*.txt".
        whole_words: Match whole words only. Defaults to True.
    """
    return _search_files(WORKSPACE, pattern, glob=glob, whole_words=whole_words)


def help() -> str:  # noqa: A001 — intentionally shadows builtin for model discoverability
    """List available workspace functions and installed Python packages."""
    functions = [
        ("list_files(path, *, pattern)", "List files in workspace. Filter by regex pattern."),
        ("read_file(path, *, offset, limit)", "Read file content. Paginate with offset/limit."),
        ("search_files(pattern, *, glob, whole_words)", "Search file contents with regex. Use | for variants."),
        ("help()", "Show this help message."),
    ]

    lines = ["Available functions (from tools import list_files, read_file, search_files, help):", ""]
    for sig, desc in functions:
        lines.append(f"  {sig}")
        lines.append(f"    {desc}")
        lines.append("")

    lines.append("Installed packages: numpy, pandas, scipy")
    lines.append("")
    lines.append("All functions return JSON strings. Use json.loads() to parse results.")

    output = "\n".join(lines)
    print(output)
    return output


# ---------------------------------------------------------------------------
# CLI entrypoint — preserved for backward compatibility / direct testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cmd = json.loads(sys.argv[1])
    workspace = Path("/workspace")
    fn = cmd.pop("fn")
    if fn == "list_files":
        print(_list_files(workspace, cmd.get("path", "."), cmd.get("pattern", "")))
    elif fn == "search_files":
        print(
            _search_files(
                workspace,
                cmd.get("pattern", ""),
                cmd.get("glob", "*.md,*.txt"),
                cmd.get("whole_words", True),
            )
        )
    elif fn == "read_file":
        print(
            _read_file(
                workspace, cmd.get("path", ""), cmd.get("offset", 0), cmd.get("limit")
            )
        )
    else:
        print(json.dumps({"error": f"Unknown function: {fn}"}))
