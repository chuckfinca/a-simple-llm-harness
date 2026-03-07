from __future__ import annotations

from typing import Any

from llm_harness.agent import run_agent_loop
from llm_harness.tools import TOOL_DEFINITIONS
from llm_harness.types import (
    Message,
    ResponseEvent,
    ToolCallEvent,
    ToolResultEvent,
)


def _collect_events(
    responses: list[Any],
    messages: list[Message] | None = None,
    max_turns: int = 20,
) -> list[Any]:
    response_iter = iter(responses)

    def fake_completion(**kwargs: Any) -> Any:
        return next(response_iter)

    if messages is None:
        messages = [{"role": "user", "content": "test"}]

    return list(
        run_agent_loop(
            model="test-model",
            messages=messages,
            tools=TOOL_DEFINITIONS,
            completion=fake_completion,
            max_turns=max_turns,
        )
    )


class TestAgentLoop:
    def test_simple_text_response(self, make_response: Any) -> None:
        events = _collect_events([make_response(content="Hello!")])

        assert len(events) == 1
        assert isinstance(events[0], ResponseEvent)
        assert events[0].content == "Hello!"

    def test_tool_call_then_text(self, make_response: Any) -> None:
        events = _collect_events(
            [
                make_response(
                    tool_calls=[
                        {
                            "id": "call_1",
                            "function": {
                                "name": "calculator",
                                "arguments": '{"expression": "2 + 2"}',
                            },
                        }
                    ]
                ),
                make_response(content="The answer is 4."),
            ]
        )

        assert isinstance(events[0], ToolCallEvent)
        assert events[0].name == "calculator"
        assert isinstance(events[1], ToolResultEvent)
        assert events[1].name == "calculator"
        assert isinstance(events[2], ResponseEvent)
        assert events[2].content == "The answer is 4."

    def test_max_turns_returns_none_content(self, make_response: Any) -> None:
        tool_response = make_response(
            tool_calls=[
                {
                    "id": "call_1",
                    "function": {
                        "name": "get_current_time",
                        "arguments": "{}",
                    },
                }
            ]
        )

        events = _collect_events(
            [tool_response] * 6,
            max_turns=3,
        )

        response_events = [e for e in events if isinstance(e, ResponseEvent)]
        assert len(response_events) == 1
        assert response_events[0].content is None

    def test_messages_mutated_correctly(self, make_response: Any) -> None:
        messages: list[Message] = [{"role": "user", "content": "calc"}]

        _collect_events(
            [
                make_response(
                    tool_calls=[
                        {
                            "id": "call_1",
                            "function": {
                                "name": "calculator",
                                "arguments": '{"expression": "1 + 1"}',
                            },
                        }
                    ]
                ),
                make_response(content="Done."),
            ],
            messages=messages,
        )

        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["tool_calls"] is not None
        assert messages[2]["role"] == "tool"
        assert messages[3]["role"] == "assistant"
        assert messages[3]["content"] == "Done."

    def test_response_event_has_metadata(self, make_response: Any) -> None:
        events = _collect_events([make_response(content="Hi")])

        response = events[0]
        assert isinstance(response, ResponseEvent)
        assert isinstance(response.latency_s, float)
        assert isinstance(response.prompt_tokens, int)
        assert isinstance(response.completion_tokens, int)
