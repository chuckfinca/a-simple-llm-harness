from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from llm_harness.telemetry import JsonlLogger


class TestJsonlLogger:
    def test_success_event_writes_valid_jsonl(self, tmp_path: Path) -> None:
        logger = JsonlLogger(log_dir=str(tmp_path))
        usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        message = SimpleNamespace(role="assistant", content="Hello!", tool_calls=None)
        response = SimpleNamespace(
            usage=usage, choices=[SimpleNamespace(message=message)]
        )
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 1, 1, second=2, tzinfo=UTC)

        logger.log_success_event(
            kwargs={
                "model": "test-model",
                "messages": [{"role": "user", "content": "hi"}],
            },
            response_obj=response,
            start_time=start,
            end_time=end,
        )

        log_file = tmp_path / "llm_calls.jsonl"
        assert log_file.exists()
        entry = json.loads(log_file.read_text().strip())
        assert entry["model"] == "test-model"
        assert entry["prompt_tokens"] == 10
        assert entry["completion_tokens"] == 5
        assert entry["latency_s"] == 2.0
        assert entry["response"]["role"] == "assistant"
        assert entry["response"]["content"] == "Hello!"

    def test_failure_event_includes_error(self, tmp_path: Path) -> None:
        logger = JsonlLogger(log_dir=str(tmp_path))
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 1, 1, second=1, tzinfo=UTC)

        logger.log_failure_event(
            kwargs={
                "model": "test-model",
                "messages": [],
                "exception": "Connection timeout",
            },
            response_obj=None,
            start_time=start,
            end_time=end,
        )

        log_file = tmp_path / "llm_calls.jsonl"
        entry = json.loads(log_file.read_text().strip())
        assert entry["error"] == "Connection timeout"
