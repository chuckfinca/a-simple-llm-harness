"""Run questions across workspaces and save full agent traces for error analysis.

Usage:
    uv run python scripts/collect_traces.py
    uv run python scripts/collect_traces.py --filter highest-revenue

Requires LH_MODEL in .env or environment. Traces are saved as JSON in
traces/<model>/<workspace>/<slug>.json for manual review.
"""

from __future__ import annotations

import argparse
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import litellm
from dotenv import load_dotenv
from questions import (
    Question,
    evaluate_assertions,
    load_questions,
)
from reporting import (
    EvalResult,
    append_results_csv,
    append_tool_calls_csv,
    save_and_report,
    slugify,
)

from llm_harness.agent import run_agent_loop
from llm_harness.prompt import build_system_prompt
from llm_harness.tools import TOOL_DEFINITIONS
from llm_harness.types import Message

load_dotenv()


def run_question(
    model: str,
    workspace_name: str,
    question: Question,
    *,
    messages: list[Message] | None = None,
    scratch_dir: Path | None = None,
) -> EvalResult:
    workspace = (Path(__file__).parent.parent / "test-data" / workspace_name).resolve()

    if messages is None:
        system_prompt = build_system_prompt(
            base_prompt=question.instructions,
            workspace=workspace,
        )
        messages = [{"role": "system", "content": system_prompt}]

    message_offset = len(messages)
    messages.append({"role": "user", "content": question.text})

    start = time.monotonic()
    agent_run = run_agent_loop(
        model=model,
        messages=messages,
        tools=TOOL_DEFINITIONS,
        completion=litellm.completion,
        workspace=workspace,
        scratch_dir=scratch_dir,
    )

    try:
        for _ in agent_run:
            pass
    except Exception as exc:
        agent_run.trace.error = str(exc)

    agent_run.trace.wall_time_s = round(time.monotonic() - start, 2)
    agent_run.trace.message_offset = message_offset

    assertions = evaluate_assertions(agent_run.trace, question)
    return EvalResult(
        workspace=workspace_name,
        question=question.text,
        category=question.category,
        trace=agent_run.trace,
        session=question.session,
        assertions=assertions,
        passed=all(assertions.values()),
    )


def _run_session(
    model: str, workspace_name: str, questions: list[Question]
) -> list[tuple[str, Question, EvalResult]]:
    """Run questions sequentially with shared message history and scratchpad."""
    workspace = (Path(__file__).parent.parent / "test-data" / workspace_name).resolve()
    system_prompt = build_system_prompt(
        base_prompt=questions[0].instructions,
        workspace=workspace,
    )
    messages: list[Message] = [{"role": "system", "content": system_prompt}]
    results: list[tuple[str, Question, EvalResult]] = []
    with tempfile.TemporaryDirectory(prefix="lh-scratch-") as scratch:
        scratch_dir = Path(scratch)
        for question in questions:
            result = run_question(
                model,
                workspace_name,
                question,
                messages=messages,
                scratch_dir=scratch_dir,
            )
            results.append((workspace_name, question, result))
    return results


def _group_sessions(
    jobs: list[tuple[str, Question]],
) -> list[tuple[str, list[Question]]]:
    """Group jobs into sessions. Standalone questions become single-question sessions."""
    groups: dict[tuple[str, str], list[Question]] = {}
    standalone_idx = 0
    for workspace_name, question in jobs:
        if question.session:
            key = (workspace_name, question.session)
        else:
            key = (workspace_name, f"__standalone_{standalone_idx}")
            standalone_idx += 1
        groups.setdefault(key, []).append(question)

    return [(ws, questions) for (ws, _), questions in groups.items()]


def _run_all(model: str, jobs: list[tuple[str, Question]]):
    """Yield (workspace_name, question, result) for each completed job.

    Every question group is a session — standalone questions are sessions of
    one.  Each session gets its own worker so all sessions run concurrently.
    """
    sessions = _group_sessions(jobs)
    with ThreadPoolExecutor(max_workers=len(sessions)) as pool:
        futures = {
            pool.submit(_run_session, model, ws, questions): (ws, questions)
            for ws, questions in sessions
        }
        for future in as_completed(futures):
            yield from future.result()


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect agent traces")
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

    all_questions = load_questions()

    jobs: list[tuple[str, Question]] = []
    for workspace_name, questions in all_questions.items():
        workspace_dir = traces_dir / workspace_name
        workspace_dir.mkdir(parents=True, exist_ok=True)
        jobs.extend((workspace_name, question) for question in questions)

    if args.filter:
        jobs = [
            (ws, q) for ws, q in jobs if any(f in slugify(q.text) for f in args.filter)
        ]
        print(f"Filtered to {len(jobs)} questions matching {args.filter}\n")

    total = len(jobs)
    passed = 0
    failed = 0
    start_all = time.monotonic()
    results: list[EvalResult] = []

    for completed, (workspace_name, question, result) in enumerate(
        _run_all(model, jobs), 1
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
        save_and_report(result, traces_dir)

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
    append_results_csv(results, model, run_type)
    append_tool_calls_csv(results, model)


if __name__ == "__main__":
    main()
