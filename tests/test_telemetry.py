from __future__ import annotations

import json
from pathlib import Path

from llm_harness.telemetry import AgentRun, Trace, Turn, save_trace
from llm_harness.types import ResponseEvent


class TestTurn:
    def test_default_values(self) -> None:
        turn = Turn()
        assert turn.prompt_tokens == 0
        assert turn.completion_tokens == 0
        assert turn.latency_s == 0.0
        assert turn.cost is None


class TestTrace:
    def test_empty_trace_totals(self) -> None:
        trace = Trace(model="test")
        assert trace.prompt_tokens == 0
        assert trace.completion_tokens == 0
        assert trace.latency_s == 0.0
        assert trace.cost is None

    def test_aggregated_totals(self) -> None:
        trace = Trace(model="test")
        trace.turns.append(
            Turn(prompt_tokens=10, completion_tokens=5, latency_s=1.0, cost=0.01)
        )
        trace.turns.append(
            Turn(prompt_tokens=20, completion_tokens=10, latency_s=2.0, cost=0.02)
        )
        assert trace.prompt_tokens == 30
        assert trace.completion_tokens == 15
        assert trace.latency_s == 3.0
        assert trace.cost == 0.03

    def test_cost_none_when_no_turn_has_cost(self) -> None:
        trace = Trace(model="test")
        trace.turns.append(Turn(prompt_tokens=10, completion_tokens=5, latency_s=1.0))
        assert trace.cost is None


class TestSaveTrace:
    def test_saves_json_file(self, tmp_path: Path) -> None:
        trace = Trace(model="test-model", answer="hello")
        trace.turns.append(Turn(prompt_tokens=10, completion_tokens=5, latency_s=1.0))

        out = tmp_path / "traces" / "test.json"
        save_trace(trace, out)

        assert out.exists()
        data = json.loads(out.read_text())
        assert data["model"] == "test-model"
        assert data["answer"] == "hello"
        assert len(data["turns"]) == 1
        assert data["turns"][0]["prompt_tokens"] == 10


class TestAgentRun:
    def test_iteration_yields_events(self) -> None:
        event = ResponseEvent(
            content="hi",
            prompt_tokens=0,
            completion_tokens=0,
            cached_tokens=0,
            latency_s=0.0,
            cost=None,
        )

        def gen():
            yield event

        trace = Trace(model="test")
        run = AgentRun(events=gen(), trace=trace)
        events = list(run)
        assert events == [event]

    def test_trace_accessible(self) -> None:
        trace = Trace(model="test", answer="result")
        run = AgentRun(events=iter([]), trace=trace)
        assert run.trace.answer == "result"
