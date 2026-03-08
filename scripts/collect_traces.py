"""Run questions across workspaces and save full agent traces for error analysis.

Usage:
    uv run python scripts/collect_traces.py

Requires LH_MODEL in .env or environment. Traces are saved as JSON in
traces/<model>/<workspace>/<slug>.json for manual review.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import litellm
from dotenv import load_dotenv

from llm_harness.agent import run_agent_loop
from llm_harness.prompt import build_system_prompt
from llm_harness.tools import TOOL_DEFINITIONS
from llm_harness.types import (
    Message,
    ResponseEvent,
    ToolCallEvent,
)

load_dotenv()

BASE_PROMPT = (
    "You are a helpful assistant with access to tools for computation, "
    "code execution, and file exploration."
)

QUESTIONS: dict[str, list[str]] = {
    "federalist-papers": [
        "What does Federalist No. 10 argue about factions?",
        "Which papers discuss the judiciary?",
        "What are the main themes across the Federalist Papers?",
        "What does Hamilton say about standing armies?",
        "How do Hamilton and Madison differ on federal power?",
    ],
    "origin-of-species": [
        "What does Darwin say about natural selection in Chapter 4?",
        "How does Darwin explain the struggle for existence?",
        "What examples of variation under domestication does Darwin give?",
    ],
    "sherlock-holmes": [
        'What happens in "A Scandal in Bohemia"?',
        "How does Holmes solve the case in The Speckled Band?",
        "What methods does Holmes use across the stories?",
    ],
    "world-factbook": [
        "What is the population of Japan?",
        "Compare the economies of Brazil and Argentina.",
        "Which countries in the dataset are in Africa?",
    ],
}


def slugify(text: str) -> str:
    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")[:60]


@dataclass
class Trace:
    workspace: str
    question: str
    answer: str | None = None
    tool_calls: list[dict[str, str]] = field(default_factory=list)
    latency_s: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost: float | None = None
    error: str | None = None


def run_question(model: str, workspace_name: str, question: str) -> Trace:
    workspace = (Path(__file__).parent.parent / "test-data" / workspace_name).resolve()

    system_prompt = build_system_prompt(
        base_prompt=BASE_PROMPT,
        workspace=workspace,
    )

    messages: list[Message] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]

    trace = Trace(workspace=workspace_name, question=question)

    try:
        for event in run_agent_loop(
            model=model,
            messages=messages,
            tools=TOOL_DEFINITIONS,
            completion=litellm.completion,
            workspace=workspace,
        ):
            if isinstance(event, ToolCallEvent):
                trace.tool_calls.append(
                    {"name": event.name, "arguments": event.arguments}
                )
            elif isinstance(event, ResponseEvent):
                trace.answer = event.content
                trace.latency_s = event.latency_s
                trace.prompt_tokens = event.prompt_tokens
                trace.completion_tokens = event.completion_tokens
                trace.cost = event.cost
    except Exception as exc:
        trace.error = str(exc)

    return trace


def main() -> None:
    litellm.suppress_debug_info = True

    model = os.environ.get("LH_MODEL")
    if not model:
        print("ERROR: LH_MODEL not set")
        return

    model_slug = slugify(model)
    traces_dir = Path(__file__).parent.parent / "traces" / model_slug

    total = sum(len(qs) for qs in QUESTIONS.values())
    completed = 0

    for workspace_name, questions in QUESTIONS.items():
        workspace_dir = traces_dir / workspace_name
        workspace_dir.mkdir(parents=True, exist_ok=True)

        for question in questions:
            completed += 1
            slug = slugify(question)
            out_file = workspace_dir / f"{slug}.json"

            print(
                f"[{completed}/{total}] {workspace_name}: {question[:60]}...",
                flush=True,
            )

            start = time.monotonic()
            trace = run_question(model, workspace_name, question)
            elapsed = time.monotonic() - start

            out_file.write_text(json.dumps(asdict(trace), indent=2, default=str))

            status = "OK" if trace.answer else "ERROR"
            tools_used = len(trace.tool_calls)
            print(f"  {status} | {tools_used} tool calls | {elapsed:.1f}s", flush=True)

            if trace.error:
                print(f"  ERROR: {trace.error}", flush=True)

    print(f"\nTraces saved to {traces_dir}")


if __name__ == "__main__":
    main()
