from __future__ import annotations

import os
from pathlib import Path

import litellm
from dotenv import load_dotenv

litellm.suppress_debug_info = True

from llm_harness.agent import run_agent_loop
from llm_harness.display import (
    console,
    print_error,
    print_header,
    print_response,
    print_tool_call,
    print_tool_result,
)
from llm_harness.files import set_workspace
from llm_harness.prompt import build_system_prompt
from llm_harness.telemetry import JsonlLogger
from llm_harness.tools import TOOL_DEFINITIONS
from llm_harness.types import (
    Message,
    ResponseEvent,
    ToolCallEvent,
    ToolResultEvent,
)


def main() -> None:
    load_dotenv()

    model = os.environ.get("LH_MODEL")
    if not model:
        print_error("LH_MODEL is required (set in .env or environment)")
        return

    system_prompt = os.environ.get("LH_SYSTEM_PROMPT")
    if not system_prompt:
        print_error("LH_SYSTEM_PROMPT is required (set in .env or environment)")
        return

    workspace = os.environ.get("LH_WORKSPACE")
    if workspace:
        try:
            set_workspace(workspace)
        except ValueError as exc:
            print_error(str(exc))
            return

    system_prompt = build_system_prompt(
        base_prompt=system_prompt,
        workspace=Path(workspace).resolve() if workspace else None,
    )

    litellm.callbacks = [JsonlLogger()]

    messages: list[Message] = [{"role": "system", "content": system_prompt}]

    print_header(model)

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
            for event in run_agent_loop(
                model=model,
                messages=messages,
                tools=TOOL_DEFINITIONS,
                completion=litellm.completion,
            ):
                if isinstance(event, ToolCallEvent):
                    print_tool_call(event)
                elif isinstance(event, ToolResultEvent):
                    print_tool_result(event)
                elif isinstance(event, ResponseEvent):
                    print_response(event)
        except Exception as exc:
            messages.pop()
            print_error(str(exc))


if __name__ == "__main__":
    main()
