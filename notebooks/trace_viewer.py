"""Thin notebook wrapper — display logic only, rendering lives in the package."""

from __future__ import annotations

from IPython.display import HTML, display

from llm_harness.trace_viewer import render_trace

__all__ = ["render_trace", "show_trace"]


def show_trace(data: dict, max_chars: int | None = None) -> None:
    """Render a full agent trace as HTML in Jupyter."""
    display(HTML(render_trace(data, max_chars)))
