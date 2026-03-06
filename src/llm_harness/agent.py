from __future__ import annotations

from typing import Any

from llm_harness.tools import execute_tool
from llm_harness.types import CompletionFunc, Message, ToolDef


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


def run_agent_loop(
    *,
    model: str,
    messages: list[Message],
    tools: list[ToolDef],
    completion: CompletionFunc,
    max_turns: int = 20,
) -> str | None:
    for _ in range(max_turns):
        response = completion(model=model, messages=messages, tools=tools)
        assistant_msg = _parse_response_message(response)
        messages.append(assistant_msg)

        if not assistant_msg.get("tool_calls"):
            return assistant_msg.get("content")

        for tool_call in assistant_msg["tool_calls"]:
            fn = tool_call["function"]
            result = execute_tool(fn["name"], fn["arguments"])
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": result,
                }
            )

    return None
