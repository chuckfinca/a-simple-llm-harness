from __future__ import annotations

import time
from collections.abc import Generator
from pathlib import Path
from typing import Any

from llm_harness.telemetry import AgentRun, Trace, Turn
from llm_harness.tools import execute_tool
from llm_harness.types import (
    AgentEvent,
    CompletionFunc,
    Message,
    ResponseEvent,
    ToolCallEvent,
    ToolDef,
    ToolResultEvent,
)


def _parse_response_message(response: Any) -> Message:
    msg = response.choices[0].message
    result: Message = {"role": msg.role, "content": msg.content}
    if msg.tool_calls:
        result["tool_calls"] = [
            {
                "id": tool_call.id,
                "type": "function",
                "function": {
                    "name": tool_call.function.name,
                    "arguments": tool_call.function.arguments,
                },
            }
            for tool_call in msg.tool_calls
        ]
    return result


def _extract_usage(response: Any) -> tuple[int, int]:
    if hasattr(response, "usage") and response.usage:
        prompt_tokens = getattr(response.usage, "prompt_tokens", None)
        completion_tokens = getattr(response.usage, "completion_tokens", None)
        return (prompt_tokens or 0, completion_tokens or 0)
    return 0, 0


def _extract_cost(response: Any) -> float | None:
    cost = getattr(response, "_hidden_params", {}).get("response_cost")
    return float(cost) if cost is not None else None


def _run_loop(
    *,
    model: str,
    messages: list[Message],
    tools: list[ToolDef],
    completion: CompletionFunc,
    workspace: Path | None = None,
    max_turns: int = 20,
    trace: Trace,
) -> Generator[AgentEvent, None, None]:
    for _ in range(max_turns):
        start = time.monotonic()
        response = completion(model=model, messages=messages, tools=tools)
        elapsed = time.monotonic() - start

        prompt_tokens, completion_tokens = _extract_usage(response)
        cost = _extract_cost(response)

        trace.turns.append(
            Turn(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_s=round(elapsed, 2),
                cost=cost,
            )
        )

        assistant_msg = _parse_response_message(response)
        messages.append(assistant_msg)

        if not assistant_msg.get("tool_calls"):
            trace.answer = assistant_msg.get("content")
            yield ResponseEvent(
                content=trace.answer,
                prompt_tokens=trace.prompt_tokens,
                completion_tokens=trace.completion_tokens,
                latency_s=trace.latency_s,
                cost=trace.cost,
            )
            return

        for tool_call in assistant_msg["tool_calls"]:
            tool_function = tool_call["function"]
            yield ToolCallEvent(
                name=tool_function["name"], arguments=tool_function["arguments"]
            )

            result = execute_tool(
                tool_function["name"], tool_function["arguments"], workspace=workspace
            )
            yield ToolResultEvent(name=tool_function["name"], result=result)

            trace.tool_calls.append(
                {
                    "name": tool_function["name"],
                    "arguments": tool_function["arguments"],
                    "result": result,
                }
            )

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": result,
                }
            )

    yield ResponseEvent(
        content=None,
        prompt_tokens=trace.prompt_tokens,
        completion_tokens=trace.completion_tokens,
        latency_s=trace.latency_s,
        cost=trace.cost,
    )


def run_agent_loop(
    *,
    model: str,
    messages: list[Message],
    tools: list[ToolDef],
    completion: CompletionFunc,
    workspace: Path | None = None,
    max_turns: int = 20,
) -> AgentRun:
    trace = Trace(model=model, messages=messages)
    events = _run_loop(
        model=model,
        messages=messages,
        tools=tools,
        completion=completion,
        workspace=workspace,
        max_turns=max_turns,
        trace=trace,
    )
    return AgentRun(events=events, trace=trace)
