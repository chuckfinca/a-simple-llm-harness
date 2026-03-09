from __future__ import annotations

import json
import re
from pathlib import Path

MAX_READ_CHARS = 8000
MAX_SEARCH_RESULTS = 30


def _resolve_within_workspace(workspace: Path, relative_path: str) -> Path | None:
    resolved = (workspace / relative_path).resolve()
    if not resolved.is_relative_to(workspace):
        return None
    return resolved


def list_files(workspace: Path, path: str = ".", pattern: str = "") -> str:
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


def read_file(
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


def search_files(
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


if __name__ == "__main__":
    import sys

    cmd = json.loads(sys.argv[1])
    workspace = Path("/workspace")
    fn = cmd.pop("fn")
    if fn == "list_files":
        print(list_files(workspace, cmd.get("path", "."), cmd.get("pattern", "")))
    elif fn == "search_files":
        print(
            search_files(
                workspace,
                cmd.get("pattern", ""),
                cmd.get("glob", "*.md,*.txt"),
                cmd.get("whole_words", True),
            )
        )
    elif fn == "read_file":
        print(
            read_file(
                workspace, cmd.get("path", ""), cmd.get("offset", 0), cmd.get("limit")
            )
        )
    else:
        print(json.dumps({"error": f"Unknown function: {fn}"}))
