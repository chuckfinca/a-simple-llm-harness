"""One-shot LLM completion with usage and cost attached.

``run_agent_loop`` covers multi-turn tool-use sessions; this module
covers the other common shape — a single request/response call (vision
classification, structured extraction) that still wants the harness's
telemetry conventions instead of re-deriving tokens and cost from the
raw litellm response at every call site.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from llm_harness.types import Message

logger = logging.getLogger(__name__)


@dataclass
class CompletionResult:
    """The parts of a completion response callers actually consume.

    ``raw`` keeps the full litellm response for anything not lifted
    out (extra choices, provider-specific fields).

    Token fields are ``None`` when the provider didn't report usage at
    all, distinct from an explicit ``0`` — collapsing the two would
    make "the provider went silent" indistinguishable from "this call
    genuinely used no tokens" for any caller summing or monitoring
    usage across calls.
    """

    content: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    cached_tokens: int | None
    latency_s: float
    cost: float | None
    model: str
    raw: Any


def extract_usage(response: Any) -> tuple[int | None, int | None, int | None]:
    """(prompt_tokens, completion_tokens, cached_tokens); each ``None``
    when the provider didn't report it, distinct from an explicit 0."""
    usage = getattr(response, "usage", None)
    if not usage:
        return None, None, None
    prompt_tokens = getattr(usage, "prompt_tokens", None)
    completion_tokens = getattr(usage, "completion_tokens", None)
    details = getattr(usage, "prompt_tokens_details", None)
    cached_tokens = getattr(details, "cached_tokens", None) if details is not None else None
    return prompt_tokens, completion_tokens, cached_tokens


def extract_cost(response: Any) -> float | None:
    """USD cost litellm attached to the response, else its price-table
    estimate, else None (unknown model / free tier).

    The price-table estimate can fail for reasons unrelated to the
    completion itself (model missing from litellm's price table, a
    litellm version mismatch) — logged rather than raised, since cost
    is best-effort telemetry that must never take down an otherwise-
    successful completion, but a silent swallow would hide a genuinely
    broken cost estimate behind an identical-looking "free" model.
    """
    cost = getattr(response, "_hidden_params", {}).get("response_cost")
    if cost is not None:
        return float(cost)
    try:
        import litellm

        return litellm.completion_cost(completion_response=response)
    except Exception:
        logger.warning(
            "completion_cost estimate failed for model=%s",
            getattr(response, "model", "<unknown>"),
            exc_info=True,
        )
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
