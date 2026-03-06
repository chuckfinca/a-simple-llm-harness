from __future__ import annotations

from dataclasses import dataclass
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


@dataclass
class ToolCallEvent:
    name: str
    arguments: str


@dataclass
class ToolResultEvent:
    name: str
    result: str


@dataclass
class ResponseEvent:
    content: str | None
    prompt_tokens: int
    completion_tokens: int
    latency_s: float
    cost: float | None


AgentEvent = ToolCallEvent | ToolResultEvent | ResponseEvent
