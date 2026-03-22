"""Web interface for exploring document workspaces with an LLM agent.

Usage:
    uv run python app.py

Requires LH_MODEL and LH_ACCESS_TOKEN in .env or environment.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from dataclasses import asdict
from pathlib import Path

import gradio as gr
import litellm
from dotenv import load_dotenv

# Add notebooks/ to path so we can import trace_viewer
sys.path.insert(0, str(Path(__file__).parent / "notebooks"))

from trace_viewer import render_trace

from llm_harness.agent import run_agent_loop
from llm_harness.prompt import build_system_prompt
from llm_harness.tools import TOOL_DEFINITIONS
from llm_harness.types import Message, ToolCallEvent, ToolResultEvent

load_dotenv()
litellm.suppress_debug_info = True

MODEL = os.environ.get("LH_MODEL", "")
ACCESS_TOKEN = os.environ.get("LH_ACCESS_TOKEN", "")
MAX_SESSION_COST = float(os.environ.get("LH_MAX_SESSION_COST", "0.50"))


def authenticate(username: str, password: str) -> bool:
    return password == ACCESS_TOKEN


def save_uploaded_files(files: list[str]) -> Path:
    workspace = Path(tempfile.mkdtemp(prefix="lh-workspace-"))
    for file_path in files:
        src = Path(file_path)
        (workspace / src.name).write_bytes(src.read_bytes())
    return workspace


def format_stats(trace: object) -> str:
    cost_str = f"${trace.cost:.4f}" if trace.cost else "n/a"
    cached = trace.cached_tokens
    cache_str = f" ({cached} cached)" if cached else ""
    scratchpad = len(trace.scratch_files)
    stats = (
        f"*{trace.prompt_tokens + trace.completion_tokens:,} tokens{cache_str}"
        f" · {len(trace.tool_calls)} tool calls"
        f" · {trace.wall_time_s:.1f}s"
        f" · {cost_str}"
    )
    if scratchpad:
        stats += f" · {scratchpad} scratchpad files"
    return stats + "*"


def build_trace_html(trace: object, question: str) -> str:
    trace_data = {
        "question": question,
        "passed": True,
        "assertions": {},
        "trace": asdict(trace),
    }
    return render_trace(trace_data, max_chars=2000)


def chat(
    message: str,
    history: list[dict],
    files: list[str] | None,
    workspace_path: str,
    scratch_path: str,
    session_cost: float,
):
    if not MODEL:
        yield (
            "Error: LH_MODEL not set.",
            "",
            workspace_path,
            scratch_path,
            session_cost,
        )
        return

    if session_cost >= MAX_SESSION_COST:
        yield (
            f"Session cost limit reached (${session_cost:.2f} / "
            f"${MAX_SESSION_COST:.2f}). Start a new session.",
            "",
            workspace_path,
            scratch_path,
            session_cost,
        )
        return

    # Set up workspace from uploaded files (first message only)
    workspace = Path(workspace_path) if workspace_path else None
    if files and not workspace:
        workspace = save_uploaded_files(files)
        workspace_path = str(workspace)

    # Set up scratchpad (once per session)
    if not scratch_path:
        scratch_path = tempfile.mkdtemp(prefix="lh-scratch-")
    scratch_dir = Path(scratch_path)

    # Build messages from Gradio history
    system_prompt = build_system_prompt(base_prompt="", workspace=workspace)
    messages: list[Message] = [{"role": "system", "content": system_prompt}]
    messages.extend({"role": e["role"], "content": e["content"]} for e in history)
    messages.append({"role": "user", "content": message})

    # Run agent loop and stream results
    start = time.monotonic()
    agent_run = run_agent_loop(
        model=MODEL,
        messages=messages,
        tools=TOOL_DEFINITIONS,
        completion=litellm.completion,
        workspace=workspace,
        scratch_dir=scratch_dir,
    )

    tool_call_count = 0
    try:
        for event in agent_run:
            if isinstance(event, ToolCallEvent):
                tool_call_count += 1
                status = f"*Exploring documents ({tool_call_count} tool calls)...*"
                yield status, "", workspace_path, scratch_path, session_cost
            elif isinstance(event, ToolResultEvent):
                continue
            else:
                cost = agent_run.trace.cost or 0
                session_cost += cost
    except Exception as exc:
        yield (
            f"Error: {exc}",
            "",
            workspace_path,
            scratch_path,
            session_cost,
        )
        return

    trace = agent_run.trace
    trace.wall_time_s = round(time.monotonic() - start, 2)
    answer = trace.answer or "(no answer)"
    stats = format_stats(trace)
    trace_html = build_trace_html(trace, message)

    yield (
        f"{answer}\n\n---\n{stats}",
        trace_html,
        workspace_path,
        scratch_path,
        session_cost,
    )


def build_app() -> gr.Blocks:
    with gr.Blocks(title="Document Explorer") as demo:
        gr.Markdown(
            "# Document Explorer\nUpload documents and ask questions about them."
        )

        workspace_state = gr.State("")
        scratch_state = gr.State("")
        cost_state = gr.State(0.0)

        file_upload = gr.File(
            label="Upload documents (text, CSV)",
            file_count="multiple",
            file_types=[".txt", ".csv", ".md", ".json"],
        )

        chatbot = gr.Chatbot()
        msg = gr.Textbox(placeholder="Ask a question about your documents...", label="")

        with gr.Accordion("Trace", open=False):
            trace_display = gr.HTML("")

        def respond(
            message, history, files, workspace_path, scratch_path, session_cost
        ):
            history = history or []
            history.append({"role": "user", "content": message})

            for response, trace_html, wp, sp, sc in chat(
                message, history[:-1], files, workspace_path, scratch_path, session_cost
            ):
                history_with_response = [
                    *history,
                    {"role": "assistant", "content": response},
                ]
                yield history_with_response, "", trace_html, wp, sp, sc

        msg.submit(
            respond,
            inputs=[
                msg,
                chatbot,
                file_upload,
                workspace_state,
                scratch_state,
                cost_state,
            ],
            outputs=[
                chatbot,
                msg,
                trace_display,
                workspace_state,
                scratch_state,
                cost_state,
            ],
        )

    return demo


if __name__ == "__main__":
    if not ACCESS_TOKEN:
        print("WARNING: LH_ACCESS_TOKEN not set — app is unprotected")

    app = build_app()
    app.launch(auth=authenticate if ACCESS_TOKEN else None)
