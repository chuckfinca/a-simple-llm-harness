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
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    return _factory
