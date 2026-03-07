# Evaluating Retrieval Quality in Tool-Based LLM Agent Harnesses

How to evaluate whether an LLM agent that uses tool-based document search
(list_files, search_files, read_file) retrieves the right information and
cites it accurately. Focused on practical approaches for a small harness
with ~85 Federalist Papers text files.

---

## 1. Existing Benchmarks and Datasets

### Directly Relevant: ToolQA

ToolQA is the closest existing benchmark to our use case. It evaluates LLMs'
ability to answer questions using external tools (search, read, filter)
rather than internal knowledge. Key properties:

- Questions are designed so LLMs cannot answer from memory alone
- Each instance is a tuple of (question, answer, reference corpora, tools)
- Two difficulty levels (easy/hard) across 8 domains
- Requires compositional use of multiple tools
- LLMs using only internal knowledge score ~5% on easy, ~2% on hard
- Available on GitHub: github.com/night-chen/ToolQA

**Relevance to us**: High conceptual relevance, but the actual data domains
(flight info, coffee shop reviews, etc.) do not overlap with our corpus.
The dataset design methodology -- ensuring questions require tool use -- is
directly applicable to crafting our own eval set.

Source: [ToolQA: A Dataset for LLM Question Answering with External Tools](https://arxiv.org/abs/2306.13304) (NeurIPS 2023)

### Multi-Hop Retrieval: HotpotQA

HotpotQA is the gold standard for multi-hop question answering with ground
truth evidence:

- 112,779 Wikipedia-based Q&A pairs with sentence-level supporting evidence
- Questions require finding and reasoning over multiple source documents
- Provides ground truth "supporting facts" (specific sentences used to
  create the question)
- Two settings: "distractor" (10 passages given) and "full wiki" (open)
- Evaluation uses EM (exact match) and F1 on answer tokens, plus a separate
  supporting-fact F1 metric

**Relevance to us**: The supporting-fact evaluation is directly applicable.
We could adapt this approach: for each test question, annotate which
files/passages should be found, then measure whether the agent found them.

Source: [HotpotQA: A Dataset for Diverse, Explainable Multi-hop Question Answering](https://hotpotqa.github.io/)

### Multi-Hop Retrieval: MultiHop-RAG

A newer benchmark specifically for multi-hop retrieval across documents:

- Knowledge base of English news articles (Sept-Dec 2023)
- Multi-hop queries with ground-truth answers and supporting evidence
- Four query types: Inference, Comparison, Temporal, and Null
- Five-step quality pipeline for dataset construction

**Relevance to us**: The query type taxonomy (comparison, temporal, inference)
is useful for designing varied test cases over the Federalist Papers.

Source: [MultiHop-RAG](https://github.com/yixuantt/MultiHop-RAG) (COLM 2024)

### Citation Evaluation: ALCE

ALCE (Automatic LLMs' Citation Evaluation) from Princeton is the primary
benchmark for evaluating citation quality:

- Three datasets: ASQA, QAMPARI, ELI5
- Metrics along three dimensions: fluency, correctness, citation quality
- Citation quality measured by whether cited passages actually support claims
- Automatic metrics correlate strongly with human judgments
- Uses NLI (Natural Language Inference) models for citation verification

**Relevance to us**: The citation quality metrics are directly applicable.
The NLI-based verification approach (checking whether a cited passage
entails the claim) could be adapted for our use case without requiring an
LLM judge.

Source: [ALCE: Enabling Large Language Models to Generate Text with Citations](https://github.com/princeton-nlp/ALCE) (EMNLP 2023)

### Classical QA: SQuAD and TriviaQA

These are large-scale reading comprehension benchmarks:

- SQuAD 2.0: 150K Q&A pairs over Wikipedia paragraphs, with unanswerable
  questions. Evaluation script provided (EM + F1).
- TriviaQA: 95K Q&A pairs with ~6 evidence documents per question.

**Relevance to us**: Low for direct use, but the evaluation methodology
(exact match + token-level F1) is a proven pattern for answer correctness
checking that does not require an LLM judge.

### No Existing Federalist Papers QA Dataset

There is no existing question-answer evaluation dataset for the Federalist
Papers. The papers are widely used in NLP for authorship attribution
(Mosteller-Wallace studies from the 1960s onward), but not for QA
benchmarking. We will need to create our own eval set.

Available resources for creating one:
- GradeSaver study guide with 100 quiz questions across essays
- CliffsNotes summaries and analysis by section
- Library of Congress research guides with full text
- Various university teaching materials with discussion questions
- The Kaggle Federalist Papers dataset (raw text, JSON format)

Sources:
- [GradeSaver Federalist Papers Study Guide](https://www.gradesaver.com/the-federalist-papers)
- [Kaggle Federalist Papers Dataset](https://www.kaggle.com/datasets/tobyanderson/federalist-papers)
- [Library of Congress Full Text](https://guides.loc.gov/federalist-papers/full-text)

---

## 2. Evaluation Metrics

### Tier 1: Programmatic Metrics (No LLM Required)

These can run as fast, deterministic pytest assertions.

#### Document Recall

Did the agent find the right files?

```
recall = |retrieved_files intersection expected_files| / |expected_files|
```

For each test case, define a set of expected source files. After the agent
runs, extract which files it actually read (from tool call logs). Compute
recall. This is the single most important retrieval metric for our harness.

#### Document Precision

Did the agent avoid reading irrelevant files?

```
precision = |retrieved_files intersection expected_files| / |retrieved_files|
```

Less critical than recall (reading an extra file is less harmful than missing
a key one), but useful for measuring search efficiency.

#### Citation File Accuracy

Did the agent cite the right file in its answer?

Parse the agent's output for citation references (our format:
`[1] federalist-10-....txt, lines 42-58`). Check whether each cited file
is in the expected source set. This is a programmatic string-matching check.

```
citation_accuracy = |cited_files intersection expected_files| / |cited_files|
```

#### Citation Precision (Source Verification)

For each citation, does the cited passage actually exist at the stated
location? Read the cited file at the cited line range and verify the text
is not empty/nonsensical. This catches fabricated line numbers.

```python
def verify_citation_exists(file_path, start_line, end_line, workspace):
    """Check that the cited text region exists and is non-trivial."""
    lines = Path(workspace / file_path).read_text().splitlines()
    cited_text = "\n".join(lines[start_line-1:end_line])
    return len(cited_text.strip()) > 20  # not empty/trivial
```

#### Answer Contains Expected Keywords

For factual questions with known answers, check for expected keywords or
phrases in the output. Not a full correctness check, but catches gross
failures.

```python
def answer_contains_keywords(answer: str, expected: list[str]) -> bool:
    answer_lower = answer.lower()
    return all(kw.lower() in answer_lower for kw in expected)
```

#### Search Efficiency

Count the number of tool calls the agent made. For a given question
difficulty, compare against an expected budget:
- Simple lookup: 2-4 tool calls (1 search + 1-2 reads)
- Multi-file question: 4-8 tool calls
- Broad exploration: 8-15 tool calls

This metric catches both over-searching (wasting tokens) and under-searching
(giving up too early).

#### Answer Token-Level F1 (SQuAD-Style)

For questions with a known short answer, compute token overlap:

```python
def token_f1(prediction: str, reference: str) -> float:
    pred_tokens = set(prediction.lower().split())
    ref_tokens = set(reference.lower().split())
    if not ref_tokens:
        return 1.0 if not pred_tokens else 0.0
    common = pred_tokens & ref_tokens
    if not common:
        return 0.0
    precision = len(common) / len(pred_tokens)
    recall = len(common) / len(ref_tokens)
    return 2 * precision * recall / (precision + recall)
```

### Tier 2: NLI-Based Metrics (Small Model, Not Full LLM)

These use a small classification model, not a large LLM, so they are fast
and cheap.

#### Citation Faithfulness via NLI

Following the ALCE approach: for each claim-citation pair, use a Natural
Language Inference model (e.g., `cross-encoder/nli-deberta-v3-base` from
HuggingFace) to check whether the cited passage entails the claim.

- Extract each claim sentence from the answer
- Extract the corresponding cited passage from the source file
- Run NLI: does the passage entail the claim?
- Score: fraction of claims where citation entails the claim

This is significantly more reliable than substring matching for semantic
verification, but does not require calling an expensive LLM API.

#### Retrieval Relevance via Embedding Similarity

Compute cosine similarity between the question and each retrieved passage
using a small embedding model (e.g., `all-MiniLM-L6-v2`). Threshold at
a relevance cutoff.

This is supplementary -- the programmatic document recall metric is more
directly useful for our case since we know the expected files.

### Tier 3: LLM-as-Judge (When Needed)

Use sparingly. Best reserved for evaluating qualities that cannot be
checked programmatically.

#### Answer Faithfulness

"Is the answer supported by the passages the agent read, or does it contain
information not found in those passages?"

This is the one metric where LLM-as-judge provides clear value over
alternatives. Feed the judge the agent's answer plus all passages the
agent actually read, and ask a binary question: "Does every factual claim
in the answer appear in the provided passages? Yes/No."

Per Hamel Husain's guidance: use binary (pass/fail), not Likert scales.
Validate the judge against human labels on a small set (20-40 examples).
Aim for >90% TPR and TNR against human judgment.

#### When NOT to Use LLM-as-Judge

- Document recall: deterministic, use set intersection
- Citation file accuracy: deterministic, use string parsing
- Citation existence: deterministic, check file contents
- Answer keywords: deterministic, use string matching
- Search efficiency: deterministic, count tool calls

Source: [Hamel Husain - LLM Evals FAQ](https://hamel.dev/blog/posts/evals-faq/)

---

## 3. Evaluation Frameworks and Tools

### DeepEval (Best Fit for Our Use Case)

DeepEval is the most practical framework for our harness. Key features:

- Pytest-native: `pip install deepeval`, write tests like pytest
- `ToolCorrectnessMetric`: compares called tools vs expected tools
- `LLMTestCase` supports `tools_called` and `expected_tools` fields
- Can run without LLM judges for tool-correctness checks
- Parametrized test cases from JSON/CSV files

Example of tool correctness evaluation:

```python
from deepeval.test_case import LLMTestCase, ToolCall
from deepeval.metrics import ToolCorrectnessMetric

test_case = LLMTestCase(
    input="What does Federalist No. 10 argue about factions?",
    actual_output=agent_response,
    tools_called=[
        ToolCall(name="search_files"),
        ToolCall(name="read_file"),
    ],
    expected_tools=[
        ToolCall(name="search_files"),
        ToolCall(name="read_file"),
    ],
)
metric = ToolCorrectnessMetric()
```

**Caveat**: DeepEval's RAG-specific metrics (faithfulness, contextual
recall) assume a standard RAG pipeline where you pass `retrieval_context`.
For our tool-based system, we would need to extract the retrieval context
from tool call results and pass it in -- possible but requires adapter code.

Source: [DeepEval Tool Correctness](https://deepeval.com/docs/metrics-tool-correctness)

### RAGAS

RAGAS is primarily designed for vector-embedding RAG evaluation. Its core
metrics (faithfulness, answer relevancy, context precision/recall) can
technically be adapted, but they assume you pass in the retrieved contexts
directly. For a tool-based agent, you need to:

1. Run the agent and capture tool call results
2. Assemble retrieved contexts from search/read results
3. Pass them to RAGAS metrics

This is more friction than it is worth for our simple harness. RAGAS is
better suited for teams with a traditional RAG pipeline.

Source: [RAGAS: Automated Evaluation of Retrieval Augmented Generation](https://arxiv.org/abs/2309.15217)

### Braintrust

Braintrust provides agent-specific evaluation with tool-call tracing:

- Records tool invocations, arguments, and results
- Supports custom scoring functions (code-based graders)
- Side-by-side experiment comparison
- TypeScript and Python SDKs

Better suited for teams at scale who want a hosted platform. For our
minimal harness, custom pytest is simpler.

Source: [Braintrust AI Agent Evaluation](https://www.braintrust.dev/articles/ai-agent-evaluation-framework)

### LangSmith / LangChain agentevals

LangChain's `agentevals` package provides trajectory evaluators:

- Compare agent's tool call sequence against a reference trajectory
- Deterministic, fast, no LLM calls needed
- Can assert "tool X was called at some point" without caring about order

This is a good pattern but brings in the LangChain dependency. We can
implement the same checks ourselves in ~20 lines of Python.

Source: [LangChain: Evaluating Deep Agents](https://blog.langchain.com/evaluating-deep-agents-our-learnings/)

### Recommendation: Start with Custom Pytest, Graduate to DeepEval

For our minimal harness with 85 files:

1. **Start with custom pytest** -- hand-crafted test cases with expected
   files, keywords, and tool call budgets. No dependencies.
2. **Add DeepEval** when we want tool correctness metrics or LLM-as-judge
   for faithfulness checks.
3. **Skip RAGAS and Braintrust** -- more complexity than value at our scale.

---

## 4. Practical Approaches for Our Harness

### Approach A: The Ground-Truth File Set (Recommended Starting Point)

The simplest useful eval. Zero additional dependencies.

**Step 1**: Create 20-30 test cases as a JSON file:

```json
[
  {
    "id": "faction_argument",
    "question": "What does Federalist No. 10 argue about factions?",
    "expected_files": [
      "federalist-10-the-same-subject-continued.txt"
    ],
    "expected_keywords": ["faction", "republic", "democracy"],
    "difficulty": "simple",
    "max_tool_calls": 5
  },
  {
    "id": "judiciary_papers",
    "question": "Which papers discuss the judiciary?",
    "expected_files": [
      "federalist-79-the-judiciary-department.txt",
      "federalist-80-the-judiciary-continued.txt",
      "federalist-81-the-powers-of-the-judiciary.txt",
      "federalist-82-the-judiciary-continued-and-the-distribution-of-the-judicial.txt",
      "federalist-83-the-judiciary-continued.txt",
      "federalist-84-the-judiciary-continued-in-relation-to-trial-by-jury.txt"
    ],
    "expected_keywords": ["judiciary", "court", "judicial"],
    "min_expected_recall": 0.5,
    "difficulty": "multi_file",
    "max_tool_calls": 12
  },
  {
    "id": "standing_armies",
    "question": "What does Hamilton say about standing armies?",
    "expected_files": [
      "federalist-24-the-powers-necessary-to-the-common-defense-further-considere.txt",
      "federalist-25-the-same-subject-continued.txt",
      "federalist-26-the-idea-of-restraining-the-legislative-authority-in-regard-.txt",
      "federalist-29-concerning-the-militia.txt"
    ],
    "expected_keywords": ["army", "armies", "military", "standing"],
    "difficulty": "specific_detail",
    "max_tool_calls": 10
  },
  {
    "id": "hamilton_madison_federal_power",
    "question": "How do Hamilton and Madison differ on federal power?",
    "expected_files": [
      "federalist-45-the-alleged-danger-from-the-powers-of-the-union-to-the-state.txt",
      "federalist-46-the-influence-of-the-state-and-federal-governments-compared.txt",
      "federalist-23-the-necessity-of-a-government-as-energetic-as-the-one-propos.txt"
    ],
    "expected_keywords": ["federal", "state", "power"],
    "difficulty": "cross_document_comparison",
    "max_tool_calls": 15
  }
]
```

**Step 2**: Write a test runner that:

1. Runs the agent on each question (or replays recorded tool calls)
2. Extracts which files were read from tool call logs
3. Computes document recall against expected_files
4. Checks expected keywords in the final answer
5. Counts tool calls against budget
6. Parses citations and verifies cited files exist

**Step 3**: Run as `pytest tests/test_retrieval_eval.py`

### Approach B: Citation Verification Pipeline

Builds on Approach A to verify citation quality programmatically.

**Step 1**: Parse citations from agent output using regex:

```python
import re

CITATION_PATTERN = re.compile(
    r"\[(\d+)\]\s+([\w\-]+\.txt),\s+lines?\s+(\d+)(?:-(\d+))?"
)

def parse_citations(answer: str) -> list[dict]:
    citations = []
    for match in CITATION_PATTERN.finditer(answer):
        citations.append({
            "ref_num": int(match.group(1)),
            "file": match.group(2),
            "start_line": int(match.group(3)),
            "end_line": int(match.group(4)) if match.group(4) else int(match.group(3)),
        })
    return citations
```

**Step 2**: For each citation, verify the text exists:

```python
def verify_citation(citation: dict, workspace: Path) -> dict:
    file_path = workspace / citation["file"]
    if not file_path.exists():
        return {"valid": False, "reason": "file_not_found"}
    lines = file_path.read_text().splitlines()
    start = citation["start_line"] - 1
    end = citation["end_line"]
    if start >= len(lines) or end > len(lines):
        return {"valid": False, "reason": "lines_out_of_range"}
    cited_text = "\n".join(lines[start:end])
    if len(cited_text.strip()) < 10:
        return {"valid": False, "reason": "cited_text_too_short"}
    return {"valid": True, "cited_text": cited_text}
```

**Step 3**: Aggregate citation metrics:

- citation_existence_rate: fraction of citations pointing to real text
- citation_file_accuracy: fraction citing files in expected set
- citation_count: number of citations (too few = under-cited, too many =
  padding)

### Approach C: Trace-Based Evaluation (For Regression Testing)

Record the full tool call trace from a "golden" run, then compare future
runs against it.

**Step 1**: Instrument the agent loop to log tool calls:

```python
@dataclass
class ToolCallRecord:
    tool_name: str
    arguments: dict
    result: str

def run_agent_with_trace(question: str) -> tuple[str, list[ToolCallRecord]]:
    trace = []
    # ... agent loop, appending each tool call to trace ...
    return final_answer, trace
```

**Step 2**: Save golden traces to JSON files per test case.

**Step 3**: For regression testing, compare new trace against golden:
- Were the same files searched/read? (order does not matter)
- Was the final answer consistent? (keyword overlap, not exact match)
- Did tool call count stay within budget?

This catches regressions when changing prompts, switching models, or
modifying tool descriptions. It does NOT require calling the LLM again --
you can replay from saved traces.

Per the LangChain team's experience: "A very common way to evaluate a
full trajectory is to ensure that a particular tool was called at some
point during action, but it doesn't matter exactly when."

Source: [LangChain: Evaluating Deep Agents](https://blog.langchain.com/evaluating-deep-agents-our-learnings/)

### Approach D: Deterministic Replay for Fast CI

Following the deterministic replay pattern described by sakurasky.com and
validated by LangChain's engineering blog:

1. Record HTTP request/response pairs (LLM API calls) using `vcrpy` or
   a similar cassette-based approach
2. Replay them in CI without hitting the LLM API
3. Run all programmatic checks (document recall, citation verification,
   keyword presence) against the replayed output

This makes evals fast (<1 second per test case), free (no API calls), and
deterministic. The tradeoff: replayed tests do not catch regressions from
model changes or prompt changes -- they only verify that your evaluation
infrastructure works correctly and that your parsing/verification logic
is sound.

Run live evals (hitting the real API) on a schedule (nightly or pre-merge)
and average scores across 3+ runs to handle non-determinism.

Sources:
- [Trustworthy AI Agents: Deterministic Replay](https://www.sakurasky.com/blog/missing-primitives-for-trustworthy-ai-part-8/)
- [LangChain: Debugging Deep Agents](https://blog.langchain.com/debugging-deep-agents-with-langsmith/)

---

## 5. Federalist Papers Evaluation Dataset Design

Since no existing QA dataset exists for the Federalist Papers, here is a
taxonomy of question types to cover, with examples. The goal is 20-30
hand-crafted cases across these categories.

### Category 1: Single-Document Lookup (5-8 cases)

Questions answerable from one specific paper.

- "What does Federalist No. 10 argue about factions?"
  Expected: federalist-10
- "What form of government does Federalist No. 39 describe?"
  Expected: federalist-39
- "What does Federalist No. 51 say about checks and balances?"
  Expected: federalist-51
- "How does Federalist No. 68 propose electing the president?"
  Expected: federalist-68
- "What does Federalist No. 70 argue about a single executive?"
  Expected: federalist-70 (note: there are two versions in our corpus)

These test basic search-and-read. The agent should find the right file
quickly with 2-4 tool calls.

### Category 2: Multi-Document Search (5-8 cases)

Questions requiring information from multiple papers.

- "Which papers discuss the judiciary?"
  Expected: federalist-79 through federalist-84
- "What arguments are made about taxation?"
  Expected: federalist-30 through federalist-36
- "Which papers discuss the Senate?"
  Expected: federalist-62, federalist-63, federalist-64, federalist-65,
  federalist-66
- "What do the papers say about the militia?"
  Expected: federalist-29, federalist-46

These test the agent's ability to cast a wide net and find multiple
relevant files.

### Category 3: Cross-Document Comparison (3-5 cases)

Questions requiring synthesis across multiple papers.

- "How do Hamilton and Madison differ on federal power?"
  Expected: multiple papers by each author
- "How do the arguments about foreign dangers differ from those about
  domestic dangers?"
  Expected: federalist-02 through federalist-05 vs federalist-06 through
  federalist-09
- "Compare the arguments for and against a bill of rights across the
  papers."
  Expected: federalist-84 and others

### Category 4: Specific Detail Retrieval (3-5 cases)

Questions requiring finding a specific claim or phrase.

- "What does Hamilton say about standing armies?"
  Expected: federalist-24, federalist-25, federalist-26
- "What historical examples does Federalist No. 18 use?"
  Expected: federalist-18
- "What does Madison say about the 'necessary and proper' clause?"
  Expected: federalist-44

### Category 5: Negative Cases (2-3 cases)

Questions where the answer should be "not found" or "not discussed."

- "What do the Federalist Papers say about slavery?"
  Expected: agent should note limited/indirect discussion, possibly
  reference federalist-54 (three-fifths clause) but be clear this is
  tangential
- "What is the Federalist Papers' position on term limits?"
  Expected: agent should note this is discussed in federalist-72 but that
  the papers generally argue against mandatory rotation

### Building the Dataset

Practical steps:

1. Start with the 5 test questions already in CLAUDE.md -- those are good
   seeds with known intent
2. Add 5-10 questions from GradeSaver's quiz section, adapted with
   expected file annotations
3. Create 5-10 more covering the category gaps above
4. For each question, manually determine the expected files by searching
   the corpus yourself
5. Run the agent, review outputs, refine expected files and keywords
6. Store as a JSON file in `tests/fixtures/retrieval_eval.json`

Per Anthropic's guidance: "20-50 simple tasks drawn from real failures
is a great start." We can start with 20 and grow to 50 as we encounter
edge cases.

Source: [Anthropic: Demystifying Evals for AI Agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

---

## 6. Expert Guidance Summary

### Hamel Husain's Core Advice (evals.info, hamel.dev)

1. **Do not use generic/off-the-shelf metrics** like "faithfulness score"
   or "helpfulness." They measure abstract qualities that may not matter
   for your use case. "All you get from using these prefab evals is...in
   the worst case they create an illusion of confidence that is unjustified."

2. **Start with error analysis**, not evals. Look at 100+ agent traces.
   Annotate failures. Group them into categories. Only then write evals
   targeting observed failures.

3. **Good eval metrics are**: observed (from real errors), binary
   (pass/fail, not 1-5), scoped (specific failure mode), and verifiable
   (human can check).

4. **For retrieval specifically**: traditional IR metrics (Recall@K,
   Precision@K, MRR) are useful for optimizing retrieval but may be
   insufficient for RAG -- the relationship between retrieval quality
   and final answer quality is not always straightforward.

5. **If using LLM-as-judge**: validate against human labels. Split into
   train (20%, for few-shot examples), dev (40%, optimize judge), test
   (40%, final check). Aim for >90% TPR and TNR.

Sources:
- [Hamel Husain: LLM Evals FAQ](https://hamel.dev/blog/posts/evals-faq/)
- [Hamel Husain: Ready-to-Use Metrics](https://hamel.dev/blog/posts/evals-faq/should-i-use-ready-to-use-evaluation-metrics.html)
- [Hamel Husain: Modern IR Evals for RAG](https://hamel.dev/notes/llm/rag/p2-evals.html)
- [Applied AI Evals Guide](https://evals.info)

### Anthropic's Eval Taxonomy

Anthropic recommends three evaluation levels:

1. **Unit evals**: Test individual capabilities (does search_files find
   the right document for a keyword?). Fast, code-based graders.
2. **Integration evals**: Test multi-step workflows (search, then read,
   then cite). Medium complexity.
3. **End-to-end evals**: Full question-to-answer evaluation. Slower,
   may need LLM judge for subjective quality.

They also recommend "eval-driven development": define evals for planned
capabilities before the agent can fulfill them, then iterate until it
passes.

For graders: "Code-based graders are fast, cheap, and reproducible. Use
them for unit tests, state verification, and tool call validation."

Source: [Anthropic: Demystifying Evals for AI Agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

### LangChain's Deep Agent Eval Learnings

Three dimensions to evaluate:

1. **Trajectory**: The sequence of tool calls. Assert that a particular
   tool was called, without requiring a specific order. Record HTTP
   requests with vcrpy and replay in CI for speed.
2. **Final response**: The quality of the answer.
3. **Agent state/artifacts**: Any intermediate outputs.

Key practical advice: "Record HTTP requests into a filesystem and replay
them during test execution -- for Python, vcrpy works well."

Source: [LangChain: Evaluating Deep Agents](https://blog.langchain.com/evaluating-deep-agents-our-learnings/)

### Eugene Yan: Faithfulness vs Correctness

An important distinction for citation evaluation:

- **Faithfulness**: Is the answer supported by the retrieved documents?
  (This is what we primarily care about)
- **Correctness**: Is the answer factually true? (Less relevant -- we
  want the agent to be faithful to sources, not to have general knowledge)

False negatives (saying "not found" when info is present) are often a
bigger problem than false positives in retrieval systems.

Source: [Eugene Yan: Evaluating Long-Context QA Systems](https://eugeneyan.com/writing/qa-evals/)

---

## 7. Recommended Implementation Plan

### Phase 1: Minimum Viable Eval (This Week)

No new dependencies. Pure pytest.

1. Create `tests/fixtures/retrieval_eval.json` with 20 test cases
2. Create `tests/test_retrieval_eval.py` with:
   - A test runner that calls the agent (or replays saved responses)
   - Document recall checker (set intersection)
   - Expected keyword checker (string matching)
   - Tool call budget checker (count)
   - Citation existence checker (file + line number validation)
3. Run manually against live API, save the traces
4. Add replayed version to CI for fast regression testing

What this catches:
- Agent fails to find the right file
- Agent cites a nonexistent file or line number
- Agent misses key terms from expected answer
- Agent uses too many tool calls (cost/efficiency)

What this misses:
- Whether the answer is actually correct or well-written
- Whether citations semantically support the claims

### Phase 2: Citation Verification (Next Sprint)

Add NLI-based citation faithfulness checking.

1. Add `cross-encoder/nli-deberta-v3-base` as a dev dependency
2. For each citation, extract the claim and cited passage
3. Run NLI entailment check
4. Report citation_faithfulness score

This catches the case where the agent cites the right file but misquotes
or misrepresents its contents. Does not require an LLM API call.

### Phase 3: LLM-as-Judge for Faithfulness (When Needed)

Only add this if Phase 1+2 reveal a specific class of failures that
programmatic checks cannot catch.

1. For each agent response, feed the full answer + retrieved passages
   to a judge model
2. Ask binary: "Is every claim supported by the passages? Yes/No"
3. Validate judge against 20-40 hand-labeled examples
4. Run on nightly schedule (not per-commit due to cost)

---

## 8. Anti-Patterns to Avoid

1. **Do not start with LLM-as-judge.** Start with programmatic checks.
   You can evaluate document recall, citation existence, keyword presence,
   and tool call efficiency without any LLM calls. These cover the most
   common failure modes.

2. **Do not use generic "faithfulness" or "relevancy" scores from RAGAS
   or similar.** Per Hamel Husain: these give you numbers that feel
   authoritative but do not reliably correlate with your specific quality
   concerns.

3. **Do not build a large eval set upfront.** Start with 20 cases. Grow
   based on observed failures. An eval that never gets updated becomes
   stale.

4. **Do not test exact answer text.** LLM outputs vary. Test for expected
   documents retrieved, expected keywords present, and citations valid.

5. **Do not ignore the tool call trace.** The trace tells you more about
   retrieval quality than the final answer. If the agent found the right
   files but gave a bad answer, that is a generation problem, not a
   retrieval problem. If the agent gave a confident wrong answer, the
   trace reveals whether it searched the right terms.

---

## 9. Key Takeaways

1. **No existing Federalist Papers QA dataset exists.** We must create
   our own, but study guides and quiz resources provide a starting point.

2. **Document recall is the most important metric** for our use case.
   It is programmatic, deterministic, and directly answers "did the agent
   find the right sources?"

3. **Citation existence checking is the second priority.** It is also
   programmatic and catches a common class of hallucination (fabricated
   file names or line numbers).

4. **ToolQA and HotpotQA provide design inspiration** for structuring
   our test cases, even though their data domains differ.

5. **Start with custom pytest, not a framework.** At 20-30 test cases
   over a fixed 85-file corpus, the overhead of DeepEval or RAGAS is
   not justified yet. We can add DeepEval later if we need its
   tool-correctness metrics or LLM-as-judge integration.

6. **Deterministic replay (vcrpy) enables fast CI.** Record API responses
   once, replay in CI. Run live evals on a schedule.

7. **The eval gap is real.** The hardest part is not the tooling -- it is
   curating the test cases and maintaining them as the system evolves.
   Budget time for this.

---

Sources:
- [ToolQA: A Dataset for LLM Question Answering with External Tools](https://arxiv.org/abs/2306.13304)
- [HotpotQA: Multi-hop Question Answering Dataset](https://hotpotqa.github.io/)
- [MultiHop-RAG Benchmark](https://github.com/yixuantt/MultiHop-RAG)
- [ALCE: Citation Evaluation Benchmark](https://github.com/princeton-nlp/ALCE)
- [DeepEval Tool Correctness Metric](https://deepeval.com/docs/metrics-tool-correctness)
- [DeepEval Agent Evaluation Guide](https://deepeval.com/guides/guides-ai-agent-evaluation)
- [Hamel Husain: LLM Evals FAQ](https://hamel.dev/blog/posts/evals-faq/)
- [Hamel Husain: Selecting the Right Eval Tool](https://hamel.dev/blog/posts/eval-tools/)
- [Hamel Husain: Modern IR Evals for RAG](https://hamel.dev/notes/llm/rag/p2-evals.html)
- [Anthropic: Demystifying Evals for AI Agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- [Anthropic: Multi-Agent Research System](https://www.anthropic.com/engineering/multi-agent-research-system)
- [LangChain: Evaluating Deep Agents](https://blog.langchain.com/evaluating-deep-agents-our-learnings/)
- [Eugene Yan: Evaluating Long-Context QA Systems](https://eugeneyan.com/writing/qa-evals/)
- [Applied AI Evals Guide](https://evals.info)
- [Braintrust Agent Evaluation Framework](https://www.braintrust.dev/articles/ai-agent-evaluation-framework)
- [Deterministic Replay for AI Agents](https://www.sakurasky.com/blog/missing-primitives-for-trustworthy-ai-part-8/)
- [VeriCite: Citation Verification](https://arxiv.org/html/2510.11394v1)
- [GradeSaver Federalist Papers Study Guide](https://www.gradesaver.com/the-federalist-papers)
- [Kaggle Federalist Papers Dataset](https://www.kaggle.com/datasets/tobyanderson/federalist-papers)
