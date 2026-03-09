"""Run questions across workspaces and save full agent traces for error analysis.

Usage:
    uv run python scripts/collect_traces.py
    uv run python scripts/collect_traces.py --workers 4

Requires LH_MODEL in .env or environment. Traces are saved as JSON in
traces/<model>/<workspace>/<slug>.json for manual review.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
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
    ToolResultEvent,
)

load_dotenv()

EVAL_PROMPT = (
    "You are a helpful assistant with access to tools for computation, "
    "code execution, and file exploration."
)


@dataclass
class Question:
    text: str
    category: str
    # Answer must contain ALL of these (case-insensitive)
    must_contain: list[str] = field(default_factory=list)
    # Answer must contain AT LEAST ONE of these (case-insensitive)
    must_contain_any: list[str] = field(default_factory=list)
    # Answer must NOT contain any of these (case-insensitive)
    must_not_contain: list[str] = field(default_factory=list)
    # Must have at least this many tool calls
    min_tool_calls: int = 1


QUESTIONS: dict[str, list[Question]] = {
    "federalist-papers": [
        Question(
            text="What does Federalist No. 10 argue about factions?",
            category="single_doc",
            must_contain=["madison", "faction"],
        ),
        Question(
            text="Which papers discuss the judiciary?",
            category="enumeration",
            must_contain_any=["78", "79", "80", "81"],
        ),
        Question(
            text="What are the main themes across the Federalist Papers?",
            category="multi_doc",
            min_tool_calls=3,
        ),
        Question(
            text="What does Hamilton say about standing armies?",
            category="single_doc",
            must_contain=["hamilton"],
            must_contain_any=["army", "armies", "military"],
        ),
        Question(
            text="How do Hamilton and Madison differ on federal power?",
            category="comparison",
            must_contain=["hamilton", "madison"],
        ),
    ],
    "origin-of-species": [
        Question(
            text="What does Darwin say about natural selection in Chapter 4?",
            category="single_doc",
            must_contain=["natural selection"],
        ),
        Question(
            text="How does Darwin explain the struggle for existence?",
            category="single_doc",
            must_contain_any=["geometrical", "geometric", "increase"],
        ),
        Question(
            text="What examples of variation under domestication does Darwin give?",
            category="enumeration",
            must_contain_any=["pigeon", "dog", "cattle", "horse", "sheep"],
        ),
    ],
    "sherlock-holmes": [
        Question(
            text='What happens in "A Scandal in Bohemia"?',
            category="single_doc",
            must_contain=["irene adler"],
            must_contain_any=["photograph", "king"],
        ),
        Question(
            text="How does Holmes solve the case in The Speckled Band?",
            category="single_doc",
            must_contain_any=["snake", "adder", "ventilator"],
        ),
        Question(
            text="What methods does Holmes use across the stories?",
            category="multi_doc",
            min_tool_calls=3,
        ),
    ],
    "world-factbook": [
        Question(
            text="What is the population of Japan?",
            category="single_fact",
            must_contain_any=["123,201,945", "123.2 million", "123 million"],
        ),
        Question(
            text="Compare the economies of Brazil and Argentina.",
            category="comparison",
            must_contain=["brazil", "argentina"],
            min_tool_calls=2,
        ),
        Question(
            text="Which countries in the dataset are in Africa?",
            category="enumeration",
            must_contain_any=["nigeria", "kenya", "ghana", "egypt", "ethiopia"],
            min_tool_calls=2,
        ),
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
    category: str = ""
    answer: str | None = None
    tool_calls: list[dict] = field(default_factory=list)
    latency_s: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost: float | None = None
    error: str | None = None
    assertions: dict[str, bool] = field(default_factory=dict)
    passed: bool = False


def check_assertions(trace: Trace, question: Question) -> None:
    answer = (trace.answer or "").lower()
    tool_count = len(trace.tool_calls)

    if question.must_contain:
        for term in question.must_contain:
            trace.assertions[f"contains '{term}'"] = term.lower() in answer

    if question.must_contain_any:
        found = any(term.lower() in answer for term in question.must_contain_any)
        trace.assertions[f"contains_any {question.must_contain_any}"] = found

    if question.must_not_contain:
        for term in question.must_not_contain:
            trace.assertions[f"not contains '{term}'"] = term.lower() not in answer

    trace.assertions[f"min_tool_calls >= {question.min_tool_calls}"] = (
        tool_count >= question.min_tool_calls
    )

    trace.assertions["has_answer"] = trace.answer is not None and trace.error is None

    trace.passed = all(trace.assertions.values())


def _parse_tool_result(
    tool_name: str, result: str
) -> tuple[int, bool, str | None]:
    try:
        data = json.loads(result)
    except (json.JSONDecodeError, TypeError):
        return 0, False, "invalid JSON"

    if "error" in data:
        return 0, False, str(data["error"])

    if tool_name == "search_files":
        count = data.get("total_matches", 0)
    elif tool_name == "list_files":
        count = data.get("count", 0)
    elif tool_name == "read_file":
        count = data.get("lines_returned", 0)
    elif tool_name == "run_python":
        count = 1 if data.get("exit_code") == 0 else 0
    elif tool_name == "calculator":
        count = 1 if "result" in data else 0
    else:
        count = 1

    return count, count > 0, None


def run_question(model: str, workspace_name: str, question: Question) -> Trace:
    workspace = (Path(__file__).parent.parent / "test-data" / workspace_name).resolve()

    system_prompt = build_system_prompt(
        base_prompt=EVAL_PROMPT,
        workspace=workspace,
    )

    messages: list[Message] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question.text},
    ]

    trace = Trace(
        workspace=workspace_name,
        question=question.text,
        category=question.category,
    )

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
            elif isinstance(event, ToolResultEvent):
                result_count, hit, error = _parse_tool_result(
                    event.name, event.result
                )
                trace.tool_calls[-1].update(
                    {"result_count": result_count, "hit": hit, "error": error}
                )
            elif isinstance(event, ResponseEvent):
                trace.answer = event.content
                trace.latency_s = event.latency_s
                trace.prompt_tokens = event.prompt_tokens
                trace.completion_tokens = event.completion_tokens
                trace.cost = event.cost
    except Exception as exc:
        trace.error = str(exc)

    check_assertions(trace, question)
    return trace


def _run_all(model: str, jobs: list[tuple[str, Question]], workers: int):
    """Yield (workspace_name, question, trace, elapsed) for each completed job."""
    if workers <= 1:
        for workspace_name, question in jobs:
            start = time.monotonic()
            trace = run_question(model, workspace_name, question)
            yield workspace_name, question, trace, time.monotonic() - start
    else:
        print(f"Running {len(jobs)} questions with {workers} workers\n", flush=True)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {}
            for workspace_name, question in jobs:
                future = pool.submit(run_question, model, workspace_name, question)
                futures[future] = (workspace_name, question, time.monotonic())
            for future in as_completed(futures):
                workspace_name, question, start = futures[future]
                elapsed = time.monotonic() - start
                yield workspace_name, question, future.result(), elapsed


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect agent traces")
    parser.add_argument(
        "--workers", type=int, default=1, help="Number of parallel workers (default: 1)"
    )
    args = parser.parse_args()

    litellm.suppress_debug_info = True

    model = os.environ.get("LH_MODEL")
    if not model:
        print("ERROR: LH_MODEL not set")
        return

    model_slug = slugify(model)
    traces_dir = Path(__file__).parent.parent / "traces" / model_slug

    jobs: list[tuple[str, Question]] = []
    for workspace_name, questions in QUESTIONS.items():
        workspace_dir = traces_dir / workspace_name
        workspace_dir.mkdir(parents=True, exist_ok=True)
        jobs.extend((workspace_name, question) for question in questions)

    total = len(jobs)
    passed = 0
    failed = 0
    start_all = time.monotonic()
    results: list[Trace] = []
    wall_times: dict[str, float] = {}

    for completed, (workspace_name, question, trace, elapsed) in enumerate(
        _run_all(model, jobs, args.workers), 1
    ):
        print(
            f"[{completed}/{total}] {workspace_name}: {question.text[:60]}...",
            flush=True,
        )
        results.append(trace)
        wall_times[slugify(trace.question)] = elapsed
        if trace.passed:
            passed += 1
        else:
            failed += 1
        _save_and_report(trace, traces_dir, elapsed)

    total_elapsed = time.monotonic() - start_all
    print(f"\nTraces saved to {traces_dir} ({total_elapsed:.1f}s total)")
    print(f"Results: {passed} passed, {failed} failed, {total} total")

    if failed > 0:
        print("\nFailed assertions:")
        for trace in results:
            if not trace.passed:
                print(f"  {trace.workspace}: {trace.question[:60]}")
                for name, ok in trace.assertions.items():
                    if not ok:
                        print(f"    FAIL: {name}")

    _append_csv(results, model, wall_times)
    _append_tool_calls_csv(results, model)


CSV_COLUMNS = [
    "timestamp",
    "model",
    "trace_id",
    "workspace",
    "category",
    "question",
    "passed",
    # Instruction following
    "used_tools",
    "has_citations",
    "has_sources_section",
    "citation_count",
    "files_accessed",
    "tool_sequence",
    # Performance
    "tool_calls",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "cost_usd",
    "latency_s",
    "wall_time_s",
    # Diagnostics
    "failed_assertions",
    "error",
]


def _extract_instruction_metrics(trace: Trace) -> dict[str, object]:
    answer = trace.answer or ""

    used_tools = len(trace.tool_calls) > 0

    citations = re.findall(r"\[\d+\]", answer)
    has_citations = len(citations) > 0
    citation_count = len(set(citations))

    has_sources_section = bool(re.search(r"(?i)\bsources?\s*:", answer))

    files_read = set()
    for tool_call in trace.tool_calls:
        try:
            arguments = json.loads(tool_call["arguments"])
        except (json.JSONDecodeError, KeyError):
            continue
        if tool_call["name"] == "read_file" and "path" in arguments:
            files_read.add(arguments["path"])

    tool_abbreviations = {
        "list_files": "L",
        "search_files": "S",
        "read_file": "R",
        "run_python": "P",
        "calculator": "C",
        "get_current_time": "T",
    }
    tool_sequence = "→".join(
        tool_abbreviations.get(tool_call["name"], "?")
        for tool_call in trace.tool_calls
    )

    return {
        "used_tools": used_tools,
        "has_citations": has_citations,
        "has_sources_section": has_sources_section,
        "citation_count": citation_count,
        "files_accessed": len(files_read),
        "tool_sequence": tool_sequence,
    }


def _append_csv(
    results: list[Trace],
    model: str,
    wall_times: dict[str, float],
) -> None:
    csv_path = Path(__file__).parent.parent / "traces" / "results.csv"
    file_exists = csv_path.exists()

    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")

    with csv_path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if not file_exists:
            writer.writeheader()

        for trace in results:
            prompt_tokens = trace.prompt_tokens or 0
            completion_tokens = trace.completion_tokens or 0
            failed_assertions = [
                name for name, ok in trace.assertions.items() if not ok
            ]
            metrics = _extract_instruction_metrics(trace)
            writer.writerow(
                {
                    "timestamp": timestamp,
                    "model": model,
                    "trace_id": f"{trace.workspace}/{slugify(trace.question)}",
                    "workspace": trace.workspace,
                    "category": trace.category,
                    "question": trace.question,
                    "passed": trace.passed,
                    **metrics,
                    "tool_calls": len(trace.tool_calls),
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                    "cost_usd": f"{trace.cost:.6f}" if trace.cost else "",
                    "latency_s": trace.latency_s,
                    "wall_time_s": round(
                        wall_times.get(slugify(trace.question), 0), 1
                    ),
                    "failed_assertions": (
                        "; ".join(failed_assertions) if failed_assertions else ""
                    ),
                    "error": trace.error or "",
                }
            )

    print(f"Results appended to {csv_path}", flush=True)


TOOL_CALL_COLUMNS = [
    "timestamp",
    "model",
    "trace_id",
    "step",
    "tool",
    "arguments",
    "result_count",
    "hit",
    "error",
]


def _append_tool_calls_csv(results: list[Trace], model: str) -> None:
    csv_path = Path(__file__).parent.parent / "traces" / "tool_calls.csv"
    file_exists = csv_path.exists()
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")

    with csv_path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TOOL_CALL_COLUMNS)
        if not file_exists:
            writer.writeheader()

        for trace in results:
            trace_id = f"{trace.workspace}/{slugify(trace.question)}"
            for step, tool_call in enumerate(trace.tool_calls):
                writer.writerow(
                    {
                        "timestamp": timestamp,
                        "model": model,
                        "trace_id": trace_id,
                        "step": step,
                        "tool": tool_call["name"],
                        "arguments": tool_call["arguments"],
                        "result_count": tool_call.get("result_count", ""),
                        "hit": tool_call.get("hit", ""),
                        "error": tool_call.get("error") or "",
                    }
                )

    print(f"Tool calls appended to {csv_path}", flush=True)


def _save_and_report(trace: Trace, traces_dir: Path, elapsed: float) -> None:
    out_file = traces_dir / trace.workspace / f"{slugify(trace.question)}.json"
    out_file.write_text(json.dumps(asdict(trace), indent=2, default=str))

    status = "PASS" if trace.passed else "FAIL"
    tools_used = len(trace.tool_calls)
    print(f"  {status} | {tools_used} tool calls | {elapsed:.1f}s", flush=True)

    if not trace.passed:
        for name, ok in trace.assertions.items():
            if not ok:
                print(f"    FAIL: {name}", flush=True)

    if trace.error:
        print(f"    ERROR: {trace.error}", flush=True)


if __name__ == "__main__":
    main()
