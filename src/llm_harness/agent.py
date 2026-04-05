from __future__ import annotations

import tempfile
import time
from collections.abc import Generator
from pathlib import Path
from typing import Any

from llm_harness.telemetry import AgentRun, Trace, Turn
from llm_harness.tools import execute_tool
from llm_harness.types import (
    AgentEvent,
    CompletionFunc,
    Message,
    ResponseEvent,
    SandboxFunc,
    TextDeltaEvent,
    ToolCallEvent,
    ToolDef,
    ToolResultEvent,
)


def _parse_response_message(response: Any) -> Message:
    msg = response.choices[0].message
    result: Message = {"role": msg.role, "content": msg.content}
    if msg.tool_calls:
        result["tool_calls"] = [
            {
                "id": tool_call.id,
                "type": "function",
                "function": {
                    "name": tool_call.function.name,
                    "arguments": tool_call.function.arguments,
                },
            }
            for tool_call in msg.tool_calls
        ]
    return result


def _extract_usage(response: Any) -> tuple[int, int, int]:
    if hasattr(response, "usage") and response.usage:
        prompt_tokens = getattr(response.usage, "prompt_tokens", None)
        completion_tokens = getattr(response.usage, "completion_tokens", None)
        details = getattr(response.usage, "prompt_tokens_details", None)
        cached_tokens = getattr(details, "cached_tokens", None) or 0
        return (prompt_tokens or 0, completion_tokens or 0, cached_tokens)
    return 0, 0, 0


def _extract_cost(response: Any) -> float | None:
    cost = getattr(response, "_hidden_params", {}).get("response_cost")
    if cost is not None:
        return float(cost)
    try:
        import litellm
        return litellm.completion_cost(completion_response=response)
    except Exception:
        return None


def _should_nudge(workspace: Path | None, trace: Trace, nudged: bool) -> bool:
    """Without a nudge, models often answer from memory instead of exploring
    the workspace — producing ungrounded responses with no citations."""
    return bool(workspace) and not trace.tool_calls and not nudged


_NUDGE_MESSAGE: Message = {
    "role": "user",
    "content": (
        "Use the workspace tools to find evidence that supports "
        "your answer. Do not answer from memory alone."
    ),
}

# Cache the system prompt (stable across turns) and the most recent message
# (likely to appear again as context in the next turn's prompt)
_DEFAULT_CACHE_INJECTION = [
    {"location": "message", "role": "system"},
    {"location": "message", "index": -1},
]


def _snapshot_scratch(scratch_dir: Path) -> dict[str, str]:
    files = {}
    for p in sorted(scratch_dir.rglob("*")):
        if not p.is_file():
            continue
        try:
            files[str(p.relative_to(scratch_dir))] = p.read_text()
        except (UnicodeDecodeError, OSError):
            files[str(p.relative_to(scratch_dir))] = "<binary>"
    return files


def _record_turn(response: Any, elapsed: float, trace: Trace) -> None:
    prompt_tokens, completion_tokens, cached_tokens = _extract_usage(response)
    trace.turns.append(
        Turn(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_tokens=cached_tokens,
            latency_s=round(elapsed, 2),
            cost=_extract_cost(response),
            finish_reason=getattr(response.choices[0], "finish_reason", "") or "",
            response_model=getattr(response, "model", "") or "",
        )
    )


def _execute_tool_calls(
    assistant_msg: Message,
    *,
    workspace: Path | None,
    scratch_dir: Path,
    sandbox_fn: SandboxFunc | None,
    trace: Trace,
    messages: list[Message],
) -> Generator[AgentEvent, None, None]:
    for tool_call in assistant_msg["tool_calls"]:
        tool_function = tool_call["function"]
        yield ToolCallEvent(
            name=tool_function["name"],
            arguments=tool_function["arguments"],
        )

        result = execute_tool(
            tool_function["name"],
            tool_function["arguments"],
            workspace=workspace,
            scratch_dir=scratch_dir,
            sandbox_fn=sandbox_fn,
        )
        yield ToolResultEvent(name=tool_function["name"], result=result)

        trace.tool_calls.append(
            {
                "name": tool_function["name"],
                "arguments": tool_function["arguments"],
                "result": result,
            }
        )
        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "content": result,
            }
        )


class StreamedCompletion:
    """Buffer chunks from a streaming LLM response until complete.

    Iterate to get text chunks as they arrive. After iteration finishes,
    access .response for the reconstructed full response with usage metrics.
    This two-phase pattern is necessary because streaming APIs return
    incremental text but we need the aggregated response for telemetry.
    """

    def __init__(self, stream: Any) -> None:
        self._stream = stream
        self._chunks: list[Any] = []
        self.response: Any = None

    def __iter__(self) -> Generator[str, None, None]:
        import litellm

        for chunk in self._stream:
            self._chunks.append(chunk)
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content
        self.response = litellm.stream_chunk_builder(
            self._chunks, messages=None
        )


def _run_loop(
    *,
    model: str,
    messages: list[Message],
    tools: list[ToolDef],
    completion: CompletionFunc,
    workspace: Path | None = None,
    max_turns: int = 30,
    trace: Trace,
    completion_kwargs: dict[str, Any],
    scratch_dir: Path | None = None,
    sandbox_fn: SandboxFunc | None = None,
    stream: bool = False,
) -> Generator[AgentEvent, None, None]:
    completion_kwargs.setdefault(
        "cache_control_injection_points", _DEFAULT_CACHE_INJECTION
    )
    nudged = False
    if scratch_dir is not None:
        active_scratch = scratch_dir
        scratch_ctx = None
    else:
        scratch_ctx = tempfile.TemporaryDirectory(prefix="lh-scratch-")
        active_scratch = Path(scratch_ctx.__enter__())
    try:
        for _ in range(max_turns):
            start = time.monotonic()

            if stream:
                raw_stream = completion(
                    model=model,
                    messages=messages,
                    tools=tools,
                    stream=True,
                    stream_options={"include_usage": True},
                    num_retries=2,
                    **completion_kwargs,
                )
                streamed = StreamedCompletion(raw_stream)
                for text_delta in streamed:
                    yield TextDeltaEvent(content=text_delta)
                response = streamed.response
            else:
                response = completion(
                    model=model,
                    messages=messages,
                    tools=tools,
                    num_retries=2,
                    **completion_kwargs,
                )

            _record_turn(response, time.monotonic() - start, trace)

            assistant_msg = _parse_response_message(response)
            messages.append(assistant_msg)

            if not assistant_msg.get("tool_calls"):
                if _should_nudge(workspace, trace, nudged):
                    nudged = True
                    messages.append(_NUDGE_MESSAGE)
                    continue
                trace.answer = assistant_msg.get("content")
                break

            yield from _execute_tool_calls(
                assistant_msg,
                workspace=workspace,
                scratch_dir=active_scratch,
                sandbox_fn=sandbox_fn,
                trace=trace,
                messages=messages,
            )

        yield ResponseEvent(
            content=trace.answer,
            prompt_tokens=trace.prompt_tokens,
            completion_tokens=trace.completion_tokens,
            cached_tokens=trace.cached_tokens,
            latency_s=trace.latency_s,
            cost=trace.cost,
        )
    finally:
        trace.scratch_files = _snapshot_scratch(active_scratch)
        if scratch_ctx is not None:
            scratch_ctx.__exit__(None, None, None)


def run_agent_loop(
    *,
    model: str,
    messages: list[Message],
    tools: list[ToolDef],
    completion: CompletionFunc,
    workspace: Path | None = None,
    scratch_dir: Path | None = None,
    sandbox_fn: SandboxFunc | None = None,
    max_turns: int = 30,
    stream: bool = False,
    **completion_kwargs: Any,
) -> AgentRun:
    trace = Trace(
        model=model, messages=messages, tools=tools, completion_kwargs=completion_kwargs
    )
    events = _run_loop(
        model=model,
        messages=messages,
        tools=tools,
        completion=completion,
        workspace=workspace,
        scratch_dir=scratch_dir,
        sandbox_fn=sandbox_fn,
        max_turns=max_turns,
        trace=trace,
        completion_kwargs=completion_kwargs,
        stream=stream,
    )
    return AgentRun(events=events, trace=trace)
