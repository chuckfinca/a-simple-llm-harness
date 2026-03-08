"""Counterfactual tests to verify the agent reads documents instead of using training data.

These are integration tests that make real LLM API calls and run Docker containers.
They are slow and cost money. Run explicitly with:

    uv run pytest tests/test_retrieval_grounding.py -m integration

Three mutation types:
    1. Text replacement — change a fact, verify the agent returns the changed version
    2. Synthetic file — add a new document, verify the agent can find and use it
    3. Document removal — delete relevant files, verify the agent says "not found"
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import litellm
import pytest
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

pytestmark = pytest.mark.integration

TEST_DATA = Path(__file__).parent.parent / "test-data"
BASE_PROMPT = (
    "You are a helpful assistant with access to tools for computation, "
    "code execution, and file exploration."
)


@dataclass
class AgentTrace:
    question: str
    answer: str | None
    tool_calls: list[dict[str, str]] = field(default_factory=list)
    events: list[object] = field(default_factory=list)


def _run_agent(question: str, workspace: Path) -> AgentTrace:
    """Run the agent against a workspace and collect the full trace."""
    model = os.environ.get("LH_MODEL")
    if not model:
        pytest.skip("LH_MODEL not set")

    system_prompt = build_system_prompt(
        base_prompt=BASE_PROMPT,
        workspace=workspace,
    )

    messages: list[Message] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]

    trace = AgentTrace(question=question, answer=None)

    for event in run_agent_loop(
        model=model,
        messages=messages,
        tools=TOOL_DEFINITIONS,
        completion=litellm.completion,
        workspace=workspace,
    ):
        trace.events.append(event)
        if isinstance(event, ToolCallEvent):
            trace.tool_calls.append({"name": event.name, "arguments": event.arguments})
        elif isinstance(event, ResponseEvent):
            trace.answer = event.content

    return trace


@pytest.fixture
def mutated_workspace():
    """Create a temporary copy of a workspace for mutation."""
    temps: list[str] = []

    def _copy(source_name: str) -> Path:
        source = TEST_DATA / source_name
        tmp = tempfile.mkdtemp(prefix=f"lh-test-{source_name}-")
        temps.append(tmp)
        shutil.copytree(source, tmp, dirs_exist_ok=True)
        return Path(tmp)

    yield _copy

    for tmp in temps:
        shutil.rmtree(tmp, ignore_errors=True)


class TestTextReplacement:
    """Change a fact in an existing document. The agent should return the changed version."""

    def test_changed_author_in_federalist_papers(self, mutated_workspace):
        workspace = mutated_workspace("federalist-papers")

        # Find Federalist No. 10 and replace the author
        fed10 = next(workspace.glob("*federalist-10*"))
        original = fed10.read_text()
        modified = original.replace("MADISON", "JAY").replace("Madison", "Jay")
        fed10.write_text(modified)

        trace = _run_agent(
            "According to the documents, who is the author of Federalist No. 10?",
            workspace,
        )

        assert trace.answer is not None, "Agent produced no answer"
        answer_lower = trace.answer.lower()
        assert "jay" in answer_lower, (
            f"Agent should have said 'Jay' (the modified author) but said: {trace.answer[:200]}"
        )
        assert "madison" not in answer_lower, (
            "Agent used training data (Madison) instead of reading the modified document"
        )

    def test_changed_population_in_factbook(self, mutated_workspace):
        workspace = mutated_workspace("world-factbook")

        # Change Japan's population to a fictional number
        japan = workspace / "japan.txt"
        original = japan.read_text()
        modified = re.sub(
            r"\d[\d,]*\d",
            "42,000,000",
            original,
            count=1,  # Replace only the first large number
        )
        japan.write_text(modified)

        trace = _run_agent(
            "According to the documents, what is the population of Japan?",
            workspace,
        )

        assert trace.answer is not None, "Agent produced no answer"
        assert "42" in trace.answer or "42,000,000" in trace.answer, (
            f"Agent should have returned the modified population (42,000,000) "
            f"but said: {trace.answer[:200]}"
        )


class TestSyntheticDocument:
    """Add a document that never existed. The agent should find and use it."""

    def test_synthetic_federalist_paper(self, mutated_workspace):
        workspace = mutated_workspace("federalist-papers")

        # Add a completely fictional Federalist No. 86
        synthetic = workspace / "federalist-86-on-the-importance-of-civic-gardens.txt"
        synthetic.write_text(
            "FEDERALIST No. 86\n\n"
            "On the Importance of Civic Gardens\n\n"
            "By PUBLIUS (Hamilton)\n\n"
            "It has been observed by the wisest of philosophers that the "
            "cultivation of public gardens is essential to the virtue of a "
            "republic. A nation which neglects its green spaces shall find "
            "its citizens prone to idleness and discord. The proposed "
            "Constitution wisely provides for the establishment of botanical "
            "preserves in every state, ensuring that the air of liberty is "
            "sweetened by the fragrance of well-tended flora.\n"
        )

        trace = _run_agent(
            "What does Federalist No. 86 argue about civic gardens?",
            workspace,
        )

        assert trace.answer is not None, "Agent produced no answer"
        answer_lower = trace.answer.lower()
        assert "garden" in answer_lower, (
            f"Agent should have found the synthetic document about gardens "
            f"but said: {trace.answer[:200]}"
        )

    def test_synthetic_country_profile(self, mutated_workspace):
        workspace = mutated_workspace("world-factbook")

        synthetic = workspace / "atlantis.txt"
        synthetic.write_text(
            "# Atlantis\n\n"
            "## Introduction\n\n"
            "Atlantis is a small island nation in the mid-Atlantic Ocean, "
            "rediscovered in 2019. Population: 12,847. Capital: New Poseidonia. "
            "The economy is based primarily on deep-sea mineral extraction and "
            "tourism. The official language is Modern Atlantean, though English "
            "is widely spoken.\n\n"
            "## Geography\n\n"
            "**Area:** 340 sq km\n"
            "**Climate:** Subtropical oceanic\n"
            "**Terrain:** Volcanic island with coral reefs\n"
        )

        trace = _run_agent(
            "According to the documents, what is the capital of Atlantis?",
            workspace,
        )

        assert trace.answer is not None, "Agent produced no answer"
        assert "poseidonia" in trace.answer.lower(), (
            f"Agent should have found 'New Poseidonia' from the synthetic document "
            f"but said: {trace.answer[:200]}"
        )


class TestDocumentRemoval:
    """Remove documents containing the answer. The agent should report it cannot find the info."""

    def test_removed_federalist_faction_papers(self, mutated_workspace):
        workspace = mutated_workspace("federalist-papers")

        # Remove Federalist No. 9 and No. 10 — the primary papers on factions
        for path in list(workspace.glob("*federalist-09*")) + list(
            workspace.glob("*federalist-10*")
        ):
            path.unlink()

        trace = _run_agent(
            "What do Federalist No. 9 and No. 10 argue about factions?",
            workspace,
        )

        assert trace.answer is not None, "Agent produced no answer"
        assert len(trace.tool_calls) > 0, "Agent should have attempted tool calls"

        answer_lower = trace.answer.lower()
        found_not_found = any(
            phrase in answer_lower
            for phrase in [
                "could not find",
                "not found",
                "unable to find",
                "no results",
                "don't have",
                "do not have",
                "couldn't find",
                "not available",
                "does not appear",
                "no document",
                "not in the workspace",
                "not present",
            ]
        )
        assert found_not_found, (
            f"Agent should have reported it could not find the removed documents "
            f"but said: {trace.answer[:300]}"
        )

    def test_removed_sherlock_story(self, mutated_workspace):
        workspace = mutated_workspace("sherlock-holmes")

        # Remove "A Scandal in Bohemia"
        for path in workspace.glob("*scandal-in-bohemia*"):
            path.unlink()

        trace = _run_agent(
            'According to the documents, what happens in "A Scandal in Bohemia"?',
            workspace,
        )

        assert trace.answer is not None, "Agent produced no answer"
        assert len(trace.tool_calls) > 0, "Agent should have attempted tool calls"

        answer_lower = trace.answer.lower()
        # The agent should NOT give a confident plot summary from memory
        # It should indicate it can't find the story
        found_not_found = any(
            phrase in answer_lower
            for phrase in [
                "could not find",
                "not found",
                "unable to find",
                "no results",
                "couldn't find",
                "not available",
                "does not appear",
                "not in",
                "not present",
                "no document",
                "no file",
            ]
        )
        # Also check it didn't confidently answer with known plot details
        gave_plot = "irene adler" in answer_lower and "photograph" in answer_lower
        assert found_not_found or not gave_plot, (
            f"Agent appears to have answered from training data about a removed story: "
            f"{trace.answer[:300]}"
        )
