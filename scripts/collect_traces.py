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
from llm_harness.telemetry import Trace
from llm_harness.tools import TOOL_DEFINITIONS
from llm_harness.types import Message

load_dotenv()


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
    "sec-10k": [
        Question(
            text="What was Amazon's net income in fiscal year 2025?",
            category="single_fact",
            must_contain=["amazon"],
            must_contain_any=[
                "77,670,000,000",
                "77.7 billion",
                "77.7B",
                "78 billion",
                "77,670 million",
                "77,670",
            ],
            min_tool_calls=1,
        ),
        Question(
            text=(
                "Which company had higher total revenue in fiscal year 2025,"
                " JPMorgan Chase or UnitedHealth Group?"
            ),
            category="comparison",
            must_contain=["unitedhealth group"],
            min_tool_calls=2,
        ),
        Question(
            text="Which company in the dataset had the highest total revenue?",
            category="multi_doc",
            must_contain=["amazon"],
            min_tool_calls=3,
        ),
        Question(
            text="Which company in the dataset had the highest net income?",
            category="multi_doc",
            must_contain=["alphabet"],
            min_tool_calls=3,
        ),
        Question(
            text="Which company in the dataset had the highest total assets?",
            category="multi_doc",
            must_contain=["jpmorgan chase"],
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


def _load_external_questions() -> dict[str, list[Question]]:
    """Load questions.json from any workspace directory that has one."""
    external: dict[str, list[Question]] = {}
    test_data_dir = Path(__file__).parent.parent / "test-data"
    if not test_data_dir.exists():
        return external
    for workspace_dir in sorted(test_data_dir.iterdir()):
        if not workspace_dir.is_dir() or workspace_dir.name in QUESTIONS:
            continue
        questions_file = workspace_dir / "questions.json"
        if not questions_file.exists():
            continue
        raw = json.loads(questions_file.read_text())
        external[workspace_dir.name] = [
            Question(
                text=q["text"],
                category=q["category"],
                must_contain=q.get("must_contain", []),
                must_contain_any=q.get("must_contain_any", []),
                must_not_contain=q.get("must_not_contain", []),
                min_tool_calls=q.get("min_tool_calls", 1),
            )
            for q in raw
        ]
    return external


@dataclass
class EvalResult:
    workspace: str
    question: str
    category: str
    trace: Trace
    assertions: dict[str, bool] = field(default_factory=dict)
    passed: bool = False


def slugify(text: str) -> str:
    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")[:60]


def evaluate_assertions(trace: Trace, question: Question) -> dict[str, bool]:
    answer = (trace.answer or "").lower()
    tool_count = len(trace.tool_calls)
    assertions: dict[str, bool] = {}

    for term in question.must_contain:
        assertions[f"contains '{term}'"] = term.lower() in answer

    if question.must_contain_any:
        found = any(term.lower() in answer for term in question.must_contain_any)
        assertions[f"contains_any {question.must_contain_any}"] = found

    for term in question.must_not_contain:
        assertions[f"not contains '{term}'"] = term.lower() not in answer

    assertions[f"min_tool_calls >= {question.min_tool_calls}"] = (
        tool_count >= question.min_tool_calls
    )

    assertions["has_answer"] = trace.answer is not None and trace.error is None

    return assertions


@dataclass
class ToolResultParsed:
    result_count: int = 0
    succeeded: bool = False
    error: str | None = None


def _parse_tool_result(result: str) -> ToolResultParsed:
    try:
        data = json.loads(result)
    except (json.JSONDecodeError, TypeError):
        return ToolResultParsed(error="invalid JSON")

    if "error" in data:
        return ToolResultParsed(error=str(data["error"]))

    succeeded = data.get("exit_code") == 0
    return ToolResultParsed(
        result_count=1 if succeeded else 0,
        succeeded=succeeded,
    )



def run_question(model: str, workspace_name: str, question: Question) -> EvalResult:
    workspace = (Path(__file__).parent.parent / "test-data" / workspace_name).resolve()

    system_prompt = build_system_prompt(
        base_prompt="",
        workspace=workspace,
    )

    messages: list[Message] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question.text},
    ]

    start = time.monotonic()
    agent_run = run_agent_loop(
        model=model,
        messages=messages,
        tools=TOOL_DEFINITIONS,
        completion=litellm.completion,
        workspace=workspace,
    )

    try:
        for _ in agent_run:
            pass
    except Exception as exc:
        agent_run.trace.error = str(exc)

    agent_run.trace.wall_time_s = round(time.monotonic() - start, 2)

    assertions = evaluate_assertions(agent_run.trace, question)
    return EvalResult(
        workspace=workspace_name,
        question=question.text,
        category=question.category,
        trace=agent_run.trace,
        assertions=assertions,
        passed=all(assertions.values()),
    )


def _run_all(model: str, jobs: list[tuple[str, Question]], workers: int):
    """Yield (workspace_name, question, result) for each completed job."""
    if workers <= 1:
        for workspace_name, question in jobs:
            result = run_question(model, workspace_name, question)
            yield workspace_name, question, result
    else:
        print(f"Running {len(jobs)} questions with {workers} workers\n", flush=True)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {}
            for workspace_name, question in jobs:
                future = pool.submit(run_question, model, workspace_name, question)
                futures[future] = (workspace_name, question)
            for future in as_completed(futures):
                workspace_name, question = futures[future]
                yield workspace_name, question, future.result()


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect agent traces")
    parser.add_argument(
        "--workers", type=int, default=1, help="Number of parallel workers (default: 1)"
    )
    parser.add_argument(
        "--filter",
        nargs="+",
        help="Only run questions whose slug contains one of these substrings",
    )
    args = parser.parse_args()

    litellm.suppress_debug_info = True

    model = os.environ.get("LH_MODEL")
    if not model:
        print("ERROR: LH_MODEL not set")
        return

    model_slug = slugify(model)
    traces_dir = Path(__file__).parent.parent / "traces" / model_slug

    all_questions = {**QUESTIONS, **_load_external_questions()}

    jobs: list[tuple[str, Question]] = []
    for workspace_name, questions in all_questions.items():
        workspace_dir = traces_dir / workspace_name
        workspace_dir.mkdir(parents=True, exist_ok=True)
        jobs.extend((workspace_name, question) for question in questions)

    if args.filter:
        jobs = [
            (ws, q)
            for ws, q in jobs
            if any(f in slugify(q.text) for f in args.filter)
        ]
        print(f"Filtered to {len(jobs)} questions matching {args.filter}\n")

    total = len(jobs)
    passed = 0
    failed = 0
    start_all = time.monotonic()
    results: list[EvalResult] = []

    for completed, (workspace_name, question, result) in enumerate(
        _run_all(model, jobs, args.workers), 1
    ):
        print(
            f"[{completed}/{total}] {workspace_name}: {question.text[:60]}...",
            flush=True,
        )
        results.append(result)
        if result.passed:
            passed += 1
        else:
            failed += 1
        _save_and_report(result, traces_dir)

    total_elapsed = time.monotonic() - start_all
    print(f"\nTraces saved to {traces_dir} ({total_elapsed:.1f}s total)")
    print(f"Results: {passed} passed, {failed} failed, {total} total")

    if failed > 0:
        print("\nFailed assertions:")
        for result in results:
            if not result.passed:
                print(f"  {result.workspace}: {result.question[:60]}")
                for name, ok in result.assertions.items():
                    if not ok:
                        print(f"    FAIL: {name}")

    run_type = "rerun" if args.filter else "full"
    _append_csv(results, model, run_type)
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
    "used_scratch",
    "has_citations",
    "has_sources_section",
    "citation_count",
    "files_accessed",
    "tool_sequence",
    # Performance
    "tool_calls",
    "prompt_tokens",
    "completion_tokens",
    "cached_tokens",
    "total_tokens",
    "cost_usd",
    "model_time_s",
    "tool_time_s",
    "avg_turn_latency_s",
    "wall_time_s",
    # Diagnostics
    "stdout_truncations",
    "failed_assertions",
    "error",
    "run_type",
]


def _extract_instruction_metrics(result: EvalResult) -> dict[str, object]:
    answer = result.trace.answer or ""

    used_tools = len(result.trace.tool_calls) > 0

    citations = re.findall(r"\[\d+\]", answer)
    has_citations = len(citations) > 0
    citation_count = len(set(citations))

    has_sources_section = bool(re.search(r"(?i)\bsources?\s*:", answer))

    stdout_truncations = sum(
        1
        for tc in result.trace.tool_calls
        if "characters omitted" in tc.get("result", "")
    )

    used_scratch = bool(result.trace.scratch_files)

    return {
        "used_tools": used_tools,
        "used_scratch": used_scratch,
        "has_citations": has_citations,
        "has_sources_section": has_sources_section,
        "citation_count": citation_count,
        "files_accessed": "",
        "tool_sequence": "→".join(
            tc["name"] for tc in result.trace.tool_calls
        ),
        "stdout_truncations": stdout_truncations,
    }


def _rewrite_csv_if_schema_changed(csv_path: Path, columns: list[str]) -> None:
    """Rewrite a CSV if its header doesn't match the expected columns."""
    if not csv_path.exists():
        return
    with csv_path.open(newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header == columns:
            return
        rows = list(reader)
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        if header:
            for row in rows:
                mapped = dict(zip(header, row, strict=False))
                writer.writerow({col: mapped.get(col, "") for col in columns})


def _append_csv(
    results: list[EvalResult],
    model: str,
    run_type: str = "full",
) -> None:
    csv_path = Path(__file__).parent.parent / "traces" / "results.csv"
    _rewrite_csv_if_schema_changed(csv_path, CSV_COLUMNS)

    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")

    with csv_path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if not csv_path.stat().st_size:
            writer.writeheader()

        for result in results:
            trace = result.trace
            prompt_tokens = trace.prompt_tokens
            completion_tokens = trace.completion_tokens
            failed_assertions = [
                name for name, ok in result.assertions.items() if not ok
            ]
            metrics = _extract_instruction_metrics(result)
            writer.writerow(
                {
                    "timestamp": timestamp,
                    "model": model,
                    "trace_id": f"{result.workspace}/{slugify(result.question)}",
                    "workspace": result.workspace,
                    "category": result.category,
                    "question": result.question,
                    "passed": result.passed,
                    **metrics,
                    "tool_calls": len(trace.tool_calls),
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "cached_tokens": trace.cached_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                    "cost_usd": f"{trace.cost:.6f}" if trace.cost else "",
                    "model_time_s": trace.latency_s,
                    "tool_time_s": round(
                        trace.wall_time_s - trace.latency_s, 2
                    )
                    if trace.wall_time_s
                    else "",
                    "avg_turn_latency_s": round(
                        trace.latency_s / len(trace.turns), 2
                    )
                    if trace.turns
                    else "",
                    "wall_time_s": trace.wall_time_s,
                    "failed_assertions": (
                        "; ".join(failed_assertions) if failed_assertions else ""
                    ),
                    "error": trace.error or "",
                    "run_type": run_type,
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


def _append_tool_calls_csv(results: list[EvalResult], model: str) -> None:
    csv_path = Path(__file__).parent.parent / "traces" / "tool_calls.csv"
    _rewrite_csv_if_schema_changed(csv_path, TOOL_CALL_COLUMNS)
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")

    with csv_path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TOOL_CALL_COLUMNS)
        if not csv_path.stat().st_size:
            writer.writeheader()

        for result in results:
            trace_id = f"{result.workspace}/{slugify(result.question)}"
            for step, tool_call in enumerate(result.trace.tool_calls):
                parsed = _parse_tool_result(tool_call.get("result", ""))
                writer.writerow(
                    {
                        "timestamp": timestamp,
                        "model": model,
                        "trace_id": trace_id,
                        "step": step,
                        "tool": tool_call["name"],
                        "arguments": tool_call["arguments"],
                        "result_count": parsed.result_count,
                        "hit": parsed.succeeded,
                        "error": parsed.error or "",
                    }
                )

    print(f"Tool calls appended to {csv_path}", flush=True)


def _save_and_report(result: EvalResult, traces_dir: Path) -> None:
    out_file = traces_dir / result.workspace / f"{slugify(result.question)}.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(asdict(result), indent=2, default=str))

    trace = result.trace
    status = "PASS" if result.passed else "FAIL"
    model_s = trace.latency_s
    tool_s = round(trace.wall_time_s - model_s, 1)
    print(
        f"  {status} | {len(trace.tool_calls)} tool calls | "
        f"{trace.wall_time_s:.1f}s (model {model_s}s, tools {tool_s}s)",
        flush=True,
    )

    if not result.passed:
        for name, ok in result.assertions.items():
            if not ok:
                print(f"    FAIL: {name}", flush=True)

    if result.trace.error:
        print(f"    ERROR: {result.trace.error}", flush=True)


if __name__ == "__main__":
    main()
