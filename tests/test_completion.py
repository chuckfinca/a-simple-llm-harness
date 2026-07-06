from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import litellm
import pytest

from llm_harness.completion import CompletionResult, simple_completion
from llm_harness.types import Message


@pytest.fixture
def capture_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    """Patch ``litellm.completion``; returns a dict that records the call
    kwargs and lets the test choose the canned response via ``response``."""
    captured: dict[str, Any] = {"response": None}

    def fake_completion(**kwargs: Any) -> Any:
        captured["kwargs"] = kwargs
        return captured["response"]

    monkeypatch.setattr(litellm, "completion", fake_completion)
    return captured


class TestSimpleCompletion:
    def test_returns_content_usage_and_cost(
        self, make_response: Any, capture_completion: dict[str, Any]
    ) -> None:
        capture_completion["response"] = make_response(
            content="42",
            usage={"prompt_tokens": 10, "completion_tokens": 3},
            response_cost=0.004,
            model="test-model-v2",
        )

        result = simple_completion("test-model", [{"role": "user", "content": "q"}])

        assert isinstance(result, CompletionResult)
        assert result.content == "42"
        assert result.prompt_tokens == 10
        assert result.completion_tokens == 3
        assert result.cached_tokens == 0
        assert result.cost == 0.004
        assert result.model == "test-model-v2"
        assert result.latency_s >= 0.0
        assert result.raw is capture_completion["response"]

    def test_kwargs_pass_through_to_litellm(
        self, make_response: Any, capture_completion: dict[str, Any]
    ) -> None:
        capture_completion["response"] = make_response(content="{}")
        messages: list[Message] = [{"role": "user", "content": "q"}]

        simple_completion(
            "test-model",
            messages,
            max_tokens=8,
            temperature=0.0,
            response_format={"type": "json_object"},
        )

        kwargs = capture_completion["kwargs"]
        assert kwargs["model"] == "test-model"
        assert kwargs["messages"] is messages
        assert kwargs["max_tokens"] == 8
        assert kwargs["temperature"] == 0.0
        assert kwargs["response_format"] == {"type": "json_object"}

    def test_image_url_content_blocks_forwarded_unchanged(
        self, make_response: Any, capture_completion: dict[str, Any]
    ) -> None:
        capture_completion["response"] = make_response(content="0")
        messages: list[Message] = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Which rotation?"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64,AAAA"},
                    },
                ],
            }
        ]

        simple_completion("test-model", messages)

        sent = capture_completion["kwargs"]["messages"][0]["content"]
        assert sent[0] == {"type": "text", "text": "Which rotation?"}
        assert sent[1]["image_url"]["url"] == "data:image/png;base64,AAAA"

    def test_cached_tokens_extracted_from_usage_details(
        self, make_response: Any, capture_completion: dict[str, Any]
    ) -> None:
        capture_completion["response"] = make_response(
            content="ok",
            usage={
                "prompt_tokens": 20,
                "completion_tokens": 5,
                "prompt_tokens_details": SimpleNamespace(cached_tokens=12),
            },
        )

        result = simple_completion("test-model", [{"role": "user", "content": "q"}])

        assert result.cached_tokens == 12

    def test_missing_usage_yields_zero_tokens(
        self, make_response: Any, capture_completion: dict[str, Any]
    ) -> None:
        capture_completion["response"] = make_response(content="ok")

        result = simple_completion("test-model", [{"role": "user", "content": "q"}])

        assert result.prompt_tokens == 0
        assert result.completion_tokens == 0
        assert result.cached_tokens == 0

    def test_cost_falls_back_to_completion_cost(
        self,
        make_response: Any,
        capture_completion: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        capture_completion["response"] = make_response(content="ok")
        monkeypatch.setattr(
            litellm, "completion_cost", lambda completion_response: 0.0125
        )

        result = simple_completion("test-model", [{"role": "user", "content": "q"}])

        assert result.cost == 0.0125

    def test_cost_none_when_unpriceable(
        self,
        make_response: Any,
        capture_completion: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        capture_completion["response"] = make_response(content="ok")

        def raise_unpriced(completion_response: Any) -> float:
            raise ValueError("model not in price table")

        monkeypatch.setattr(litellm, "completion_cost", raise_unpriced)

        result = simple_completion("test-model", [{"role": "user", "content": "q"}])

        assert result.cost is None

    def test_model_falls_back_to_requested_when_response_omits_it(
        self, make_response: Any, capture_completion: dict[str, Any]
    ) -> None:
        capture_completion["response"] = make_response(content="ok")

        result = simple_completion("test-model", [{"role": "user", "content": "q"}])

        assert result.model == "test-model"
