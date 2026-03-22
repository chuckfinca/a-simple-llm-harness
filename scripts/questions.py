"""Question definitions and assertion-based evaluation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from llm_harness.telemetry import Trace

TEST_DATA_DIR = Path(__file__).parent.parent / "test-data"


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
    # Optional base system prompt for this question
    instructions: str = ""
    # Questions with the same session share message history and scratchpad
    session: str = ""


def load_questions() -> dict[str, list[Question]]:
    """Load questions.json from every workspace directory that has one."""
    questions: dict[str, list[Question]] = {}
    if not TEST_DATA_DIR.exists():
        return questions
    for workspace_dir in sorted(TEST_DATA_DIR.iterdir()):
        if not workspace_dir.is_dir():
            continue
        questions_file = workspace_dir / "questions.json"
        if not questions_file.exists():
            continue
        raw = json.loads(questions_file.read_text())
        questions[workspace_dir.name] = [
            Question(
                text=q["text"],
                category=q["category"],
                must_contain=q.get("must_contain", []),
                must_contain_any=q.get("must_contain_any", []),
                must_not_contain=q.get("must_not_contain", []),
                min_tool_calls=q.get("min_tool_calls", 1),
                instructions=q.get("instructions", ""),
                session=q.get("session", ""),
            )
            for q in raw
        ]
    return questions


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
