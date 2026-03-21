"""Trace rendering utilities for Jupyter notebooks."""

from __future__ import annotations

import json
from html import escape

from IPython.display import HTML, display


def _format_json(text: str) -> str:
    try:
        return json.dumps(json.loads(text), indent=2)
    except (json.JSONDecodeError, TypeError):
        return text


def _collapsible(
    summary_html: str, detail_text: str, open_: bool = False, raw_html: bool = False
) -> str:
    open_attr = " open" if open_ else ""
    if raw_html:
        body = f"<div style='margin:4px 0 8px 16px;'>{detail_text}</div>"
    else:
        body = (
            f"<pre style='margin:4px 0 8px 16px;font-size:12px;"
            f"color:#555;'>{escape(detail_text)}</pre>"
        )
    return f"<details{open_attr}><summary>{summary_html}</summary>{body}</details>"


def _format_tool_result(text: str, max_chars: int | None = None) -> str:
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return _truncate(text, max_chars)

    if not isinstance(data, dict) or "stdout" not in data:
        return _truncate(_format_json(text), max_chars)

    parts = []
    if data.get("stdout", "").strip():
        parts.append(data["stdout"].strip())
    if data.get("stderr", "").strip():
        parts.append(f"[stderr]\n{data['stderr'].strip()}")
    exit_code = data.get("exit_code")
    if exit_code and exit_code != 0:
        parts.append(f"exit_code={exit_code}")

    result = "\n\n".join(parts) if parts else "(no output)"
    return _truncate(result, max_chars)


def _truncate(text: str, max_chars: int | None = None) -> str:
    if max_chars is not None and len(text) > max_chars:
        return text[:max_chars] + f"\n... ({len(text) - max_chars} more chars)"
    return text


def _tool_result_summary(text: str) -> str:
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return f"{len(text)} chars"
    if "error" in data:
        return f"error: {data['error']}"
    if "stdout" in data:
        stdout = data["stdout"].strip()
        exit_code = data.get("exit_code", "?")
        if exit_code == 0:
            return (
                f"stdout ({len(stdout)} chars): {stdout}"
                if stdout
                else "ok (no output)"
            )
        return f"exit_code={exit_code}"
    return f"{len(text)} chars"


def _render_assertions(assertions: dict) -> str:
    parts = []
    for name, ok in assertions.items():
        icon = "✓" if ok else "✗"
        color = "#4a4" if ok else "#c44"
        parts.append(f"<span style='color:{color};'>{icon}</span> {escape(name)}")
    return "&nbsp;&nbsp;".join(parts)


def _tool_def_names(tools: list[dict]) -> list[str]:
    return [t.get("function", {}).get("name", "?") for t in tools]


def _render_tools(tools: list[dict]) -> str:
    if not tools:
        return ""
    names = _tool_def_names(tools)
    return _collapsible(
        f"<span style='color:#888;font-size:13px;'>"
        f"{len(tools)} tool definitions: {', '.join(names)}</span>",
        json.dumps(tools, indent=2),
    )


def _render_system_message(content: str, max_chars: int | None) -> str:
    formatted = _format_json(content)
    return _collapsible(
        f"<span style='color:#888;'>[system]</span>"
        f" <span style='color:#888;font-size:12px;'>"
        f"({len(content)} chars)</span>",
        formatted,
    )


def _render_user_message(content: str) -> str:
    return (
        f"<div style='margin:8px 0;'>"
        f"<b style='color:#36a;'>[user]</b> {escape(content)}</div>"
    )


def _render_tool_call(fn: dict) -> str:
    try:
        args_parsed = json.loads(fn["arguments"])
    except (json.JSONDecodeError, TypeError):
        args_parsed = {}

    if fn["name"] == "run_python" and "code" in args_parsed:
        code_html = escape(args_parsed["code"])
        return (
            f"<div style='margin:4px 0;'>"
            f"<b style='color:#483;'>[assistant]</b> calls "
            f"<code>{escape(fn['name'])}</code>"
            f"<pre style='margin:2px 0 4px 16px;font-size:12px;"
            f"background:#f6f6f6;padding:8px;"
            f"border-radius:4px;'>{code_html}</pre></div>"
        )

    args = _format_json(fn["arguments"])
    return (
        f"<div style='margin:4px 0;'>"
        f"<b style='color:#483;'>[assistant]</b> calls "
        f"<code>{escape(fn['name'])}</code>"
        f"<pre style='margin:2px 0 4px 16px;"
        f"font-size:12px;'>{escape(args)}</pre></div>"
    )


def _render_assistant_message(content: str, tool_calls: list[dict]) -> str:
    if tool_calls:
        return "\n".join(_render_tool_call(tc["function"]) for tc in tool_calls)
    return (
        f"<div style='margin:8px 0;'>"
        f"<b style='color:#483;'>[assistant]</b>"
        f" ({len(content)} chars)"
        f"<div style='margin:4px 0 8px 16px;"
        f"white-space:pre-wrap;'>{escape(content)}</div></div>"
    )


def _render_tool_result_message(content: str, max_chars: int | None) -> str:
    summary = _tool_result_summary(content)
    formatted = _format_tool_result(content, max_chars)
    return _collapsible(
        f"<span style='color:#986;'>[tool result]</span> {escape(summary)}",
        formatted,
    )


_MESSAGE_RENDERERS = {
    "system": lambda m, mc, _tc: _render_system_message(m.get("content") or "", mc),
    "user": lambda m, _mc, _tc: _render_user_message(m.get("content") or ""),
    "assistant": lambda m, _mc, _tc: _render_assistant_message(
        m.get("content") or "", m.get("tool_calls", [])
    ),
    "tool": lambda m, mc, _tc: _render_tool_result_message(m.get("content") or "", mc),
}


def _render_message(
    m: dict,
    max_chars: int | None = None,
    trace_tool_calls: list[dict] | None = None,
) -> str:
    renderer = _MESSAGE_RENDERERS.get(m["role"])
    return renderer(m, max_chars, trace_tool_calls) if renderer else ""


def _render_turn_body(
    *,
    messages: list[dict],
    asst_idx: int,
    turn_end: int,
    prev_end: int,
    tool_calls: list[dict],
    max_chars: int | None,
) -> list[str]:
    """Render user message, assistant action, and tool results for one turn."""
    parts = []
    parts.extend(
        _render_message(messages[i], max_chars, tool_calls)
        for i in range(prev_end, asst_idx)
        if messages[i]["role"] != "system"  # system shown at top
    )
    parts.append(
        "<div style='border-left:3px solid #483;padding-left:12px;margin:8px 0;'>"
    )
    parts.append(_render_message(messages[asst_idx], max_chars, tool_calls))
    parts.extend(
        _render_message(messages[i], max_chars, tool_calls)
        for i in range(asst_idx + 1, turn_end)
    )
    parts.append("</div>")
    return parts


def _render_telemetry(turns: list[dict], wall_time_s: float) -> str:
    telem_lines = []
    for i, t in enumerate(turns, 1):
        cached = t.get("cached_tokens", 0)
        cache_info = f" ({cached} cached)" if cached else ""
        cost = f" | ${t['cost']:.4f}" if t.get("cost") else ""
        telem_lines.append(
            f"Turn {i}: {t['prompt_tokens']} in{cache_info}, "
            f"{t['completion_tokens']} out, {t['latency_s']}s{cost}"
        )

    model_time = sum(t.get("latency_s", 0) for t in turns)
    total_cached = sum(t.get("cached_tokens", 0) for t in turns)
    if wall_time_s > 0:
        tool_time = wall_time_s - model_time
        telem_lines.append(
            f"\nTotal: {wall_time_s:.1f}s wall"
            f" = {model_time:.1f}s model + {tool_time:.1f}s tool"
        )
    if total_cached > 0:
        telem_lines.append(f"Cached: {total_cached} tokens")

    return _collapsible(
        "<span style='color:#888;font-size:13px;'>telemetry</span>",
        "\n".join(telem_lines),
    )


def _group_turns_by_question(
    messages: list[dict], asst_indices: list[int]
) -> list[tuple[str, list[tuple[int, int]]]]:
    """Group assistant turn indices by their preceding user question.

    Returns list of (question_text, [(asst_idx, turn_end), ...]).
    """
    groups: list[tuple[str, list[tuple[int, int]]]] = []
    current_question = ""

    for asst_idx in asst_indices:
        # Find the most recent user message before this assistant turn
        for j in range(asst_idx - 1, -1, -1):
            if messages[j]["role"] == "user":
                q = (messages[j].get("content") or "")[:80]
                if q != current_question:
                    current_question = q
                    groups.append((current_question, []))
                break

        turn_end = asst_idx + 1
        while turn_end < len(messages) and messages[turn_end]["role"] == "tool":
            turn_end += 1

        if groups:
            groups[-1][1].append((asst_idx, turn_end))

    return groups


def _render_prior_session(
    messages: list[dict],
    prior_asst: list[int],
    tool_calls: list[dict],
    max_chars: int | None,
) -> str:
    """Render prior session turns as nested collapsibles grouped by question."""
    question_groups = _group_turns_by_question(messages, prior_asst)
    prior_inner = []
    global_turn = 0
    for question_text, turn_pairs in question_groups:
        q_turns = []
        prev = turn_pairs[0][0]
        for j in range(prev - 1, -1, -1):
            if messages[j]["role"] == "user":
                prev = j
                break
        for asst_idx, turn_end in turn_pairs:
            global_turn += 1
            body = "\n".join(
                _render_turn_body(
                    messages=messages,
                    asst_idx=asst_idx,
                    turn_end=turn_end,
                    prev_end=prev,
                    tool_calls=tool_calls,
                    max_chars=max_chars,
                )
            )
            q_turns.append(
                _collapsible(
                    f"<span style='color:#888;font-size:13px;'>"
                    f"Turn {global_turn}</span>",
                    body,
                    raw_html=True,
                )
            )
            prev = turn_end

        label = f"{question_text}..." if len(question_text) == 80 else question_text
        prior_inner.append(
            _collapsible(
                f"<span style='color:#888;font-size:13px;'>"
                f"{escape(label)}"
                f" ({len(turn_pairs)} turns)</span>",
                "\n".join(q_turns),
                raw_html=True,
            )
        )

    return _collapsible(
        f"<span style='color:#888;font-size:13px;'>"
        f"{len(prior_asst)} cached turns from session</span>",
        "\n".join(prior_inner),
        raw_html=True,
    )


def show_trace(data: dict, max_chars: int | None = None) -> None:
    """Render a full agent trace as HTML in Jupyter."""
    inner = data.get("trace", data)
    tool_calls = inner.get("tool_calls", [])
    messages = inner.get("messages", [])
    turns = inner.get("turns", [])
    tools = inner.get("tools", [])

    parts = []

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

    if data.get("assertions"):
        parts.append(
            f"<div style='margin-bottom:8px;font-size:13px;'>"
            f"{_render_assertions(data['assertions'])}</div>"
        )

    if turns:
        parts.append(_render_telemetry(turns, inner.get("wall_time_s", 0)))

    if inner.get("error"):
        parts.append(
            f"<div style='color:#c44;margin:8px 0;'>"
            f"Error: {escape(inner['error'])}</div>"
        )

    if not messages:
        parts.append("<div style='color:#888;'>No messages in trace</div>")
        display(HTML("\n".join(parts)))
        return

    offset = inner.get("message_offset", 0)
    all_asst = [i for i, m in enumerate(messages) if m["role"] == "assistant"]
    prior_asst = [i for i in all_asst if i < offset]
    own_asst = [i for i in all_asst if i >= offset]

    # System message and tools shown once at top, outside turns
    if messages and messages[0]["role"] == "system":
        parts.append(_render_system_message(messages[0].get("content") or "", None))
    if tools:
        parts.append(_render_tools(tools))

    # Prior session turns (cached, grouped by question)
    if prior_asst:
        parts.append(_render_prior_session(messages, prior_asst, tool_calls, max_chars))

    # This question's turns (collapsible, open by default)
    turn_offset = len(prior_asst)
    prev_end = offset
    for i, asst_idx in enumerate(own_asst):
        turn_num = turn_offset + i + 1
        turn_end = asst_idx + 1
        while turn_end < len(messages) and messages[turn_end]["role"] == "tool":
            turn_end += 1

        body = "\n".join(
            _render_turn_body(
                messages=messages,
                asst_idx=asst_idx,
                turn_end=turn_end,
                prev_end=prev_end,
                tool_calls=tool_calls,
                max_chars=max_chars,
            )
        )
        parts.append(
            _collapsible(
                f"<span style='color:#888;font-size:13px;'>Turn {turn_num}</span>",
                body,
                open_=True,
                raw_html=True,
            )
        )
        prev_end = turn_end

    # Raw messages JSON for prompt debugging
    raw_json = json.dumps(messages, indent=2, default=str)
    parts.append(
        _collapsible(
            "<span style='color:#888;font-size:13px;'>raw messages JSON</span>",
            raw_json,
        )
    )

    display(HTML("\n".join(parts)))
