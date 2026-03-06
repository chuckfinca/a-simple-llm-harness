from __future__ import annotations

from typing import Any, Protocol

Message = dict[str, Any]
ToolDef = dict[str, Any]


class CompletionFunc(Protocol):
    def __call__(
        self,
        *,
        model: str,
        messages: list[Message],
        tools: list[ToolDef],
    ) -> Any: ...
