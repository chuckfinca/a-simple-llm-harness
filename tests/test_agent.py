from __future__ import annotations

from typing import Any

from llm_harness.agent import run_agent_loop
from llm_harness.tools import TOOL_DEFINITIONS
from llm_harness.types import Message


class TestAgentLoop:
    def test_simple_text_response(self, make_response: Any) -> None:
        text_response = make_response(content="Hello!")

        def fake_completion(**kwargs: Any) -> Any:
            return text_response

        messages: list[Message] = [{"role": "user", "content": "hi"}]
        result = run_agent_loop(
            model="test-model",
            messages=messages,
            tools=TOOL_DEFINITIONS,
            completion=fake_completion,
        )

        assert result == "Hello!"

    def test_tool_call_then_text(self, make_response: Any) -> None:
        tool_response = make_response(
            tool_calls=[
                {
                    "id": "call_1",
                    "function": {
                        "name": "calculator",
                        "arguments": '{"expression": "2 + 2"}',
                    },
                }
            ]
        )
        text_response = make_response(content="The answer is 4.")
        responses = iter([tool_response, text_response])

        def fake_completion(**kwargs: Any) -> Any:
            return next(responses)

        messages: list[Message] = [{"role": "user", "content": "what is 2+2?"}]
        result = run_agent_loop(
            model="test-model",
            messages=messages,
            tools=TOOL_DEFINITIONS,
            completion=fake_completion,
        )

        assert result == "The answer is 4."

    def test_max_turns_returns_none(self, make_response: Any) -> None:
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

        def fake_completion(**kwargs: Any) -> Any:
            return tool_response

        messages: list[Message] = [{"role": "user", "content": "loop forever"}]
        result = run_agent_loop(
            model="test-model",
            messages=messages,
            tools=TOOL_DEFINITIONS,
            completion=fake_completion,
            max_turns=3,
        )

        assert result is None

    def test_messages_mutated_correctly(self, make_response: Any) -> None:
        tool_response = make_response(
            tool_calls=[
                {
                    "id": "call_1",
                    "function": {
                        "name": "calculator",
                        "arguments": '{"expression": "1 + 1"}',
                    },
                }
            ]
        )
        text_response = make_response(content="Done.")
        responses = iter([tool_response, text_response])

        def fake_completion(**kwargs: Any) -> Any:
            return next(responses)

        messages: list[Message] = [{"role": "user", "content": "calc"}]
        run_agent_loop(
            model="test-model",
            messages=messages,
            tools=TOOL_DEFINITIONS,
            completion=fake_completion,
        )

        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["tool_calls"] is not None
        assert messages[2]["role"] == "tool"
        assert messages[3]["role"] == "assistant"
        assert messages[3]["content"] == "Done."
