"""E2B-based sandbox for cloud deployment without Docker."""

from __future__ import annotations

import json
from pathlib import Path

from e2b_code_interpreter import Sandbox

from llm_harness.sandbox import TIMEOUT_SECONDS, _truncate

# Reuse a sandbox across tool calls within a session.
# The caller manages the lifecycle via create/close.
_active_sandbox: Sandbox | None = None


def get_or_create_sandbox(
    workspace: Path | None = None,
    scratch_dir: Path | None = None,
) -> Sandbox:
    """Get the active sandbox, creating one if needed and uploading workspace files."""
    global _active_sandbox
    if _active_sandbox is not None:
        return _active_sandbox

    _active_sandbox = Sandbox(timeout=300)

    # Create workspace and scratchpad directories
    _active_sandbox.commands.run("mkdir -p /workspace /scratchpad")

    # Upload workspace files
    if workspace is not None:
        for file_path in workspace.iterdir():
            if file_path.is_file():
                _active_sandbox.files.write(
                    f"/workspace/{file_path.name}",
                    file_path.read_bytes(),
                )

    return _active_sandbox


def close_sandbox() -> None:
    global _active_sandbox
    if _active_sandbox is not None:
        _active_sandbox.kill()
        _active_sandbox = None


def run_python(
    code: str,
    *,
    workspace: Path | None = None,
    scratch_dir: Path | None = None,
    timeout: int = TIMEOUT_SECONDS,
) -> str:
    """Execute Python code in an E2B sandbox. Same interface as sandbox.run_python."""
    sandbox = get_or_create_sandbox(workspace, scratch_dir)

    try:
        execution = sandbox.run_code(code, timeout=timeout)

        stdout = "\n".join(line.text for line in execution.logs.stdout)
        stderr = "\n".join(line.text for line in execution.logs.stderr)

        if execution.error:
            stderr += f"\n{execution.error.name}: {execution.error.value}"
            exit_code = 1
        else:
            exit_code = 0

        return json.dumps(
            {
                "stdout": _truncate(stdout),
                "stderr": _truncate(stderr),
                "exit_code": exit_code,
                "timed_out": False,
            }
        )
    except TimeoutError:
        return json.dumps(
            {
                "stdout": "",
                "stderr": "Execution timed out.",
                "exit_code": -1,
                "timed_out": True,
            }
        )
