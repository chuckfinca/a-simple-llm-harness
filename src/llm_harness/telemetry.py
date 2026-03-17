from __future__ import annotations

import json
from collections.abc import Generator, Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from llm_harness.types import AgentEvent


@dataclass
class Turn:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    latency_s: float = 0.0
    cost: float | None = None


@dataclass
class Trace:
    model: str
    messages: list[Any] = field(default_factory=list)
    tools: list[dict[str, Any]] = field(default_factory=list)
    completion_kwargs: dict[str, Any] = field(default_factory=dict)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    turns: list[Turn] = field(default_factory=list)
    answer: str | None = None
    error: str | None = None
    wall_time_s: float = 0.0
    scratch_files: dict[str, str] = field(default_factory=dict)

    @property
    def prompt_tokens(self) -> int:
        return sum(t.prompt_tokens for t in self.turns)

    @property
    def completion_tokens(self) -> int:
        return sum(t.completion_tokens for t in self.turns)

    @property
    def cached_tokens(self) -> int:
        return sum(t.cached_tokens for t in self.turns)

    @property
    def latency_s(self) -> float:
        return round(sum(t.latency_s for t in self.turns), 2)

    @property
    def cost(self) -> float | None:
        costs = [t.cost for t in self.turns if t.cost is not None]
        return sum(costs) if costs else None


class AgentRun:
    def __init__(
        self, events: Generator[AgentEvent, None, None], trace: Trace
    ) -> None:
        self._events = events
        self.trace = trace

    def __iter__(self) -> Iterator[AgentEvent]:
        return self._events


def save_trace(trace: Trace, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(trace), indent=2, default=str))
