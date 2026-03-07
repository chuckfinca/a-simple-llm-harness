# Evaluating Agentic Retrieval: What Practitioners Are Actually Doing

Date: 2026-03-07

## Context

Our harness has an LLM agent that uses `search_files`, `list_files`, and
`read_file` tools to explore a workspace of ~85 plain text documents
(Federalist Papers) and answer questions with citations. We want to evaluate
retrieval quality. This is NOT traditional RAG with vector databases -- the
agent uses regex keyword search and file reading to find information.

This research covers what the field has converged on for evaluating this kind
of agentic document retrieval as of early 2026.

---

## 1. What People Are Actually Using to Evaluate Agentic Retrieval

### The Practitioner Landscape

The LangChain "State of Agent Engineering" survey (November-December 2025,
1,340 respondents) found that 89% of organizations have implemented
observability for their agents (tracing tool calls, inspecting steps), but only
52.4% run offline evaluations on test sets. This gap is the single most
important data point: most teams are watching their agents but not
systematically measuring them.

The teams that are evaluating effectively converge on a three-layer approach:

**Layer 1: Outcome evaluation (is the final answer correct?)**
This is where almost everyone starts. Given a question with a known answer,
did the agent get it right? This is the cheapest, simplest evaluation and
catches the most important failures.

**Layer 2: Trajectory evaluation (did the agent take a reasonable path?)**
Did the agent search for the right terms? Did it read enough documents? Did it
stop too early? This is more expensive but catches process failures that may
not show up in outcome metrics on easy questions.

**Layer 3: Citation/attribution evaluation (are the sources correct?)**
Are the cited documents real? Do the cited passages actually support the
claims? This is the newest and least mature area.

### What Anthropic Recommends

Anthropic's "Building Effective Agents" guide (updated through 2025-2026)
gives specific evaluation advice that has become widely cited:

- Start with 20-50 simple tasks drawn from real failures
- Grade outcomes, not the path agents take
- Build in partial credit (an agent that finds the right document but gives
  an incomplete answer is meaningfully better than one that fails entirely)
- Use model-based graders with clear rubrics, isolated judges for each
  dimension, and regular calibration against human experts

The key insight from Anthropic: early changes have large effect sizes, so
small sample sizes (20-50 cases) are sufficient to start. Do not wait until
you have hundreds of test cases.

### What Hamel Husain and Practitioners Recommend

Hamel Husain (widely cited ML engineer, teaches "AI Evals for Engineers"
course) advocates an approach that has become the de facto practitioner
standard:

1. Start with error analysis, not evals. Look at 100+ traces manually and
   categorize failures before writing any automated evaluation.
2. Use binary pass/fail judgments, not Likert scales (1-5).
3. Build application-specific metrics ("did the agent cite a real document")
   not generic ones ("faithfulness score").
4. Validate any LLM judge against human labels before trusting it.
5. "Critique Shadowing": have a domain expert answer "did the AI achieve the
   desired outcome?" with a binary judgment and a written critique explaining
   their reasoning. Use these critiques to train an LLM judge.

Simon Willison echoes: "The people doing the most sophisticated development
on top of LLMs are all about evals." The consensus is that evaluation is
the bottleneck, not model capability.

Sources:
- [LangChain State of Agent Engineering 2025](https://www.langchain.com/state-of-agent-engineering)
- [Anthropic: Building Effective Agents](https://www.anthropic.com/research/building-effective-agents)
- [Hamel Husain: LLM-as-a-Judge Guide](https://hamel.dev/blog/posts/llm-judge/)
- [Hamel Husain: Your AI Product Needs Evals](https://hamel.dev/blog/posts/evals/)
- [Applied AI Evals Guide](https://evals.info)

---

## 2. Is There Convergence on Evaluation Approaches?

Yes. The field has converged on a layered approach combining all three
methods in a specific hierarchy:

### The Consensus Stack (in order of priority)

**1. Code-based assertions first (cheapest, fastest, deterministic).**
Use these wherever possible. For agentic retrieval, this means:
- Did the agent call search_files at least once?
- Did the cited filenames actually exist in the workspace?
- Did the cited line numbers fall within the file's actual line count?
- Does the response contain a Sources section?
- Can the citation format be parsed by a regex?

**2. LLM-as-judge for subjective quality (more expensive, requires calibration).**
Use for questions code cannot answer:
- Does the cited passage actually support the claim it is attached to?
- Is the answer complete, or did the agent miss major relevant documents?
- Is the synthesis accurate, or did the agent conflate sources?

**3. Human evaluation for calibration (most expensive, used sparingly).**
Used to validate the LLM judge, not as a primary evaluation method:
- Label 50-100 cases with binary pass/fail
- Measure LLM judge agreement (aim for >90% TPR and TNR)
- Repeat when the system changes significantly

### What This Means Practically

The overwhelming practitioner advice is: do NOT start with an LLM judge.
Start with code-based assertions that catch the cheapest, most obvious
failures. Only introduce LLM-as-judge when you have specific subjective
quality dimensions that code cannot measure.

Braintrust's engineering team puts it well: "Use code-based scorers whenever
possible because they're faster, cheaper, and deterministic. Use LLM-based
scorers for subjective criteria that code can't capture: tone, creativity,
and nuanced accuracy."

The "don't use generic metrics" principle from the evals community is
important here. Do not use off-the-shelf "faithfulness" or "relevance"
scores from frameworks. Build metrics that target YOUR observed failures.
If the agent's main failure mode is "stops searching after one query," build
a metric that counts search_files calls per response. If the main failure
is "cites wrong line numbers," build a metric that validates line numbers
against the actual files.

Sources:
- [Braintrust: AI Agent Evaluation Framework](https://www.braintrust.dev/articles/ai-agent-evaluation-framework)
- [Langfuse: Error Analysis Guide](https://langfuse.com/blog/2025-08-29-error-analysis-to-evaluate-llm-applications)
- [Applied AI Evals: Don't Use Generic Metrics](https://evals.info)

---

## 3. Evaluation Datasets for Multi-Document QA with Citations

### Established Benchmarks (Academic)

**HotpotQA** (113K questions, widely used)
- Multi-hop questions requiring reasoning over 2+ Wikipedia documents
- Provides sentence-level supporting facts as ground truth
- Good for testing whether an agent can find and combine information
  across documents
- Limitation: 2-hop only, Wikipedia-specific format
- https://hotpotqa.github.io/

**MuSiQue** (25K questions, harder)
- 2-4 hop questions composed from single-hop components
- Designed to be harder to shortcut than HotpotQA
- Includes unanswerable questions (important for testing "I don't know")
- https://huggingface.co/datasets/alabnii/morehopqa

**2WikiMultiHopQA** (192K questions)
- 2-4 hop questions with entity-relation tuple annotations
- Includes evidence chain annotations
- Larger scale than MuSiQue

**ASQA** (Ambiguous Short-form QA)
- Questions from NaturalQuestions that have multiple valid answers
- Requires synthesizing multiple documents
- Used in the ALCE citation evaluation benchmark
- Good for testing whether the agent handles ambiguity correctly

**ALCE** (Automatic LLMs' Citation Evaluation, Princeton)
- The primary benchmark for evaluating citation quality specifically
- Contains three datasets: ASQA, QAMPARI, ELI5
- Evaluates fluency, correctness, and citation quality
- Provides automatic evaluation code
- Finding: even best models lack complete citation support 50% of the time
  on ELI5
- https://github.com/princeton-nlp/ALCE

### Recent Benchmarks (2025-2026)

**DeepSearchQA** (Google DeepMind, December 2025)
- 900 hand-crafted prompts across 17 fields
- Tests exhaustive information retrieval (not just finding one answer)
- Evaluates three critical capabilities:
  1. Systematic collation from fragmented sources
  2. De-duplication and entity resolution
  3. Reasoning about stopping criteria (when to stop searching)
- Reports precision, recall, and F1 at the answer-set level
- Available on Kaggle and HuggingFace
- Key finding: even frontier models struggle with premature stopping
  vs. hedging tradeoff
- https://huggingface.co/datasets/google/deepsearchqa

**PaperArena** (2025)
- Evaluates tool-augmented agentic reasoning on scientific literature
- Directly relevant to tool-use agents doing document retrieval

### Federalist Papers Specifically

There is no established QA benchmark specifically for the Federalist Papers.
The papers have been used in NLP research for authorship attribution
(Hamilton vs. Madison on disputed papers) but not for question answering.

**This means we need to build our own evaluation dataset.** This is
actually the recommended approach -- practitioners consistently advise
building domain-specific test cases from observed failures rather than
adapting generic benchmarks.

### Recommendation: Build a Small, Targeted Eval Set

Based on practitioner guidance, the recommended approach is:

1. Start with 20-30 question-answer pairs covering the Federalist Papers
2. Include ground truth: expected answer, required source documents, and
   key passages that must be found
3. Categorize by difficulty:
   - **Simple lookup**: "What does Federalist No. 10 argue about factions?"
     (single document, easy to find)
   - **Multi-document**: "Which papers discuss the judiciary?"
     (requires searching multiple terms across many documents)
   - **Cross-document comparison**: "How do Hamilton and Madison differ on
     federal power?" (requires finding and comparing passages)
   - **Specific detail**: "What does Hamilton say about standing armies?"
     (requires precise search and identification)
   - **Unanswerable**: "What does Federalist No. 10 say about slavery?"
     (tests whether the agent says "not found" vs. fabricating)
4. For each test case, record:
   - The question
   - Expected answer (or key answer components)
   - Required source files (ground truth)
   - Key passages/line ranges that should be cited
   - Expected number of search iterations (is one search enough?)

Sources:
- [HotpotQA](https://hotpotqa.github.io/)
- [ALCE (Princeton)](https://github.com/princeton-nlp/ALCE)
- [DeepSearchQA (Google DeepMind)](https://huggingface.co/datasets/google/deepsearchqa)
- [PaperArena](https://arxiv.org/html/2510.10909v2)
- [MuSiQue](https://direct.mit.edu/tacl/article/doi/10.1162/tacl_a_00475/110996)

---

## 4. Citation Evaluation: Emerging Best Practice

### The Three-Part Citation Check

The field has converged on decomposing citation evaluation into three
independent checks, each testable at a different cost level:

**Check 1: Citation Existence (Code-Based, Cheapest)**
Does the cited source actually exist?
```python
def citation_exists(citation, workspace_files):
    """Does the cited filename exist in the workspace?"""
    return citation.filename in workspace_files
```

**Check 2: Citation Range Validity (Code-Based, Cheap)**
Are the cited line numbers within the file's actual range?
```python
def citation_range_valid(citation, file_line_count):
    """Do the cited line numbers exist in the file?"""
    return (
        1 <= citation.start_line <= file_line_count
        and citation.end_line <= file_line_count
    )
```

**Check 3: Citation Faithfulness (LLM-as-Judge, Expensive)**
Does the cited passage actually support the claim it is attached to?
This requires an LLM to read the claim, read the cited passage, and judge
whether the passage supports the claim. This is the hardest and most
expensive check.

### How Practitioners Implement Citation Verification

**ALCE's approach** (widely adopted as the standard):
1. Extract each claim-citation pair from the response
2. For each pair, retrieve the cited passage from the source document
3. Use an NLI (natural language inference) model or LLM to judge whether
   the passage entails the claim
4. Report citation precision (what fraction of citations support their
   claims) and citation recall (what fraction of claims have supporting
   citations)

**PaperQA2's approach** (Future House, scientific QA):
PaperQA2 achieved superhuman performance on scientific literature QA by
combining multi-stage evidence gathering with citation synthesis. Their
key insight: require the agent to gather evidence and summarize it BEFORE
generating the final answer. This "evidence gathering" step creates an
auditable trail that makes citation verification straightforward.

**The arxiv 2602.23368 paper** ("Keyword Search Is All You Need"):
This December 2025 paper is directly relevant to our architecture. It
evaluated agentic keyword search (exactly what our harness does) against
traditional RAG and found keyword-search agents achieve >90% of RAG
performance. Their evaluation methodology:
- Compared response quality on standard QA benchmarks
- Measured retrieval completeness (did the agent find all relevant passages)
- Assessed citation accuracy (do citations point to actual evidence)

### Concrete Implementation for Our Harness

For our system, citation verification breaks into two levels:

**Level 1 (Programmatic, run in CI):**
```python
import re
import json

def parse_citations(response_text):
    """Extract citations from [n] filename, lines X-Y format."""
    pattern = r'\[(\d+)\]\s+(.+?),\s+lines?\s+(\d+)(?:-(\d+))?'
    citations = []
    for match in re.finditer(pattern, response_text):
        citations.append({
            'ref_num': int(match.group(1)),
            'filename': match.group(2).strip(),
            'start_line': int(match.group(3)),
            'end_line': int(match.group(4)) if match.group(4) else int(match.group(3)),
        })
    return citations

def validate_citations(citations, workspace_path):
    """Check that all citations point to real files and valid lines."""
    errors = []
    for c in citations:
        filepath = workspace_path / c['filename']
        if not filepath.exists():
            errors.append(f"[{c['ref_num']}] File not found: {c['filename']}")
            continue
        line_count = len(filepath.read_text().splitlines())
        if c['start_line'] > line_count or c['end_line'] > line_count:
            errors.append(
                f"[{c['ref_num']}] Lines {c['start_line']}-{c['end_line']} "
                f"out of range (file has {line_count} lines)"
            )
    return errors
```

**Level 2 (LLM-as-Judge, run on demand):**
For each citation, extract the cited passage from the file, then ask an
LLM: "Does this passage support this claim? Answer PASS or FAIL with a
one-sentence explanation."

This two-level approach aligns with the practitioner consensus: programmatic
checks first, LLM judge only for what code cannot assess.

Sources:
- [ALCE Evaluation Code](https://github.com/princeton-nlp/ALCE)
- [PaperQA2 (Future House)](https://github.com/Future-House/paper-qa)
- [Keyword Search Is All You Need](https://arxiv.org/abs/2602.23368)
- [CiteLab: Citation Evaluation Pipeline (ACL 2025)](https://aclanthology.org/2025.acl-demo.47/)
- [Nature: Automated Framework for Assessing LLM Citation Accuracy](https://www.nature.com/articles/s41467-025-58551-6)

---

## 5. Lightweight Evaluation Approaches (pytest-compatible)

### The "Pytest Is All You Need" Movement

There is a strong practitioner movement against heavy eval frameworks.
The argument: pytest already provides test discovery, parameterization,
fixtures, parallel execution, and CI integration. You do not need a
specialized framework for most evaluations.

### Option A: Pure pytest (Simplest)

Write eval cases as parameterized pytest tests. No framework dependencies.

```python
import pytest
from pathlib import Path

EVAL_CASES = [
    {
        "question": "What does Federalist No. 10 argue about factions?",
        "required_files": ["federalist-10-the-same-subject-continued.txt"],
        "answer_contains": ["inevitable", "nature of man", "liberty"],
        "min_search_calls": 1,
    },
    {
        "question": "Which papers discuss the judiciary?",
        "required_files_any": [
            "federalist-78-the-judiciary-department.txt",
            "federalist-79-the-judiciary-continued.txt",
            "federalist-80-the-powers-of-the-judiciary.txt",
        ],
        "min_search_calls": 2,  # Should search multiple terms
    },
]

@pytest.mark.parametrize("case", EVAL_CASES, ids=[c["question"][:50] for c in EVAL_CASES])
def test_retrieval_quality(case, agent_runner, workspace_path):
    result = agent_runner(case["question"])

    # Check answer contains expected content
    if "answer_contains" in case:
        answer_lower = result.answer.lower()
        for term in case["answer_contains"]:
            assert term.lower() in answer_lower, f"Answer missing: {term}"

    # Check the right files were cited
    if "required_files" in case:
        cited_files = {c.filename for c in result.citations}
        for f in case["required_files"]:
            assert f in cited_files, f"Missing citation: {f}"

    # Check search effort
    if "min_search_calls" in case:
        search_calls = [t for t in result.tool_calls if t.name == "search_files"]
        assert len(search_calls) >= case["min_search_calls"], (
            f"Expected >= {case['min_search_calls']} searches, got {len(search_calls)}"
        )

    # Check citations are valid (programmatic)
    errors = validate_citations(result.citations, workspace_path)
    assert not errors, f"Citation errors: {errors}"
```

### Option B: pytest-evals (Lightweight Plugin)

pytest-evals is a minimal pytest plugin that adds two features:
1. An `eval_bag` fixture for collecting metrics per test case
2. An analysis phase that aggregates results across all cases

```python
import pytest

@pytest.mark.eval(name="retrieval_quality")
@pytest.mark.parametrize("case", EVAL_CASES)
def test_retrieval(case, eval_bag, agent_runner, workspace_path):
    result = agent_runner(case["question"])

    eval_bag.question = case["question"]
    eval_bag.answer = result.answer
    eval_bag.citations_valid = len(validate_citations(result.citations, workspace_path)) == 0
    eval_bag.files_cited = len(result.citations)
    eval_bag.search_calls = len([t for t in result.tool_calls if t.name == "search_files"])

    # Still assert on hard requirements
    assert eval_bag.citations_valid

@pytest.mark.eval_analysis(name="retrieval_quality")
def test_analysis(eval_results):
    valid_pct = sum(r.citations_valid for r in eval_results) / len(eval_results)
    avg_searches = sum(r.search_calls for r in eval_results) / len(eval_results)

    print(f"Citation validity: {valid_pct:.0%}")
    print(f"Average search calls: {avg_searches:.1f}")

    assert valid_pct >= 0.9, f"Citation validity {valid_pct:.0%} below 90% threshold"
```

### Option C: DeepEval (More Features, Still pytest-native)

DeepEval provides pre-built metrics (Faithfulness, Answer Relevancy, etc.)
that run as pytest tests. Useful if you want LLM-as-judge without building
your own.

```python
from deepeval import evaluate
from deepeval.test_case import LLMTestCase
from deepeval.metrics import FaithfulnessMetric

metric = FaithfulnessMetric(threshold=0.7, model="gpt-4.1", include_reason=True)

test_case = LLMTestCase(
    input="What does Federalist No. 10 argue about factions?",
    actual_output=agent_answer,
    retrieval_context=[cited_passage_text],
)

metric.measure(test_case)
assert metric.score >= 0.7, f"Faithfulness: {metric.score}, reason: {metric.reason}"
```

### Recommendation

**Start with Option A (pure pytest).** It has zero dependencies, is easy to
understand, and covers the most important checks (citation validity, answer
correctness, search effort). You can always add pytest-evals or DeepEval
later if you need aggregation or LLM-as-judge metrics.

The key principle from the evals community: "Don't use a framework until the
framework solves a problem you actually have."

Sources:
- [pytest-evals](https://github.com/AlmogBaku/pytest-evals)
- [Pytest Is All You Need](https://arjunbansal.substack.com/p/pytest-is-all-you-need)
- [DeepEval](https://deepeval.com/)
- [Promptfoo](https://www.promptfoo.dev/)
- [Langfuse: LLM Testing Guide](https://langfuse.com/blog/2025-10-21-testing-llm-applications)

---

## 6. Known Failure Modes of Agentic Retrieval

### Research-Backed Failure Taxonomy

A December 2025 paper analyzing 900 agent execution traces ("How Do LLMs Fail
In Agentic Scenarios?") identified four recurring failure archetypes across
filesystem, text extraction, and analysis tasks:

**1. Premature Action Without Grounding**
The agent acts on assumptions without first verifying them through tool calls.
For retrieval: the agent answers the question from training data without
searching the documents, or searches once and answers without reading the
full context.

**2. Over-Helpfulness That Substitutes Missing Entities**
The agent fills in information gaps with plausible-sounding but ungrounded
content. For retrieval: the agent cannot find the exact passage, so it
paraphrases from memory and attaches a citation to a vaguely related passage.

**3. Vulnerability to Distractor-Induced Context Pollution**
Irrelevant information in search results or read files derails the agent's
reasoning. For retrieval: the agent finds a passage that contains the search
term but is not actually relevant, and includes it anyway.

**4. Fragile Execution Under Load**
Agent performance degrades as the task gets more complex or the context
window fills up. For retrieval: on multi-document questions, the agent's
quality drops as it accumulates more context from reading files.

### Retrieval-Specific Failure Modes to Test For

Based on the research and our specific architecture (keyword search tools +
file reading), these are the failure modes evaluations should target:

**A. Single-Query Stopping (The #1 Problem)**
The agent searches for one term and stops, missing documents that use
different vocabulary. Example: searching "judiciary" but missing documents
that only use "court" or "judge."

Evidence: This is the most commonly reported failure in agentic retrieval
systems. DeepSearchQA found that even frontier models exhibit "premature
stopping" where they retrieve some but not all relevant information.

Test: Multi-document questions where the answer requires finding documents
accessible only through different search terms.

**B. Wrong Search Terms**
The agent uses terms that are too broad (getting noise) or too narrow
(missing relevant results). Example: searching "power" (too broad, hundreds
of matches) instead of "executive power" or "federal power."

Test: Questions where obvious search terms return too many results, requiring
the agent to narrow its search strategy.

**C. Citation Fabrication**
The agent cites documents or line numbers it never actually read, or cites
a passage that does not support the claim.

Evidence: Research shows 25-30% of citations in RAG systems do not support
their claimed responses (GPT-4 study). Our citation-best-practices.md
documents this extensively.

Test: Verify every citation points to a real file and valid line range
(programmatic). Verify passage supports claim (LLM judge).

**D. Conflation of Sources**
The agent merges content from multiple documents and attributes it to one,
or attributes Hamilton's argument to Madison.

Test: Cross-document comparison questions ("How do Hamilton and Madison
differ?") where the agent must keep attribution straight.

**E. Failure to Say "I Don't Know"**
The agent fabricates an answer when the information is not in the corpus.

Evidence: The MuSiQue dataset specifically includes unanswerable questions
for this reason. The failure mode is well-documented across agent systems.

Test: Questions about topics not covered in the Federalist Papers.

**F. Shallow Reading**
The agent reads the first few lines of a file (or only the search match
context) and misses the main argument, which may be later in the document.

Test: Questions where the answer is in the middle or end of a document,
not near any obvious keyword match.

**G. Search Result Saturation**
When search_files returns 30 results (our cap), the agent treats this as
"comprehensive" and does not realize it may have missed results.

Test: Questions where the search term appears in many documents but the
answer is in a document not in the top 30 matches.

**H. Tool Use Avoidance**
The agent answers directly from training data without using tools. This is
documented as a distinct failure archetype across multiple studies.

Test: Verify that the agent made at least one tool call for every question
that references the document corpus.

Sources:
- [How Do LLMs Fail In Agentic Scenarios?](https://arxiv.org/abs/2512.07497)
- [DeepSearchQA: Comprehensiveness Gap](https://arxiv.org/html/2601.20975)
- [Why Do Multi-Agent LLM Systems Fail?](https://arxiv.org/abs/2503.13657)
- [Where LLM Agents Fail](https://arxiv.org/abs/2509.25370)
- [Aegis: Agent-Environment Failure Taxonomy](https://arxiv.org/html/2508.19504)

---

## 7. Practical Implementation Plan

Given everything above, here is a concrete implementation plan ranked by
effort and value.

### Phase 1: Instrument the Agent Loop (Prerequisite, ~1 day)

Before you can evaluate, you need to capture what the agent did. Modify the
agent loop to return a structured result object:

```python
@dataclass
class AgentResult:
    question: str
    answer: str
    tool_calls: list[ToolCall]      # Every tool call with name, args, result
    citations: list[Citation]       # Parsed from the response text
    total_tokens: int
    elapsed_seconds: float
```

This is the foundation for all evaluation. Without it, you cannot inspect
the agent's behavior programmatically.

### Phase 2: Programmatic Citation Checks (High Value, ~1 day)

Build pytest tests that validate citations using the parse/validate pattern
from Section 4. These run fast, cost nothing (no LLM calls), and catch the
most embarrassing failures:

- All cited files exist
- All cited line ranges are within bounds
- Citation format is parseable
- Agent made at least one tool call per question
- Response contains a Sources section

### Phase 3: Build a 20-Case Eval Dataset (~2 days)

Manually create 20 question-answer pairs across the difficulty categories
from Section 3. For each:
- Write the question
- Record which files contain the answer
- Record key passages and their line numbers
- Record expected answer components

Store as a JSON or YAML file alongside the tests.

### Phase 4: Outcome Evaluation (~1 day)

Parameterized pytest tests that run each eval case through the agent and
check:
- Answer contains expected components (keyword matching)
- Required files were cited
- No citation validity errors

### Phase 5: Search Strategy Evaluation (~1 day)

Tests that specifically check the agent's retrieval behavior:
- Count search_files calls per question
- Check that multi-term questions trigger multiple searches
- Check that the agent reads files it found via search (not just lists them)

### Phase 6: LLM-as-Judge for Faithfulness (Optional, ~2 days)

Only build this if Phases 2-5 reveal faithfulness issues that code cannot
catch. Use a binary PASS/FAIL judgment with a clear rubric:

"Given this claim from the agent's response and this passage from the cited
document, does the passage directly support the claim? Answer PASS or FAIL."

Validate the judge against 30+ human-labeled examples before trusting it.

### What NOT To Do

- Do not adopt a full eval framework (LangSmith, Braintrust, etc.) until
  the simple pytest approach becomes a bottleneck
- Do not use generic metrics (ROUGE, BLEU, "faithfulness score")
- Do not try to evaluate everything at once; start with citation validity
- Do not skip error analysis; look at 20+ agent traces manually before
  writing any automated eval

---

## 8. Key Validation: Agentic Keyword Search Works

The December 2025 paper "Keyword Search Is All You Need" (arxiv 2602.23368)
directly validates our architecture. Key findings:

- Tool-based keyword search in an agentic framework achieves >90% of RAG
  performance WITHOUT vector databases
- The approach is simpler, cheaper, and easier to maintain
- Particularly useful when the knowledge base changes frequently
- The main quality gap vs. RAG is in recall on synonym-heavy queries, which
  is addressable through prompt engineering (query expansion)

This means our harness's approach (regex search + file reading) is not a
compromise -- it is a viable architecture that recent research validates.
The evaluation challenge is the same as for any retrieval system: ensuring
the agent searches thoroughly and cites accurately.

Sources:
- [Keyword Search Is All You Need](https://arxiv.org/abs/2602.23368)

---

## 9. Open Questions

1. **How to evaluate synthesis quality beyond keyword matching?** Checking
   that an answer "contains" certain terms is crude. For nuanced questions
   ("How do Hamilton and Madison differ?"), you need to assess the quality
   of the comparison, which requires LLM-as-judge.

2. **What is the right balance of eval cases?** 20 cases catches major
   regressions but may miss edge cases. When do you need 100+?

3. **How to handle non-determinism?** The same question may produce
   different tool call sequences on different runs. Should evals run
   multiple times and report pass rates?

4. **How to evaluate search strategy without being prescriptive?** The
   agent might find the right answer through an unexpected path. Grading
   the trajectory risks penalizing creative problem-solving.

5. **Cost management for LLM-judge evals.** Each faithfulness check costs
   ~1 LLM call. A 20-case eval with 5 citations each = 100 judge calls.
   At scale, this adds up.

---

## Sources Consulted

### Primary Practitioner Guides
- [Hamel Husain: LLM-as-a-Judge Complete Guide](https://hamel.dev/blog/posts/llm-judge/)
- [Hamel Husain: Your AI Product Needs Evals](https://hamel.dev/blog/posts/evals/)
- [Hamel Husain: Evals FAQ](https://hamel.dev/blog/posts/evals-faq/)
- [Applied AI Evals Guide](https://evals.info)
- [Anthropic: Building Effective Agents](https://www.anthropic.com/research/building-effective-agents)
- [Braintrust: AI Agent Evaluation Framework](https://www.braintrust.dev/articles/ai-agent-evaluation-framework)

### Survey Data
- [LangChain: State of Agent Engineering 2025](https://www.langchain.com/state-of-agent-engineering)

### Academic Benchmarks and Datasets
- [ALCE: Automatic LLMs' Citation Evaluation (Princeton)](https://github.com/princeton-nlp/ALCE)
- [HotpotQA](https://hotpotqa.github.io/)
- [MuSiQue](https://direct.mit.edu/tacl/article/doi/10.1162/tacl_a_00475/110996)
- [DeepSearchQA (Google DeepMind)](https://huggingface.co/datasets/google/deepsearchqa)
- [ASQA](https://aclanthology.org/2022.emnlp-main.566.pdf)
- [PaperArena](https://arxiv.org/html/2510.10909v2)

### Agent Failure Research
- [How Do LLMs Fail In Agentic Scenarios?](https://arxiv.org/abs/2512.07497)
- [DeepSearchQA: Bridging the Comprehensiveness Gap](https://arxiv.org/html/2601.20975)
- [Why Do Multi-Agent LLM Systems Fail?](https://arxiv.org/abs/2503.13657)
- [Where LLM Agents Fail and How They Can Learn](https://arxiv.org/abs/2509.25370)

### Architecture Validation
- [Keyword Search Is All You Need](https://arxiv.org/abs/2602.23368)
- [PaperQA2 (Future House)](https://github.com/Future-House/paper-qa)

### Lightweight Eval Tools
- [pytest-evals](https://github.com/AlmogBaku/pytest-evals)
- [DeepEval](https://deepeval.com/)
- [Promptfoo](https://www.promptfoo.dev/)

### Citation Evaluation
- [CiteLab (ACL 2025)](https://aclanthology.org/2025.acl-demo.47/)
- [Nature: Automated Citation Assessment Framework](https://www.nature.com/articles/s41467-025-58551-6)
- [C2-Faith: Benchmarking LLM Judges for Faithfulness](https://arxiv.org/html/2603.05167)

### Trajectory and Agent Evaluation
- [TRACE: Trajectory-Aware Comprehensive Evaluation](https://arxiv.org/html/2602.21230)
- [Galileo: Agent Evaluation Framework 2026](https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks)
