from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

from litellm.integrations.custom_logger import CustomLogger


class JsonlLogger(CustomLogger):
    def __init__(self, log_dir: str = "logs") -> None:
        self._log_path = Path(log_dir) / "llm_calls.jsonl"
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

    def log_success_event(
        self,
        kwargs: dict[str, Any],
        response_obj: Any,
        start_time: Any,
        end_time: Any,
    ) -> None:
        self._write_entry(kwargs, response_obj, start_time, end_time)

    def log_failure_event(
        self,
        kwargs: dict[str, Any],
        response_obj: Any,
        start_time: Any,
        end_time: Any,
    ) -> None:
        self._write_entry(
            kwargs, response_obj, start_time, end_time, error=kwargs.get("exception")
        )

    def _write_entry(
        self,
        kwargs: dict[str, Any],
        response_obj: Any,
        start_time: Any,
        end_time: Any,
        error: Any = None,
    ) -> None:
        try:
            additional_args = kwargs.get("additional_args", {})

            entry: dict[str, Any] = {
                "timestamp": time.time(),
                "model": kwargs.get("model"),
                "messages": kwargs.get("messages"),
                "response": _extract_response(response_obj),
                "provider_request": additional_args.get("complete_input_dict"),
                "provider_api_base": additional_args.get("api_base"),
                "latency_s": _compute_latency(start_time, end_time),
                "cost": kwargs.get("response_cost"),
                "cache_hit": kwargs.get("cache_hit"),
                **_extract_usage(response_obj),
            }

            if error is not None:
                entry["error"] = str(error)

            with open(self._log_path, "a") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except Exception as exc:
            print(f"telemetry: failed to write log entry: {exc}", file=sys.stderr)


def _compute_latency(start_time: Any, end_time: Any) -> float | None:
    try:
        return (end_time - start_time).total_seconds()
    except Exception:
        return None


def _extract_response(response_obj: Any) -> dict[str, Any] | None:
    if not response_obj or not getattr(response_obj, "choices", None):
        return None
    msg = getattr(response_obj.choices[0], "message", None)
    if msg is None:
        return None

    result: dict[str, Any] = {
        "role": getattr(msg, "role", None),
        "content": getattr(msg, "content", None),
    }
    if getattr(msg, "tool_calls", None):
        result["tool_calls"] = [
            {"name": tc.function.name, "arguments": tc.function.arguments}
            for tc in msg.tool_calls
        ]
    return result


def _extract_usage(response_obj: Any) -> dict[str, Any]:
    if not response_obj or not getattr(response_obj, "usage", None):
        return {}
    usage = response_obj.usage
    return {
        "prompt_tokens": getattr(usage, "prompt_tokens", None),
        "completion_tokens": getattr(usage, "completion_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
    }
