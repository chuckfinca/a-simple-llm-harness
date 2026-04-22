"""HTML primitives for collapsible block-style UIs.

Small, neutral helpers used by trace_viewer to build <details>/<summary>
trees. No LLM-specific concepts and no tree data model — callers
compose strings directly. Pure HTML output, no JS, no dependencies.
"""

from __future__ import annotations

import json
from html import escape

# Neutral colors usable across any block-style UI.
COLOR_OK = "#4a4"
COLOR_FAIL = "#c44"
COLOR_META = "#999"
COLOR_MUTED = "#888"


def format_json(text: str) -> str:
    """Pretty-print a JSON string; return text unchanged if it isn't JSON."""
    try:
        return json.dumps(json.loads(text), indent=2)
    except (json.JSONDecodeError, TypeError):
        return text


def truncate(text: str, max_chars: int | None = None) -> str:
    if max_chars is not None and len(text) > max_chars:
        return text[:max_chars] + f"\n... ({len(text) - max_chars} more chars)"
    return text


def styled(color: str, text: str, bold: bool = True) -> str:
    weight = "font-weight:bold;" if bold else ""
    return f"<span style='color:{color};{weight}'>{text}</span>"


def collapsible(
    summary_html: str, body_html: str, *, open_: bool = False, body_is_html: bool = False
) -> str:
    """Render a single <details>/<summary> element.

    `body_is_html=True` inserts `body_html` verbatim inside a div.
    `body_is_html=False` treats it as text: escapes and wraps in <pre>.
    """
    open_attr = " open" if open_ else ""
    if body_is_html:
        inner = f"<div style='margin:4px 0 4px 16px;'>{body_html}</div>"
    else:
        inner = (
            f"<pre style='margin:4px 0 4px 16px;font-size:12px;"
            f"color:#555;'>{escape(body_html)}</pre>"
        )
    return f"<details{open_attr}><summary>{summary_html}</summary>{inner}</details>"
