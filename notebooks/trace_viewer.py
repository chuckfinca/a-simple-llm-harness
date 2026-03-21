"""Trace rendering utilities for Jupyter notebooks."""

from __future__ import annotations

import json
from html import escape

from IPython.display import HTML, display

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
        f"{_styled('#888', '[system]')} "
        f"<span style='color:#888;font-size:12px;'>({len(content)} chars)</span>",
        _format_json(content),
    )


def _render_user(content: str) -> str:
    return (
        f"<div style='margin:6px 0;'>"
        f"{_styled('#36a', '[user]')} {escape(content)}</div>"
    )


def _render_assistant_text(content: str) -> str:
    return (
        f"<div style='margin:6px 0;'>"
        f"{_styled('#483', '[assistant]')} ({len(content)} chars)"
        f"<div style='margin:4px 0 8px 16px;"
        f"white-space:pre-wrap;'>{escape(content)}</div></div>"
    )


def _render_tool_call(fn: dict) -> str:
    try:
        args = json.loads(fn["arguments"])
    except (json.JSONDecodeError, TypeError):
        args = {}

    if fn["name"] == "run_python" and "code" in args:
        return (
            f"<div style='margin:4px 0;'>"
            f"{_styled('#483', '[assistant]')} calls "
            f"<code>{escape(fn['name'])}</code>"
            f"<pre style='margin:2px 0 4px 16px;font-size:12px;"
            f"background:#f6f6f6;padding:8px;"
            f"border-radius:4px;'>{escape(args['code'])}</pre></div>"
        )

    return (
        f"<div style='margin:4px 0;'>"
        f"{_styled('#483', '[assistant]')} calls "
        f"<code>{escape(fn['name'])}</code>"
        f"<pre style='margin:2px 0 4px 16px;"
        f"font-size:12px;'>{escape(_format_json(fn['arguments']))}</pre></div>"
    )


def _render_assistant(content: str, tool_calls: list[dict]) -> str:
    if tool_calls:
        return "\n".join(_render_tool_call(tc["function"]) for tc in tool_calls)
    return _render_assistant_text(content)


def _render_tool_result(content: str, max_chars: int | None) -> str:
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return _collapsible(
            f"{_styled('#986', '[tool result]', bold=False)} {len(content)} chars",
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
        f"{_styled('#986', '[tool result]', bold=False)} {escape(summary)}",
        _truncate(body, max_chars),
    )


def _render_message(msg: dict, max_chars: int | None = None) -> str:
    role = msg["role"]
    content = msg.get("content") or ""
    if role == "system":
        return _render_system(content)
    if role == "user":
        return _render_user(content)
    if role == "assistant":
        return _render_assistant(content, msg.get("tool_calls", []))
    if role == "tool":
        return _render_tool_result(content, max_chars)
    return ""


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------


def _render_telemetry(turns: list[dict], wall_time_s: float) -> str:
    lines = []
    for i, t in enumerate(turns, 1):
        cached = t.get("cached_tokens", 0)
        cache_info = f" ({cached} cached)" if cached else ""
        cost = f" | ${t['cost']:.4f}" if t.get("cost") else ""
        lines.append(
            f"Turn {i}: {t['prompt_tokens']} in{cache_info}, "
            f"{t['completion_tokens']} out, {t['latency_s']}s{cost}"
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


def _render_assertions(assertions: dict) -> str:
    parts = []
    for name, ok in assertions.items():
        icon = "✓" if ok else "✗"
        color = "#4a4" if ok else "#c44"
        parts.append(f"<span style='color:{color};'>{icon}</span> {escape(name)}")
    return "&nbsp;&nbsp;".join(parts)


# ---------------------------------------------------------------------------
# Conversation structure: group messages into questions and turns
# ---------------------------------------------------------------------------


def _build_conversation(messages: list[dict]) -> list[dict]:
    """Parse messages into a structured conversation.

    Returns a list of blocks. Each block is one of:
      {"type": "system", "idx": int}
      {"type": "question", "idx": int, "text": str,
       "turns": [{"asst_idx": int, "tool_indices": [int]}]}
    """
    blocks: list[dict] = []
    current_question: dict | None = None

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
    messages: list[dict],
    question: dict,
    turn_offset: int,
    max_chars: int | None,
    open_: bool = True,
) -> tuple[str, int]:
    """Render a question block. Returns (html, number_of_turns)."""
    turn_parts = []
    for local_num, turn in enumerate(question["turns"]):
        global_num = turn_offset + local_num + 1
        asst_idx = turn["asst_idx"]
        asst_msg = messages[asst_idx]

        # Render assistant message + tool results
        inner_parts = []
        inner_parts.append(
            "<div style='border-left:3px solid #483;padding-left:12px;margin:4px 0;'>"
        )
        inner_parts.append(_render_message(asst_msg, max_chars))
        inner_parts.extend(
            _render_message(messages[tool_idx], max_chars)
            for tool_idx in turn["tool_indices"]
        )
        inner_parts.append("</div>")

        # Make a summary for the turn collapsible
        tool_calls = asst_msg.get("tool_calls", [])
        if tool_calls:
            fn_names = ", ".join(tc["function"]["name"] for tc in tool_calls)
            turn_summary = f"calls {fn_names}"
        else:
            content = asst_msg.get("content") or ""
            turn_summary = f"response ({len(content)} chars)"

        turn_parts.append(
            _collapsible(
                f"<span style='color:#888;font-size:13px;'>"
                f"Turn {global_num}: {turn_summary}</span>",
                "\n".join(inner_parts),
                open_=open_,
                raw=True,
            )
        )

    # User message as question header
    user_text = question["text"]
    label = f"{user_text}..." if len(user_text) == 100 else user_text
    n_turns = len(question["turns"])
    turn_info = f" ({n_turns} turn{'s' if n_turns != 1 else ''})"

    body = (
        "\n".join(turn_parts)
        if turn_parts
        else "<div style='color:#888;'>(no response)</div>"
    )
    html = _collapsible(
        f"{_styled('#36a', '[user]')} {escape(label)}"
        f"<span style='color:#888;font-size:12px;'>{turn_info}</span>",
        body,
        open_=open_,
        raw=True,
    )
    return html, n_turns


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def show_trace(data: dict, max_chars: int | None = None) -> None:
    """Render a full agent trace as HTML in Jupyter."""
    inner = data.get("trace", data)
    tool_calls = inner.get("tool_calls", [])
    messages = inner.get("messages", [])
    turns = inner.get("turns", [])
    tools = inner.get("tools", [])
    offset = inner.get("message_offset", 0)

    parts = []

    # Header: badge + question + stats
    passed = data.get("passed", False)
    badge_color = "#4a4" if passed else "#c44"
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
        display(HTML("\n".join(parts)))
        return

    # Parse conversation structure
    blocks = _build_conversation(messages)

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
        prior_parts = []
        turn_count = 0
        for q in prior_questions:
            html, n = _render_question_block(
                messages, q, turn_count, max_chars, open_=False
            )
            prior_parts.append(html)
            turn_count += n

        total_prior_turns = sum(len(q["turns"]) for q in prior_questions)
        parts.append(
            _collapsible(
                f"<span style='color:#888;font-size:13px;'>"
                f"{total_prior_turns} cached turns from session "
                f"({len(prior_questions)} questions)</span>",
                "\n".join(prior_parts),
                raw=True,
            )
        )
    else:
        turn_count = 0

    # This question's blocks (open)
    own_questions = [b for b in own_blocks if b["type"] == "question"]
    for q in own_questions:
        html, n = _render_question_block(messages, q, turn_count, max_chars, open_=True)
        parts.append(html)
        turn_count += n

    # Raw messages JSON
    raw_json = json.dumps(messages, indent=2, default=str)
    parts.append(
        _collapsible(
            "<span style='color:#888;font-size:13px;'>raw messages JSON</span>",
            raw_json,
        )
    )

    display(HTML("\n".join(parts)))
