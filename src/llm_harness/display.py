from __future__ import annotations

import json

from rich.console import Console
from rich.markdown import Markdown
from rich.syntax import Syntax

from llm_harness.types import AgentEvent, ResponseEvent, ToolCallEvent, ToolResultEvent

console = Console()

INLINE_TRUNCATE = 200


def display_event(event: AgentEvent) -> None:
    if isinstance(event, ToolCallEvent):
        print_tool_call(event)
    elif isinstance(event, ToolResultEvent):
        print_tool_result(event)
    elif isinstance(event, ResponseEvent):
        print_response(event)


def print_header(model: str) -> None:
    console.print(f"[bold]llm-harness[/bold] ({model})")
    console.print("Type 'quit' to exit.\n")


def print_tool_call(event: ToolCallEvent) -> None:
    if event.name == "run_python":
        try:
            code = json.loads(event.arguments).get("code", "")
        except (json.JSONDecodeError, TypeError):
            code = event.arguments
        console.print("  [bright_black]\\[tool][/bright_black] [cyan]run_python[/cyan]")
        console.print(Syntax(code, "python", padding=(0, 4)))
        return
    args_preview = _truncate(event.arguments, INLINE_TRUNCATE)
    console.print(
        f"  [bright_black]\\[tool][/bright_black] [cyan]{event.name}[/cyan]({args_preview})"
    )


def print_tool_result(event: ToolResultEvent) -> None:
    result_preview = _truncate(event.result, INLINE_TRUNCATE)
    console.print(f"  [bright_black]\\[result][/bright_black] {result_preview}")


def print_response(event: ResponseEvent) -> None:
    if event.content:
        console.print()
        console.print(Markdown(event.content))
    else:
        console.print("\n[yellow]\\[max turns reached][/yellow]")

    parts = [f"{event.latency_s}s"]
    if event.prompt_tokens or event.completion_tokens:
        token_info = f"{event.prompt_tokens} in, {event.completion_tokens} out"
        if event.cached_tokens:
            token_info += f" ({event.cached_tokens} cached)"
        parts.append(token_info)
    if event.cost is not None:
        parts.append(f"${event.cost:.4f}")
    console.print(f"[bright_black]{' | '.join(parts)}[/bright_black]\n")


def print_error(message: str) -> None:
    console.print(f"\n[red]error>[/red] {message}\n")


def _truncate(text: str, limit: int) -> str:
    text = text.replace("\n", "\\n")
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."
