"""Render agent traces as HTML strings.

Pure HTML generation with no display dependencies — usable from notebooks,
web apps, or anywhere else that can render HTML.
"""

from __future__ import annotations

import json
from html import escape
from typing import Any

# ---------------------------------------------------------------------------
# Trace viewer color scheme
# ---------------------------------------------------------------------------

COLOR_SYSTEM = "#888"
COLOR_USER = "#36a"
COLOR_ASSISTANT = "#483"
COLOR_TOOL_RESULT = "#986"
COLOR_PASS = "#4a4"
COLOR_FAIL = "#c44"
COLOR_META = "#999"

# ---------------------------------------------------------------------------
# Low-level formatting helpers
# ---------------------------------------------------------------------------


def _format_json(text: str) -> str:
    try:
        return json.dumps(json.loads(text), indent=2)
    except (json.JSONDecodeError, TypeError):
        return text


def _collapsible(
    summary_html: str, body: str, *, open_: bool = False, raw: bool = False
) -> str:
    open_attr = " open" if open_ else ""
    if raw:
        inner = f"<div style='margin:4px 0 4px 16px;'>{body}</div>"
    else:
        inner = (
            f"<pre style='margin:4px 0 4px 16px;font-size:12px;"
            f"color:#555;'>{escape(body)}</pre>"
        )
    return f"<details{open_attr}><summary>{summary_html}</summary>{inner}</details>"


def _truncate(text: str, max_chars: int | None = None) -> str:
    if max_chars is not None and len(text) > max_chars:
        return text[:max_chars] + f"\n... ({len(text) - max_chars} more chars)"
    return text


def _styled(color: str, text: str, bold: bool = True) -> str:
    weight = "font-weight:bold;" if bold else ""
    return f"<span style='color:{color};{weight}'>{text}</span>"


# ---------------------------------------------------------------------------
# Individual message renderers
# ---------------------------------------------------------------------------


def _render_system(content: str) -> str:
    return _collapsible(
        f"{_styled(COLOR_SYSTEM, '[system]')} "
        f"<span style='color:#888;font-size:12px;'>({len(content)} chars)</span>",
        _format_json(content),
    )


def _render_user(content: str) -> str:
    return (
        f"<div style='margin:6px 0;'>"
        f"{_styled(COLOR_USER, '[user]')} {escape(content)}</div>"
    )


def _turn_meta_html(turn: dict[str, Any] | None) -> str:
    if not turn:
        return ""
    parts = []
    prompt = turn.get("prompt_tokens", 0)
    comp = turn.get("completion_tokens", 0)
    cached = turn.get("cached_tokens", 0)
    latency = turn.get("latency_s", 0)
    cost = turn.get("cost")
    finish = turn.get("finish_reason", "")
    resp_model = turn.get("response_model", "")

    token_info = f"{prompt} in"
    if cached:
        token_info += f" ({cached} cached)"
    token_info += f" → {comp} out"
    parts.append(token_info)
    parts.append(f"{latency}s")
    if cost:
        parts.append(f"${cost:.4f}")
    if finish:
        parts.append(finish)
    if resp_model:
        parts.append(resp_model)
    return (
        f"<span style='color:#999;font-size:11px;margin-left:8px;'>"
        f"{' · '.join(parts)}</span>"
    )


def _render_assistant_text(content: str, turn: dict[str, Any] | None = None) -> str:
    meta = _turn_meta_html(turn)
    return _collapsible(
        f"{_styled(COLOR_ASSISTANT, '[assistant]')} ({len(content)} chars){meta}",
        f"<div style='white-space:pre-wrap;'>{escape(content)}</div>",
        open_=True,
        raw=True,
    )


def _render_tool_call(fn: dict[str, Any], turn: dict[str, Any] | None = None) -> str:
    try:
        args = json.loads(fn["arguments"])
    except (json.JSONDecodeError, TypeError):
        args = {}

    meta = _turn_meta_html(turn)

    if fn["name"] == "run_python" and "code" in args:
        return _collapsible(
            f"{_styled(COLOR_ASSISTANT, '[assistant]')} calls "
            f"<code>{escape(fn['name'])}</code>{meta}",
            f"<pre style='font-size:12px;background:#f6f6f6;padding:8px;"
            f"border-radius:4px;'>{escape(args['code'])}</pre>",
            open_=True,
            raw=True,
        )

    return _collapsible(
        f"{_styled(COLOR_ASSISTANT, '[assistant]')} calls "
        f"<code>{escape(fn['name'])}</code>{meta}",
        f"<pre style='font-size:12px;'>{escape(_format_json(fn['arguments']))}</pre>",
        open_=True,
        raw=True,
    )


def _render_assistant(
    content: str, tool_calls: list[dict[str, Any]], turn: dict[str, Any] | None = None
) -> str:
    if tool_calls:
        return "\n".join(_render_tool_call(tc["function"], turn) for tc in tool_calls)
    return _render_assistant_text(content, turn)


def _render_tool_result(content: str, max_chars: int | None) -> str:
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return _collapsible(
            f"{_styled(COLOR_TOOL_RESULT, '[tool result]', bold=False)} {len(content)} chars",
            _truncate(content, max_chars),
        )

    if "error" in data:
        summary = f"error: {data['error']}"
    elif "stdout" in data:
        stdout = data["stdout"].strip()
        exit_code = data.get("exit_code", "?")
        if exit_code == 0:
            summary = (
                f"stdout ({len(stdout)} chars): {stdout}"
                if stdout
                else "ok (no output)"
            )
        else:
            summary = f"exit_code={exit_code}"
    else:
        summary = f"{len(content)} chars"

    # Format body
    parts = []
    if isinstance(data, dict):
        if data.get("stdout", "").strip():
            parts.append(data["stdout"].strip())
        if data.get("stderr", "").strip():
            parts.append(f"[stderr]\n{data['stderr'].strip()}")
        exit_code = data.get("exit_code")
        if exit_code and exit_code != 0:
            parts.append(f"exit_code={exit_code}")
    body = "\n\n".join(parts) if parts else "(no output)"

    return _collapsible(
        f"{_styled(COLOR_TOOL_RESULT, '[tool result]', bold=False)} {escape(summary)}",
        _truncate(body, max_chars),
    )


def _render_message(
    msg: dict[str, Any], max_chars: int | None = None, turn: dict[str, Any] | None = None
) -> str:
    role = msg["role"]
    content = msg.get("content") or ""
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    if role == "system":
        return _render_system(content)
    if role == "user":
        return _render_user(content)
    if role == "assistant":
        return _render_assistant(content, msg.get("tool_calls", []), turn)
    if role == "tool":
        return _render_tool_result(content, max_chars)
    return ""


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------


def _render_telemetry(turns: list[dict[str, Any]], wall_time_s: float) -> str:
    lines = []
    for i, turn in enumerate(turns, 1):
        cached = turn.get("cached_tokens", 0)
        cache_info = f" ({cached} cached)" if cached else ""
        cost = f" | ${turn['cost']:.4f}" if turn.get("cost") else ""
        lines.append(
            f"Turn {i}: {turn['prompt_tokens']} in{cache_info}, "
            f"{turn['completion_tokens']} out, {turn['latency_s']}s{cost}"
        )

    model_time = sum(t.get("latency_s", 0) for t in turns)
    total_cached = sum(t.get("cached_tokens", 0) for t in turns)
    if wall_time_s > 0:
        tool_time = wall_time_s - model_time
        lines.append(
            f"\nTotal: {wall_time_s:.1f}s wall"
            f" = {model_time:.1f}s model + {tool_time:.1f}s tool"
        )
    if total_cached > 0:
        lines.append(f"Cached: {total_cached} tokens")

    return _collapsible(
        "<span style='color:#888;font-size:13px;'>telemetry</span>",
        "\n".join(lines),
    )


def _render_assertions(assertions: dict[str, Any]) -> str:
    parts = []
    for name, ok in assertions.items():
        icon = "\u2713" if ok else "\u2717"
        color = COLOR_PASS if ok else COLOR_FAIL
        parts.append(f"<span style='color:{color};'>{icon}</span> {escape(name)}")
    return "&nbsp;&nbsp;".join(parts)


# ---------------------------------------------------------------------------
# Conversation structure: group messages into questions and turns
# ---------------------------------------------------------------------------


def _build_conversation(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parse messages into a structured conversation.

    Returns a list of blocks. Each block is one of:
      {"type": "system", "idx": int}
      {"type": "question", "idx": int, "text": str,
       "turns": [{"asst_idx": int, "tool_indices": [int]}]}
    """
    blocks: list[dict[str, Any]] = []
    current_question: dict[str, Any] | None = None

    for i, msg in enumerate(messages):
        role = msg["role"]

        if role == "system":
            blocks.append({"type": "system", "idx": i})

        elif role == "user":
            current_question = {
                "type": "question",
                "idx": i,
                "text": (msg.get("content") or "")[:100],
                "turns": [],
            }
            blocks.append(current_question)

        elif role == "assistant":
            turn = {"asst_idx": i, "tool_indices": []}
            if current_question is not None:
                current_question["turns"].append(turn)
            else:
                # Assistant without a preceding user message (shouldn't happen)
                current_question = {
                    "type": "question",
                    "idx": i,
                    "text": "(no user message)",
                    "turns": [turn],
                }
                blocks.append(current_question)

        elif (
            role == "tool"
            and current_question is not None
            and current_question["turns"]
        ):
            current_question["turns"][-1]["tool_indices"].append(i)

    return blocks


# ---------------------------------------------------------------------------
# Render a question block (user message + turns)
# ---------------------------------------------------------------------------


def _render_question_block(
    messages: list[dict[str, Any]],
    question: dict[str, Any],
    max_chars: int | None,
    asst_to_turn: dict[int, dict[str, Any]] | None = None,
    open_: bool = True,
) -> str:
    """Render a question block: user message header with assistant/tool messages inside."""
    inner_parts = []
    for turn in question["turns"]:
        asst_idx = turn["asst_idx"]
        asst_msg = messages[asst_idx]
        turn_meta = (asst_to_turn or {}).get(asst_idx)
        inner_parts.append(
            "<div style='border-left:3px solid #483;padding-left:12px;margin:4px 0;'>"
        )
        inner_parts.append(_render_message(asst_msg, max_chars, turn_meta))
        inner_parts.extend(
            _render_message(messages[tool_idx], max_chars)
            for tool_idx in turn["tool_indices"]
        )
        inner_parts.append("</div>")

    user_content = messages[question["idx"]].get("content") or ""
    body = (
        "\n".join(inner_parts)
        if inner_parts
        else "<div style='color:#888;'>(no response)</div>"
    )
    return _collapsible(
        f"{_styled(COLOR_USER, '[user]')} {escape(user_content)}",
        body,
        open_=open_,
        raw=True,
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def render_trace(data: dict[str, Any], max_chars: int | None = None) -> str:
    """Render a full agent trace as an HTML string."""
    inner = data.get("trace", data)
    tool_calls = inner.get("tool_calls", [])
    messages = inner.get("messages", [])
    turns = inner.get("turns", [])
    tools = inner.get("tools", [])
    offset = inner.get("message_offset", 0)

    parts = []

    # Header: badge + question + stats
    passed = data.get("passed", False)
    badge_color = COLOR_PASS if passed else "#c44"
    badge_text = "PASS" if passed else "FAIL"
    parts.append(
        f"<div style='margin-bottom:12px;'>"
        f"<span style='background:{badge_color};color:white;padding:2px 8px;"
        f"border-radius:3px;font-size:12px;font-weight:bold;'>"
        f"{badge_text}</span>"
        f"&nbsp;&nbsp;<b>{escape(data['question'])}</b>"
        f"&nbsp;&nbsp;<span style='color:#888;font-size:13px;'>"
        f"{len(tool_calls)} tool calls, {len(turns)} turns</span></div>"
    )

    # Assertions
    if data.get("assertions"):
        parts.append(
            f"<div style='margin-bottom:8px;font-size:13px;'>"
            f"{_render_assertions(data['assertions'])}</div>"
        )

    # Telemetry
    if turns:
        parts.append(_render_telemetry(turns, inner.get("wall_time_s", 0)))

    # Error
    if inner.get("error"):
        parts.append(
            f"<div style='color:#c44;margin:8px 0;'>"
            f"Error: {escape(inner['error'])}</div>"
        )

    if not messages:
        parts.append("<div style='color:#888;'>No messages in trace</div>")
        return "\n".join(parts)

    # Parse conversation structure
    blocks = _build_conversation(messages)

    # Map assistant message indices to turn metadata.
    # Turns are 1:1 with assistant messages in chronological order.
    asst_indices = [i for i, m in enumerate(messages) if m["role"] == "assistant"]
    turn_dicts = [
        {
            "prompt_tokens": t.get("prompt_tokens", 0),
            "completion_tokens": t.get("completion_tokens", 0),
            "cached_tokens": t.get("cached_tokens", 0),
            "latency_s": t.get("latency_s", 0),
            "cost": t.get("cost"),
            "finish_reason": t.get("finish_reason", ""),
            "response_model": t.get("response_model", ""),
        }
        if isinstance(t, dict)
        else {
            "prompt_tokens": getattr(t, "prompt_tokens", 0),
            "completion_tokens": getattr(t, "completion_tokens", 0),
            "cached_tokens": getattr(t, "cached_tokens", 0),
            "latency_s": getattr(t, "latency_s", 0),
            "cost": getattr(t, "cost", None),
            "finish_reason": getattr(t, "finish_reason", ""),
            "response_model": getattr(t, "response_model", ""),
        }
        for t in turns
    ]
    asst_to_turn: dict[int, dict[str, Any]] = dict(
        zip(asst_indices[-len(turn_dicts) :], turn_dicts, strict=False)
    )

    # Split into prior (before offset) and own (from offset onward)
    prior_blocks = [b for b in blocks if b.get("idx", 0) < offset]
    own_blocks = [b for b in blocks if b.get("idx", 0) >= offset]

    # System message at top (from prior or own)
    for b in blocks:
        if b["type"] == "system":
            parts.append(_render_system(messages[b["idx"]].get("content") or ""))
            break

    # Tool definitions
    if tools:
        names = [t.get("function", {}).get("name", "?") for t in tools]
        parts.append(
            _collapsible(
                f"<span style='color:#888;font-size:13px;'>"
                f"{len(tools)} tool definitions: {', '.join(names)}</span>",
                json.dumps(tools, indent=2),
            )
        )

    # Prior session questions (cached, collapsed)
    prior_questions = [b for b in prior_blocks if b["type"] == "question"]
    if prior_questions:
        prior_parts = [
            _render_question_block(messages, q, max_chars, asst_to_turn, open_=False)
            for q in prior_questions
        ]
        parts.append(
            _collapsible(
                f"<span style='color:#888;font-size:13px;'>"
                f"cached session context ({len(prior_questions)} questions)</span>",
                "\n".join(prior_parts),
                raw=True,
            )
        )

    # This question's blocks (open)
    own_questions = [b for b in own_blocks if b["type"] == "question"]
    parts.extend(
        _render_question_block(messages, q, max_chars, asst_to_turn, open_=True)
        for q in own_questions
    )

    # Raw messages JSON
    raw_json = json.dumps(messages, indent=2, default=str)
    parts.append(
        _collapsible(
            "<span style='color:#888;font-size:13px;'>raw messages JSON</span>",
            raw_json,
        )
    )

    return "\n".join(parts)
