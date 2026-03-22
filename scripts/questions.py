"""Question definitions and assertion-based evaluation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from llm_harness.telemetry import Trace


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


def load_external_questions() -> dict[str, list[Question]]:
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
                instructions=q.get("instructions", ""),
                session=q.get("session", ""),
            )
            for q in raw
        ]
    return external


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
