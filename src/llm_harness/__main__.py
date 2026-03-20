from __future__ import annotations

import os
import tempfile
from pathlib import Path

import litellm
from dotenv import load_dotenv

from llm_harness.agent import run_agent_loop
from llm_harness.display import (
    console,
    display_event,
    print_error,
    print_header,
)
from llm_harness.prompt import build_system_prompt
from llm_harness.tools import TOOL_DEFINITIONS
from llm_harness.types import Message


def main() -> None:
    load_dotenv()
    litellm.suppress_debug_info = True

    model = os.environ.get("LH_MODEL")
    if not model:
        print_error("LH_MODEL is required (set in .env or environment)")
        return

    system_prompt = os.environ.get("LH_SYSTEM_PROMPT")
    if not system_prompt:
        print_error("LH_SYSTEM_PROMPT is required (set in .env or environment)")
        return

    workspace_path = os.environ.get("LH_WORKSPACE")
    workspace: Path | None = None
    if workspace_path:
        workspace = Path(workspace_path).resolve()
        if not workspace.is_dir():
            print_error(f"Workspace is not a directory: {workspace}")
            return

    system_prompt = build_system_prompt(
        base_prompt=system_prompt,
        workspace=workspace,
    )

    messages: list[Message] = [{"role": "system", "content": system_prompt}]

    print_header(model)

    with tempfile.TemporaryDirectory(prefix="lh-scratch-") as scratch:
        scratch_dir = Path(scratch)
        while True:
            try:
                user_input = console.input("[bold]you>[/bold] ").strip()
            except (EOFError, KeyboardInterrupt):
                console.print()
                break

            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit"):
                break

            messages.append({"role": "user", "content": user_input})

            try:
                agent_run = run_agent_loop(
                    model=model,
                    messages=messages,
                    tools=TOOL_DEFINITIONS,
                    completion=litellm.completion,
                    workspace=workspace,
                    scratch_dir=scratch_dir,
                )
                for event in agent_run:
                    display_event(event)
            except Exception as exc:
                messages.pop()
                print_error(str(exc))


if __name__ == "__main__":
    main()
