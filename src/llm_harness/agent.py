from __future__ import annotations

import time
from collections.abc import Generator
from pathlib import Path
from typing import Any

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
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in msg.tool_calls
        ]
    return result


def _extract_usage(response: Any) -> tuple[int, int]:
    if hasattr(response, "usage") and response.usage:
        return (
            getattr(response.usage, "prompt_tokens", 0) or 0,
            getattr(response.usage, "completion_tokens", 0) or 0,
        )
    return 0, 0


def _extract_cost(response: Any) -> float | None:
    cost = getattr(response, "_hidden_params", {}).get("response_cost")
    return float(cost) if cost is not None else None


def run_agent_loop(
    *,
    model: str,
    messages: list[Message],
    tools: list[ToolDef],
    completion: CompletionFunc,
    workspace: Path | None = None,
    max_turns: int = 20,
) -> Generator[AgentEvent, None, None]:
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_latency = 0.0
    total_cost: float | None = 0.0

    for _ in range(max_turns):
        start = time.monotonic()
        response = completion(model=model, messages=messages, tools=tools)
        elapsed = time.monotonic() - start

        prompt_tokens, completion_tokens = _extract_usage(response)
        total_prompt_tokens += prompt_tokens
        total_completion_tokens += completion_tokens
        total_latency += elapsed

        cost = _extract_cost(response)
        if cost is not None and total_cost is not None:
            total_cost += cost
        else:
            total_cost = None

        assistant_msg = _parse_response_message(response)
        messages.append(assistant_msg)

        if not assistant_msg.get("tool_calls"):
            yield ResponseEvent(
                content=assistant_msg.get("content"),
                prompt_tokens=total_prompt_tokens,
                completion_tokens=total_completion_tokens,
                latency_s=round(total_latency, 2),
                cost=total_cost,
            )
            return

        for tool_call in assistant_msg["tool_calls"]:
            fn = tool_call["function"]
            yield ToolCallEvent(name=fn["name"], arguments=fn["arguments"])

            result = execute_tool(fn["name"], fn["arguments"], workspace=workspace)
            yield ToolResultEvent(name=fn["name"], result=result)

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": result,
                }
            )

    yield ResponseEvent(
        content=None,
        prompt_tokens=total_prompt_tokens,
        completion_tokens=total_completion_tokens,
        latency_s=round(total_latency, 2),
        cost=total_cost,
    )
