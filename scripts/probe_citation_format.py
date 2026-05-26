"""Probe whether Gemini emits the new <cite> tag format under the updated prompt.

Runs the real agent loop against a tiny throwaway workspace and inspects the
final answer for well-formed <cite> tags. Costs one real API call (~$0.001).

Usage:
    cd libraries/harness
    uv run python scripts/probe_citation_format.py
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

import litellm
from dotenv import load_dotenv

from llm_harness.agent import run_agent_loop
from llm_harness.citations import process_citations
from llm_harness.prompt import build_system_prompt
from llm_harness.sandbox import run_python as docker_run_python
from llm_harness.tools import TOOL_DEFINITIONS
from llm_harness.types import TextDeltaEvent, ToolCallEvent

load_dotenv()
litellm.suppress_debug_info = True

BASE_PROMPT = (
    "Your response should stand on its own.\n\n"
    "Do not speculate, manufacture connections to make a question fit, or "
    "answer off-topic questions."
)

FACTS_CONTENT = """AppSimple LLC was founded in 2013 by Charles Feinn.
The consultancy focuses on iOS development and AI engineering.
Charles has over twelve years of software development experience."""

QUESTION = "When was AppSimple founded and what does it focus on?"

CITE_OPENING = re.compile(r'<cite\s+file=["\'][^"\']+["\']\s*(?:/>|>)')
CITE_ELEMENT_OK = re.compile(
    r'<cite\s+file=["\'][^"\']+["\']\s*>.*?</cite\s*>', re.DOTALL,
)
CITE_SELF_CLOSING_OK = re.compile(
    r'<cite\s+file=["\'][^"\']+["\']\s*/>',
)


def main() -> None:
    model = os.environ.get("LH_MODEL", "")
    if not model:
        print("ERROR: LH_MODEL not set")
        sys.exit(1)

    workspace = Path(tempfile.mkdtemp(prefix="probe-workspace-"))
    (workspace / "facts.md").write_text(FACTS_CONTENT)
    scratch = Path(tempfile.mkdtemp(prefix="probe-scratch-"))

    system_prompt = build_system_prompt(base_prompt=BASE_PROMPT, workspace=workspace)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": QUESTION},
    ]

    print(f"Model: {model}")
    print(f"Question: {QUESTION}")
    print(f"Workspace: {workspace} (facts.md)\n")

    agent_run = run_agent_loop(
        model=model,
        messages=messages,
        tools=TOOL_DEFINITIONS,
        completion=litellm.completion,
        workspace=workspace,
        scratch_dir=scratch,
        sandbox_fn=docker_run_python,
        stream=False,
    )
    for event in agent_run:
        if isinstance(event, ToolCallEvent):
            print(f"  [tool call #{1}] {event.name}")
        elif isinstance(event, TextDeltaEvent):
            pass

    raw_answer = agent_run.trace.answer or ""
    print("\n=== RAW ANSWER ===")
    print(raw_answer)

    opens = CITE_OPENING.findall(raw_answer)
    well_formed_elements = CITE_ELEMENT_OK.findall(raw_answer)
    well_formed_self_closing = CITE_SELF_CLOSING_OK.findall(raw_answer)
    well_formed = len(well_formed_elements) + len(well_formed_self_closing)

    print("\n=== TAG ANALYSIS ===")
    print(f"  Opening <cite ...> patterns found: {len(opens)}")
    print(f"  Well-formed elements <cite ...>...</cite>: {len(well_formed_elements)}")
    print(f"  Well-formed self-closing <cite .../>: {len(well_formed_self_closing)}")
    if opens and len(opens) != well_formed:
        print(f"  WARNING: {len(opens) - well_formed} opener(s) without a matching well-formed closer")

    clean, sources = process_citations(raw_answer, workspace)
    print("\n=== AFTER process_citations ===")
    print(clean)
    print(f"\n  Sources extracted: {len(sources)}")
    for s in sources:
        match_flag = "✓" if s["matched"] else "✗"
        line = f"line {s['line']}" if s["line"] else "no line"
        quote = s["quote"][:60] + ("…" if len(s["quote"]) > 60 else "")
        print(f"  [{s['id']}] {match_flag} {s['file']} ({line}): {quote!r}")

    leftover = re.search(r'<cite|</cite|\[\w+\.md:', clean)
    print("\n=== VERDICT ===")
    if not opens:
        print("  ✗ Model emitted NO <cite> tags — prompt isn't taking. Investigate.")
        sys.exit(2)
    if opens and len(opens) != well_formed:
        print("  ✗ Model emitted malformed tags — parser will leak chrome.")
        sys.exit(2)
    if leftover:
        print(f"  ✗ Chrome leaked through process_citations: {leftover.group()!r}")
        sys.exit(2)
    if not sources:
        print("  ✗ Sources list is empty despite tags being present.")
        sys.exit(2)
    print(f"  ✓ {len(sources)} citation(s) extracted, no chrome leaked.")


if __name__ == "__main__":
    main()
