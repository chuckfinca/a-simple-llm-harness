from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, TypedDict


class ToolCallFunction(TypedDict):
    name: str
    arguments: str


class ToolCallDict(TypedDict):
    id: str
    type: str
    function: ToolCallFunction


class _MessageRequired(TypedDict):
    role: str
    content: str | None


class Message(_MessageRequired, total=False):
    tool_calls: list[ToolCallDict]
    tool_call_id: str


ToolDef = dict[str, Any]


class CompletionFunc(Protocol):
    def __call__(
        self,
        *,
        model: str,
        messages: list[Message],
        tools: list[ToolDef],
        **kwargs: Any,
    ) -> Any: ...


class SandboxFunc(Protocol):
    def __call__(
        self,
        code: str,
        *,
        workspace: Path | None = None,
        scratch_dir: Path | None = None,
    ) -> str: ...


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
    cached_tokens: int
    latency_s: float
    cost: float | None


AgentEvent = ToolCallEvent | ToolResultEvent | ResponseEvent
