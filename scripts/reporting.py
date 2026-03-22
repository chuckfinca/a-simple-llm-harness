"""CSV reporting and trace persistence for eval results."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from llm_harness.telemetry import Trace


@dataclass
class EvalResult:
    workspace: str
    question: str
    category: str
    trace: Trace
    session: str = ""
    assertions: dict[str, bool] = field(default_factory=dict)
    passed: bool = False


def slugify(text: str) -> str:
    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")[:60]


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


CSV_COLUMNS = [
    "timestamp",
    "model",
    "trace_id",
    "session",
    "workspace",
    "category",
    "question",
    "passed",
    # Instruction following
    "used_tools",
    "used_scratchpad",
    "scratchpad_files",
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

    scratchpad_files = len(result.trace.scratch_files)

    return {
        "used_tools": used_tools,
        "used_scratchpad": scratchpad_files > 0,
        "scratchpad_files": scratchpad_files,
        "has_citations": has_citations,
        "has_sources_section": has_sources_section,
        "citation_count": citation_count,
        "files_accessed": "",
        "tool_sequence": "→".join(tc["name"] for tc in result.trace.tool_calls),
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


def append_results_csv(
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
                    "session": result.session,
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
                    "tool_time_s": round(trace.wall_time_s - trace.latency_s, 2)
                    if trace.wall_time_s
                    else "",
                    "avg_turn_latency_s": round(trace.latency_s / len(trace.turns), 2)
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


def append_tool_calls_csv(results: list[EvalResult], model: str) -> None:
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


def save_and_report(result: EvalResult, traces_dir: Path) -> None:
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
