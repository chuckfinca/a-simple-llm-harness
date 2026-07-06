"""One-shot LLM completion with usage and cost attached.

``run_agent_loop`` covers multi-turn tool-use sessions; this module
covers the other common shape — a single request/response call (vision
classification, structured extraction) that still wants the harness's
telemetry conventions instead of re-deriving tokens and cost from the
raw litellm response at every call site.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from llm_harness.types import Message


@dataclass
class CompletionResult:
    """The parts of a completion response callers actually consume.

    ``raw`` keeps the full litellm response for anything not lifted
    out (extra choices, provider-specific fields).
    """

    content: str | None
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    latency_s: float
    cost: float | None
    model: str
    raw: Any


def extract_usage(response: Any) -> tuple[int, int, int]:
    """(prompt_tokens, completion_tokens, cached_tokens), zeros if absent."""
    if hasattr(response, "usage") and response.usage:
        prompt_tokens = getattr(response.usage, "prompt_tokens", None)
        completion_tokens = getattr(response.usage, "completion_tokens", None)
        details = getattr(response.usage, "prompt_tokens_details", None)
        cached_tokens = getattr(details, "cached_tokens", None) or 0
        return (prompt_tokens or 0, completion_tokens or 0, cached_tokens)
    return 0, 0, 0


def extract_cost(response: Any) -> float | None:
    """USD cost litellm attached to the response, else its price-table
    estimate, else None (unknown model / free tier)."""
    cost = getattr(response, "_hidden_params", {}).get("response_cost")
    if cost is not None:
        return float(cost)
    try:
        import litellm

        return litellm.completion_cost(completion_response=response)
    except Exception:
        return None


def simple_completion(
    model: str,
    messages: list[Message],
    **kwargs: Any,
) -> CompletionResult:
    """Single ``litellm.completion`` call, no tools, no loop.

    ``kwargs`` pass through to litellm unchanged (``max_tokens``,
    ``temperature``, ``response_format``, ``num_retries``, ...).
    """
    import litellm

    started = time.monotonic()
    response = litellm.completion(model=model, messages=messages, **kwargs)
    latency_s = time.monotonic() - started

    prompt_tokens, completion_tokens, cached_tokens = extract_usage(response)
    return CompletionResult(
        content=response.choices[0].message.content,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cached_tokens=cached_tokens,
        latency_s=latency_s,
        cost=extract_cost(response),
        model=getattr(response, "model", "") or model,
        raw=response,
    )
