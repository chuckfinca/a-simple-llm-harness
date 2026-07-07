from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import litellm
import pytest

litellm.suppress_debug_info = True

MakeResponse = Callable[..., SimpleNamespace]


@pytest.fixture
def make_response() -> MakeResponse:
    def _factory(
        content: str | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        usage: dict[str, Any] | None = None,
        response_cost: float | None = None,
        model: str | None = None,
    ) -> SimpleNamespace:
        tc_objects = None
        if tool_calls:
            tc_objects = [
                SimpleNamespace(
                    id=tc["id"],
                    function=SimpleNamespace(
                        name=tc["function"]["name"],
                        arguments=tc["function"]["arguments"],
                    ),
                )
                for tc in tool_calls
            ]

        message = SimpleNamespace(
            role="assistant",
            content=content,
            tool_calls=tc_objects,
        )
        response = SimpleNamespace(choices=[SimpleNamespace(message=message)])
        if usage is not None:
            response.usage = SimpleNamespace(**usage)
        if response_cost is not None:
            response._hidden_params = {"response_cost": response_cost}
        if model is not None:
            response.model = model
        return response

    return _factory
