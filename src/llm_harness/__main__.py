from __future__ import annotations

import os
from pathlib import Path

import litellm
from dotenv import load_dotenv

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
from llm_harness.telemetry import JsonlLogger
from llm_harness.tools import TOOL_DEFINITIONS
from llm_harness.types import (
    Message,
    ResponseEvent,
    ToolCallEvent,
    ToolResultEvent,
)


def _workspace_context(workspace: str) -> str:
    resolved = Path(workspace).resolve()
    file_count = sum(1 for p in resolved.rglob("*") if p.is_file())
    return (
        "\n\n## Workspace\n\n"
        f"You have access to a workspace directory containing {file_count} text documents. "
        "Use list_files, search_files, and read_file to explore them.\n\n"
        "When searching the workspace:\n"
        "- Extract key nouns from the question. Ignore task words like "
        '"discuss" or "analyze."\n'
        "- Generate 3-5 search terms per concept: synonyms, related words, "
        "and morphological variants (e.g., judge/judicial/judiciary). A single "
        "term misses most relevant documents.\n"
        "- Start with the most specific terms. Broaden only if needed.\n"
        "- Search synonyms separately — do not combine them in one search.\n"
        "- After finding a relevant document, scan it for new terms you "
        "haven't searched for yet.\n"
        "- Stop searching when additional searches aren't finding new "
        "relevant documents.\n"
        "- Cite sources with filename and line number, e.g. "
        "(federalist-10-the-same-subject-continued.txt:42)."
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
        system_prompt += _workspace_context(workspace)

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
