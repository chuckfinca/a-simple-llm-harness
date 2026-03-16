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
    summary_html: str, detail_text: str, open_: bool = False
) -> str:
    open_attr = " open" if open_ else ""
    return (
        f"<details{open_attr}><summary>{summary_html}</summary>"
        f"<pre style='margin:4px 0 8px 16px;font-size:12px;"
        f"color:#555;'>{escape(detail_text)}</pre></details>"
    )


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
            preview = stdout[:80] + ("..." if len(stdout) > 80 else "")
            return (
                f"stdout ({len(stdout)} chars): {preview}"
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
        parts.append(
            f"<span style='color:{color};'>{icon}</span> {escape(name)}"
        )
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


def _render_cached(
    messages: list[dict], tools: list[dict] | None = None
) -> str:
    if not messages and not tools:
        return ""
    summary_parts = []
    if messages:
        summary_parts.append(f"{len(messages)} cached messages")
    if tools:
        summary_parts.append(f"{len(tools)} tool defs")

    lines = []
    if tools:
        lines.append(f"[tools] {', '.join(_tool_def_names(tools))}")
    for m in messages:
        role = m["role"]
        content = m.get("content") or ""
        tool_calls = m.get("tool_calls", [])
        if role == "system":
            lines.append(f"[system] ({len(content)} chars)")
        elif role == "user":
            lines.append(f"[user] {content[:100]}")
        elif role == "assistant":
            if tool_calls:
                names = ", ".join(
                    tc["function"]["name"] for tc in tool_calls
                )
                lines.append(f"[assistant] calls {names}")
            else:
                lines.append(f"[assistant] ({len(content)} chars)")
        elif role == "tool":
            lines.append(f"[tool result] ({len(content)} chars)")

    return _collapsible(
        f"<span style='color:#888;font-size:13px;'>"
        f"{' + '.join(summary_parts)}</span>",
        "\n".join(lines),
    )


def _render_message(
    m: dict,
    max_chars: int | None = None,
    trace_tool_calls: list[dict] | None = None,
) -> str:
    role = m["role"]
    content = m.get("content") or ""
    tool_calls = m.get("tool_calls", [])

    if role == "system":
        formatted = _format_json(content)
        if max_chars is not None:
            formatted = formatted[:max_chars]
        return _collapsible(
            f"<span style='color:#888;'>[system]</span>"
            f" <span style='color:#888;font-size:12px;'>"
            f"({len(content)} chars)</span>",
            formatted,
        )

    if role == "user":
        return (
            f"<div style='margin:8px 0;'>"
            f"<b style='color:#36a;'>[user]</b> {escape(content)}</div>"
        )

    if role == "assistant":
        if tool_calls:
            parts = []
            for tc in tool_calls:
                fn = tc["function"]
                try:
                    args_parsed = json.loads(fn["arguments"])
                except (json.JSONDecodeError, TypeError):
                    args_parsed = {}

                if fn["name"] == "run_python" and "code" in args_parsed:
                    code_html = escape(args_parsed["code"])
                    parts.append(
                        f"<div style='margin:4px 0;'>"
                        f"<b style='color:#483;'>[assistant]</b> calls "
                        f"<code>{escape(fn['name'])}</code>"
                        f"<pre style='margin:2px 0 4px 16px;font-size:12px;"
                        f"background:#f6f6f6;padding:8px;"
                        f"border-radius:4px;'>{code_html}</pre></div>"
                    )
                else:
                    args = _format_json(fn["arguments"])
                    parts.append(
                        f"<div style='margin:4px 0;'>"
                        f"<b style='color:#483;'>[assistant]</b> calls "
                        f"<code>{escape(fn['name'])}</code>"
                        f"<pre style='margin:2px 0 4px 16px;"
                        f"font-size:12px;'>{escape(args)}</pre></div>"
                    )
            return "\n".join(parts)

        return (
            f"<div style='margin:8px 0;'>"
            f"<b style='color:#483;'>[assistant]</b>"
            f" ({len(content)} chars)"
            f"<div style='margin:4px 0 8px 16px;"
            f"white-space:pre-wrap;'>{escape(content)}</div></div>"
        )

    if role == "tool":
        summary = _tool_result_summary(content)
        formatted = _format_json(content)
        if max_chars is not None and len(formatted) > max_chars:
            formatted = (
                formatted[:max_chars]
                + f"\n... ({len(formatted) - max_chars} more chars)"
            )
        return _collapsible(
            f"<span style='color:#986;'>[tool result]</span>"
            f" {escape(summary)}",
            formatted,
        )

    return ""


def show_trace(data: dict, max_chars: int | None = None) -> None:
    """Render a full agent trace as HTML in Jupyter."""
    inner = data.get("trace", data)
    tool_calls = inner.get("tool_calls", [])
    messages = inner.get("messages", [])
    turns = inner.get("turns", [])
    tools = inner.get("tools", [])

    parts = []

    # Header
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

    # Per-turn telemetry
    if turns:
        telem_lines = []
        for i, t in enumerate(turns, 1):
            cost = f" | ${t['cost']:.4f}" if t.get("cost") else ""
            telem_lines.append(
                f"Turn {i}: {t['prompt_tokens']} in, "
                f"{t['completion_tokens']} out, {t['latency_s']}s{cost}"
            )

        model_time = sum(t.get("latency_s", 0) for t in turns)
        wall_time = inner.get("wall_time_s", 0)
        if wall_time > 0:
            tool_time = wall_time - model_time
            telem_lines.append(
                f"\nTotal: {wall_time:.1f}s wall"
                f" = {model_time:.1f}s model + {tool_time:.1f}s tool"
            )

        parts.append(
            _collapsible(
                "<span style='color:#888;font-size:13px;'>telemetry</span>",
                "\n".join(telem_lines),
            )
        )

    # Error
    if inner.get("error"):
        parts.append(
            f"<div style='color:#c44;margin:8px 0;'>"
            f"Error: {escape(inner['error'])}</div>"
        )

    # Conversation turns
    if messages:
        asst_indices = [
            i for i, m in enumerate(messages) if m["role"] == "assistant"
        ]
        prev_end = 0

        for turn_num, asst_idx in enumerate(asst_indices, 1):
            # Find end of this turn (after tool results)
            turn_end = asst_idx + 1
            while (
                turn_end < len(messages)
                and messages[turn_end]["role"] == "tool"
            ):
                turn_end += 1

            parts.append(
                f"<div style='border-top:2px solid #ddd;margin-top:16px;"
                f"padding-top:8px;'>"
                f"<span style='font-size:13px;color:#888;'>"
                f"Turn {turn_num}</span></div>"
            )

            if prev_end == 0:
                parts.append(_render_tools(tools))
                parts.append(_render_cached(messages[:prev_end]))
            else:
                parts.append(
                    _render_cached(messages[:prev_end], tools=tools)
                )

            parts.extend(
                _render_message(messages[i], max_chars, tool_calls)
                for i in range(prev_end, asst_idx)
            )

            parts.append(
                "<div style='border-left:3px solid #483;"
                "padding-left:12px;margin:8px 0;'>"
            )
            parts.append(
                _render_message(messages[asst_idx], max_chars, tool_calls)
            )
            parts.extend(
                _render_message(messages[i], max_chars, tool_calls)
                for i in range(asst_idx + 1, turn_end)
            )
            parts.append("</div>")

            prev_end = turn_end
    else:
        parts.append(
            "<div style='color:#888;'>No messages in trace</div>"
        )

    display(HTML("\n".join(parts)))
