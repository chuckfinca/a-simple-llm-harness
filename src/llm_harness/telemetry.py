from __future__ import annotations

import json
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
            try:
                latency = (end_time - start_time).total_seconds()
            except Exception:
                latency = None

            response_message = None
            if (
                response_obj
                and hasattr(response_obj, "choices")
                and response_obj.choices
            ):
                choice = response_obj.choices[0]
                if hasattr(choice, "message"):
                    msg = choice.message
                    response_message = {
                        "role": getattr(msg, "role", None),
                        "content": getattr(msg, "content", None),
                    }
                    if getattr(msg, "tool_calls", None):
                        response_message["tool_calls"] = [
                            {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            }
                            for tc in msg.tool_calls
                        ]

            additional_args = kwargs.get("additional_args", {})

            entry: dict[str, Any] = {
                "timestamp": time.time(),
                "model": kwargs.get("model"),
                "messages": kwargs.get("messages"),
                "response": response_message,
                "provider_request": additional_args.get("complete_input_dict"),
                "provider_api_base": additional_args.get("api_base"),
                "latency_s": latency,
            }

            if response_obj and hasattr(response_obj, "usage") and response_obj.usage:
                usage = response_obj.usage
                entry["prompt_tokens"] = getattr(usage, "prompt_tokens", None)
                entry["completion_tokens"] = getattr(usage, "completion_tokens", None)
                entry["total_tokens"] = getattr(usage, "total_tokens", None)

            entry["cost"] = kwargs.get("response_cost")
            entry["cache_hit"] = kwargs.get("cache_hit")

            if error is not None:
                entry["error"] = str(error)

            with open(self._log_path, "a") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except Exception:
            pass
