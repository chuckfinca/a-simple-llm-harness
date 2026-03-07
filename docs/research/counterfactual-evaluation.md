# Counterfactual Evaluation: Testing Retrieval Grounding vs. Memorization

Date: 2026-03-07

## The Problem

Our harness has an LLM agent that uses `search_files`, `list_files`, and
`read_file` tools to explore a workspace of text documents and answer questions
with citations. When the workspace contains well-known texts (Federalist
Papers, Origin of Species), the model may already know the answers from
training data. It could generate a correct answer from memory, then
retroactively search for a citation to attach. Citation checking alone cannot
distinguish "found via search" from "knew already, searched for confirmation."

This document surveys the field's approaches to detecting and preventing this
failure mode, with a focus on what we can practically implement.

---

## 1. What Is Counterfactual Evaluation?

Counterfactual evaluation modifies the documents in the workspace so they
contain facts that differ from what the model learned during training, then
tests whether the agent's answers reflect the modified documents or the
original training data.

**Core logic:** If the agent answers with the MODIFIED facts, it is reading
the documents. If it answers with the ORIGINAL facts, it is relying on
memorization.

**Example:** Federalist No. 10 was written by James Madison. A counterfactual
test would change the author attribution in the document to "John Jay" and ask
"Who wrote Federalist No. 10?" If the agent answers "Madison," it is using
training data. If it answers "Jay," it is reading the document.

This is the single most direct test of retrieval grounding. No amount of
citation verification, faithfulness scoring, or trajectory analysis can
substitute for it, because those approaches cannot distinguish between an
agent that found the answer through retrieval and one that already knew the
answer and searched for confirming evidence.

---

## 2. Research Landscape: Who Has Done This

### 2.1 ClashEval (2024) -- The Definitive "Tug of War" Study

The most methodologically rigorous work on this problem is ClashEval (arxiv
2404.10198), which systematically studies what happens when retrieved documents
contradict the model's internal knowledge.

**Methodology:**
- Curated 1,200+ questions across six domains (drug dosages, Olympic records,
  Wikipedia years, names, locations, news)
- Applied systematic perturbations at varying levels of deviation from truth
- For numerical answers: multipliers from 0.1x to 10x the correct value
- For dates: shifts in 20-year increments within +/- 100 years
- For categorical answers (names, locations): "slight, significant, and
  comical" variations generated via GPT-4o

**Key metrics:**
- Accuracy: probability of correct response
- Prior bias: how often the model selects its own knowledge when context is
  correct
- Context bias: how often the model follows incorrect context when its prior
  knowledge is accurate

**Critical findings:**
- Even GPT-4o follows incorrect contextual information more than 60% of the
  time when retrieved documents contain wrong answers
- Claude Opus adheres to incorrect contextual information 30% less than
  GPT-4o for the same degree of modification
- There is a clear negative correlation between the degree of document
  modification and the context preference rate -- the more obviously wrong
  the modification, the more likely the model is to reject it
- The less confident a model is in its initial response (measured via token
  probabilities), the more likely it adopts retrieved information

**Implication for us:** Large perturbations (changing "Madison" to
"Alexander the Great") are too easy to detect. Small, plausible perturbations
(changing "Madison" to "Jay") are more revealing because they test whether
the agent truly reads the document or uses knowledge to "correct" what it
reads.

Source: [ClashEval: Quantifying the tug-of-war between an LLM's internal prior and external evidence](https://arxiv.org/abs/2404.10198)

### 2.2 RGB Benchmark (2023) -- Four Abilities Framework

The Retrieval-Augmented Generation Benchmark (RGB) defines counterfactual
robustness as one of four fundamental abilities for RAG systems, alongside
noise robustness, negative rejection, and information integration.

**Counterfactual robustness test construction:**
1. Select questions the model can already answer correctly from internal
   knowledge
2. Retrieve relevant documents via search
3. Manually modify the answers in those documents to contain factual errors
4. Ask the model to answer using the (now-incorrect) documents
5. Instruct the model that documents may contain errors and it should
   identify and correct them

**Results (alarming):**
- ChatGPT baseline accuracy without documents: 89%
- ChatGPT error detection rate with counterfactual documents: only 9%
- Error correction rates across models: 25-57%
- Models "heavily depend on retrieved information" and lack safeguards
  against misinformation

**Implication for us:** The RGB results confirm the core tension. When the
model trusts retrieved documents, it follows modified content faithfully --
which is exactly what we WANT for grounding testing, but is also a
vulnerability. The low error detection rate (9%) means that if we modify
documents, the agent will very likely follow the modified content, making
counterfactual tests highly diagnostic.

Source: [Benchmarking Large Language Models in Retrieval-Augmented Generation](https://arxiv.org/abs/2309.01431) (AAAI 2024)

### 2.3 ConflictBank (NeurIPS 2024) -- Large-Scale Knowledge Conflicts

ConflictBank is the first large-scale benchmark for systematically evaluating
knowledge conflicts, with 7.4 million claim-evidence pairs and 553K QA pairs.

**Three types of conflicts generated:**
1. **Misinformation conflicts:** Substitute the object entity with a
   same-type entity in knowledge triples. Example: "Anne Hathaway received
   Primetime Emmy Award" becomes "Anne Hathaway received Hugo Award."
2. **Temporal conflicts:** Modify objects and add future timestamps,
   simulating knowledge that evolves over time.
3. **Semantic conflicts:** Replace subject descriptions to simulate polysemy
   (same word, different meaning in different contexts).

**Generation pipeline:**
- Extract facts from Wikidata as quintuples (subject, relation, object,
  subject_description, object_description)
- Focus on top 100 most frequent relations
- For each modified claim, use LLMs to generate supporting text in three
  styles: Wikipedia article, book passage, news article

**Key findings:**
- Models show high receptivity to external evidence when it is their only
  source, even if it conflicts with internal knowledge
- Larger models are MORE susceptible to conflicting information (counterintuitive)
- Evidence ordering significantly influences model decisions

**Implication for us:** The entity substitution approach (replacing one
entity with another of the same type) is the most practical technique for
our use case. For the Federalist Papers, this means replacing author names
with other Founding Fathers, replacing paper numbers, or swapping arguments
between papers.

Source: [ConflictBank: A Benchmark for Evaluating Knowledge Conflicts in LLMs](https://arxiv.org/abs/2408.12076) (NeurIPS 2024)

### 2.4 ToolQA (NeurIPS 2023) -- Anti-Memorization by Design

ToolQA takes a different approach: instead of modifying documents, it selects
data domains where LLMs have little chance of memorizing the answers.

**Anti-memorization strategy:**
- 8 data domains chosen for LOW training data overlap: Flight records (4M+
  records), Coffee shop reviews (5.7K records), Yelp reviews (150K), Airbnb
  listings (102K), GSM8K math problems, DBLP citation graph (553K nodes),
  SciREX scientific papers (438 documents), Personal agenda events (10K)
- Questions require precise numerical or factual answers that vary per
  record (e.g., "What was the average delay of flights from LAX on March 3,
  2023?")
- Each question requires compositional use of multiple tools (search,
  filter, calculate)

**Results proving anti-memorization works:**
- LLMs using only internal knowledge (no tools): ~5% accuracy on easy, ~2%
  on hard
- Tool-augmented LLMs (best system, Chameleon): 43% on easy, 8.2% on hard
- The massive gap between no-tools and with-tools confirms that tool use is
  essential, not optional

**Implication for us:** ToolQA validates the "use obscure data" approach
as an alternative to counterfactual modification. For our eval, this
suggests adding a corpus of non-canonical documents the model is unlikely
to have memorized -- which our test-workspace-corpora.md research already
recommends (CIA World Factbook country profiles with specific statistics,
for example).

Source: [ToolQA: A Dataset for LLM Question Answering with External Tools](https://arxiv.org/abs/2306.13304) (NeurIPS 2023)

### 2.5 RePCS (2025) -- Black-Box Memorization Detection

RePCS (Retrieval-Path Contamination Scoring) offers a runtime detection
method rather than a test-time evaluation approach. It detects whether a
RAG system is actually using retrieved content or just parroting memorized
answers.

**How it works:**
1. Run the model twice per query:
   - Retrieval-augmented path: query + retrieved documents -> distribution P_rag
   - Parametric path: query alone -> distribution P_para
2. Compute KL divergence: Z(q) = KL(P_rag || P_para)
3. If Z(q) is LOW (distributions are similar), retrieved content had minimal
   impact -> likely memorization
4. If Z(q) is HIGH (distributions diverge), retrieved content changed the
   answer -> genuine retrieval use

**Calibration:**
- One-time setup: run ~500 known-clean queries through both paths
- Set threshold tau to the 5th percentile of observed KL scores
- At inference: flag any query where Z(q') < tau as potentially memorized

**Performance:**
- ROC-AUC of 0.918 on the Prompt-WNQA benchmark
- Latency overhead: 4.7% on NVIDIA T4 (one extra forward pass)
- Model-agnostic: requires only output token probabilities, not internal
  states

**Implication for us:** This is elegant but requires access to token
probabilities, which we get from the Anthropic API. In practice, for our
test suite, the counterfactual document approach is simpler and more
direct. RePCS is better suited for production monitoring than for offline
evaluation.

Source: [RePCS: Diagnosing Data Memorization in LLM-Powered Retrieval-Augmented Generation](https://arxiv.org/abs/2506.15513)

### 2.6 RARE (2025) -- Time-Sensitive Robustness

RARE (Retrieval-Aware Robustness Evaluation) from CMU uses temporal
freshness as a natural anti-memorization mechanism.

**Approach:**
- Construct questions about time-sensitive facts from finance, economics,
  and policy documents
- Use knowledge graph triplet extraction to generate QA pairs at various
  complexity levels (single-hop and multi-hop)
- Because the facts change over time, the model's training data contains
  outdated answers
- Test whether the system uses the current (retrieved) information or
  falls back to stale parametric knowledge

**Scale:** 400 expert-level documents, 48,322 questions

**Implication for us:** Time-sensitivity is a natural counterfactual -- the
"modified" version is simply the current state of the world vs. the
training data snapshot. This does not apply directly to historical texts
like the Federalist Papers, but the approach validates the general
principle: any systematic difference between document content and training
data enables memorization detection.

Source: [RARE: Retrieval-Aware Robustness Evaluation](https://arxiv.org/abs/2506.00789)

### 2.7 FACTS Grounding (Google DeepMind, 2024-2025)

Google DeepMind's FACTS benchmark evaluates factual grounding in long-form
LLM responses. While not specifically counterfactual, its methodology is
relevant.

**Approach:**
- 1,719 examples requiring long-form responses grounded in provided documents
- Two-phase evaluation: first check response adequacy, then check that every
  claim is fully grounded in the document (no hallucinations)
- Extended in 2025 to a four-benchmark suite including a "parametric
  benchmark" that measures reliance on internal knowledge vs. grounding

**Key insight for us:** FACTS separates "parametric knowledge" evaluation
from "grounded retrieval" evaluation explicitly. This two-track approach
mirrors what we need: one test set that measures whether the agent can
answer correctly, and another that measures whether the answer comes from
the documents.

Source: [FACTS Grounding Benchmark](https://deepmind.google/blog/facts-grounding-a-new-benchmark-for-evaluating-the-factuality-of-large-language-models/)

### 2.8 FreshQA and Time-Sensitive Benchmarks

FreshQA evaluates LLMs on questions where answers change over time, divided
into four categories: never-changing, slow-changing, fast-changing, and
false-premise questions.

**Key finding:** GPT-4 answers time-sensitive questions "based on memorized
facts rather than using temporal reasoning and information from contexts."
This directly confirms our concern about memorization overriding retrieval.

Source: [FreshLLMs: Refreshing Large Language Models with Search Engine Augmentation](https://arxiv.org/abs/2310.03214)

---

## 3. What Kinds of Modifications Work

Based on the research above, here is a taxonomy of document modifications
ranked by diagnostic value.

### 3.1 Entity Substitution (MOST EFFECTIVE)

Replace one entity with another of the same type.

**Examples for Federalist Papers:**
- Change author: "Written by James Madison" -> "Written by John Jay"
- Change paper number references: "As argued in Federalist No. 51" -> "As
  argued in Federalist No. 37"
- Change proper nouns: "Montesquieu" -> "Rousseau"

**Why it works:** The modification is plausible (another Founding Father
could have written it), so the model cannot easily detect it as an error.
If the agent reports the modified author, it is reading the document. If it
reports the original author, it is using training data.

**Evidence:** ConflictBank uses this as its primary technique across 7.4M
claim-evidence pairs and finds it reliably distinguishes grounded from
memorized responses.

### 3.2 Numerical Perturbation (EFFECTIVE, EASY TO AUTOMATE)

Change numbers: dates, quantities, percentages, paper numbers.

**Examples for Federalist Papers:**
- Change publication dates
- Change numbered references to other papers
- Change specific quantities mentioned in arguments

**Why it works:** Numerical details are easy to modify programmatically and
easy to verify in the output. ClashEval demonstrates this systematically
with multipliers from 0.1x to 10x.

**Caveat from ClashEval:** Large numerical perturbations (10x) are less
diagnostic than small ones (1.2x-2x) because the model may detect the
absurdity of a 10x change and fall back to prior knowledge. Use plausible
ranges.

### 3.3 Fact Contradiction (EFFECTIVE BUT RISKY)

Change a well-known fact to its opposite.

**Examples for Federalist Papers:**
- Change "factions are the inevitable product of liberty" to "factions are
  the product of tyranny"
- Change "a large republic controls factions better than a small one" to
  "a small republic controls factions better than a large one"

**Why it works:** Tests whether the agent faithfully reports what the
document says, even when it contradicts well-known content.

**Risk:** The model may detect the contradiction and either refuse to
answer, hedge, or note the discrepancy. This is actually good model behavior
in production (detecting misinformation), but it defeats the purpose of
the eval. The RGB benchmark found only 9% error detection rate, so this
risk is lower than you might expect.

### 3.4 Content Addition (EFFECTIVE FOR SPECIFIC TESTS)

Add fictional content that the model cannot have memorized.

**Examples for Federalist Papers:**
- Add a fictional paragraph about a specific policy proposal
- Add a fictional historical example not in the original
- Add a fictional counterargument

**Why it works:** If the agent's answer includes the added content, it
must be reading the document. The model has no training data for content
that was just invented.

**Advantage:** No ambiguity -- there is zero chance the model "already knew"
the fictional content. This is the cleanest signal.

**Disadvantage:** Added content must be stylistically consistent with the
surrounding text to avoid being obviously detectable.

### 3.5 Content Removal (USEFUL FOR NEGATIVE TESTING)

Remove key information and test whether the agent reports it anyway.

**Examples for Federalist Papers:**
- Remove the famous passage about factions from Federalist No. 10
- Remove all mentions of a specific topic from a paper

**Why it works:** If the agent reports information that has been removed
from the document, it is clearly using training data. This is the inverse
of the counterfactual: instead of "did the agent follow the modification?"
it tests "did the agent hallucinate content that was removed?"

**Advantage:** Very clean signal. If the content is not in any document in
the workspace and the agent reports it with a citation, that is definitive
evidence of memorization.

### 3.6 Relative Effectiveness Summary

| Modification Type     | Diagnostic Value | Automation Ease | Risk of Confusing Model |
|----------------------|-----------------|-----------------|------------------------|
| Entity substitution  | High            | Medium          | Low                    |
| Numerical perturbation| High           | High            | Low-Medium             |
| Fact contradiction   | Medium-High     | Medium          | Medium                 |
| Content addition     | Very High       | Low (manual)    | Low                    |
| Content removal      | High            | High            | Low                    |

---

## 4. Pitfalls and Failure Modes of Counterfactual Evaluation

### 4.1 The "Too Obvious" Problem

If modifications are too large or absurd, the model detects them as errors
and falls back to parametric knowledge. ClashEval demonstrated this: context
preference drops as the degree of modification increases. Changing
"Madison" to "Mickey Mouse" will not test retrieval grounding -- it will
test the model's anomaly detection.

**Mitigation:** Use plausible substitutions. Replace entities with same-type
entities. Keep numerical changes within realistic ranges.

### 4.2 The "Stylistic Mismatch" Problem

If added or modified content does not match the style of the surrounding
text, the model may treat it as noise or recognize it as an insertion.
Modern LLMs are sensitive to stylistic inconsistency.

**Mitigation:** For the Federalist Papers, modifications should use
18th-century political prose. For programmatic modifications (entity
substitution, number changes), this is not an issue since the surrounding
text remains unchanged.

### 4.3 The "Cascading Error" Problem

Changing one fact may create downstream inconsistencies in the document.
If you change the author of Federalist No. 10 to Jay, but the document
still references "as I argued in No. 51" (which was Madison), the model
may get confused by the inconsistency rather than by the modification itself.

**Mitigation:** Make atomic, self-contained changes. Change facts that do
not create cascading logical inconsistencies. Or accept that real documents
have minor inconsistencies and the agent should handle them.

### 4.4 The "It Is Not Actually Testing Retrieval" Problem

A subtle issue: if you modify a document and the agent follows the
modification, this proves the agent READ the document. But it does not
prove the agent FOUND the document through retrieval. The agent might have
known which document to read from training data and gone directly to it
without searching.

**Mitigation:** Combine counterfactual document testing with tool call
trajectory analysis. Check both that the answer reflects the modified
content AND that the agent used search tools to find the document (not
just read_file directly by name).

### 4.5 The "Model Behavior Shift" Problem

Counterfactual documents create an artificial scenario that may not
reflect real-world agent behavior. An agent that performs well on modified
documents might behave differently on authentic documents, and vice versa.

**Mitigation:** Use counterfactual tests as ONE layer in a multi-layer eval
strategy, not the only evaluation. The counterfactual layer specifically
tests grounding; other layers test answer quality, citation accuracy, and
search thoroughness on unmodified documents.

### 4.6 The "Counterfactual Reasoning" Caveat

Recent research (arxiv 2506.15732) warns that methods designed to force
models to follow contextual premises may be "ill-suited for counterfactual
reasoning, which requires selective retention and integration of parametric
knowledge, not its wholesale dismissal." In other words, there are
legitimate cases where the model SHOULD use its training knowledge to push
back against document content.

**Implication:** Counterfactual eval measures one specific thing -- whether
the agent reads documents. It does not measure overall answer quality. A
model that blindly follows every document modification would score perfectly
on counterfactual eval but would be dangerously credulous in production.

Source: [Can LLMs Reconcile Knowledge Conflicts in Counterfactual Reasoning?](https://arxiv.org/abs/2506.15732)

---

## 5. Alternative Approaches to Testing Retrieval Grounding

### 5.1 Use Synthetic/Novel Documents (The ToolQA Approach)

Instead of modifying known documents, use documents the model has never
seen. If the model cannot answer questions about these documents without
tools, retrieval is confirmed.

**How to implement for our harness:**
- Generate fictional Federalist-style essays on topics not covered by the
  real papers (e.g., "Federalist No. 86: On the Regulation of Commerce")
- Use the CIA World Factbook corpus with specific statistics the model is
  unlikely to have memorized
- Create entirely synthetic documents about fictional topics

**Advantages:**
- No ambiguity about whether the model "already knew" the answer
- Clean test of the full retrieval pipeline
- Can be reused indefinitely without concerns about training data overlap

**Disadvantages:**
- Does not test whether the agent correctly handles the ACTUAL documents
  in the workspace
- Synthetic content may have different properties than real content
- Generating high-quality synthetic documents is non-trivial

**This is the approach recommended by our test-workspace-corpora.md
research.** The CIA World Factbook corpus is particularly well-suited
because it contains precise numerical facts (population, GDP, area) that
are both verifiable and unlikely to be exactly memorized.

### 5.2 Phrasing Analysis (Forensic Approach)

Compare the agent's output phrasing against:
(a) the document text, and
(b) common training data phrasings

If the agent's answer uses phrasing from the document (including unusual
or distinctive phrasings), it is likely reading the document. If it uses
standard textbook phrasings not found in the document, it may be relying on
training data.

**How to implement:**
- After the agent answers, extract key phrases from the response
- Check n-gram overlap with the cited passages from the actual documents
- Compare against "canonical" phrasings from Wikipedia or standard
  references

**Example:**
Federalist No. 10 contains the distinctive phrase "the CAUSES of faction
cannot be removed, and... relief is only to be sought in the means of
controlling its EFFECTS." If the agent's answer uses this exact phrasing,
it likely read the document. If it says "Madison argues that factions
cannot be eliminated but can be managed" (standard textbook phrasing),
it may be paraphrasing from training data.

**Advantages:**
- Works on unmodified documents
- Can be implemented as a similarity metric
- No document modification needed

**Disadvantages:**
- LLMs naturally paraphrase, so absence of document-specific phrasing is
  not proof of memorization
- High false negative rate: the agent might read the document and
  paraphrase it differently
- Requires defining "document-specific" vs. "generic" phrasings, which is
  subjective

**Verdict:** Useful as a supplementary signal but not reliable as a primary
grounding test.

### 5.3 Tool Call Timing Analysis (Behavioral Approach)

Analyze the sequence and timing of tool calls to detect whether the agent
formulates an answer before searching.

**Signals of genuine retrieval:**
- Agent calls search_files BEFORE mentioning any specific content
- Agent reads multiple files, suggesting genuine exploration
- Agent modifies search terms based on initial results (iterative search)
- Agent's answer changes direction after reading new content

**Signals of retroactive citation:**
- Agent makes very targeted search calls that precisely match its eventual
  answer (suspiciously efficient)
- Agent reads only one file and immediately produces a comprehensive answer
- Agent calls search_files with the exact phrase it later cites (copy-paste
  behavior)

**How to implement:**
- Log all tool calls with timestamps and arguments
- Compare the first search query against the eventual answer
- Check whether the agent's answer complexity exceeds what a single
  search+read cycle could plausibly provide

**Advantages:**
- Works on unmodified documents
- Detects the specific failure mode (retroactive citation) directly
- Can be automated as part of trajectory evaluation

**Disadvantages:**
- Circumstantial evidence, not proof. An efficient search pattern is not
  necessarily evidence of memorization
- Difficult to set thresholds (how "targeted" is too targeted?)
- Does not work for questions where the answer IS in the first file found

**Verdict:** Useful as a heuristic in trajectory evaluation but not
sufficient on its own. Best combined with counterfactual testing.

### 5.4 Withholding Test (The Absence Approach)

Ask the agent a question, but configure the workspace to NOT contain the
relevant documents. If the agent answers confidently anyway (without
acknowledging the information is not in the workspace), it is relying on
training data.

**How to implement:**
- Create a workspace with some Federalist Papers removed
- Ask questions about the removed papers
- Check whether the agent says "I could not find information about this"
  or answers from memory

**Advantages:**
- Very clean signal: if the document is not in the workspace and the agent
  answers, it is definitively using training data
- Easy to implement (just remove files)
- Also tests the agent's "I don't know" capability

**Disadvantages:**
- Only tests the negative case (agent should not answer)
- Does not test whether the agent reads documents when they ARE present

**Verdict:** Highly recommended as a complementary test. This is the
"content removal" approach from Section 3.5 taken to its extreme -- remove
the entire document instead of just modifying content within it.

### 5.5 The Dual-Run Approach (Inspired by RePCS)

Run the agent twice: once with the full workspace, once with an empty
workspace. Compare the answers.

**How to implement:**
- Run: agent answers question with workspace containing all documents
- Run: agent answers same question with empty workspace
- Compare: if the answers are substantively identical, the workspace had
  no effect -> memorization
- Compare: if the with-workspace answer is richer or different ->
  genuine retrieval influence

**Advantages:**
- Direct measurement of retrieval impact
- Works on unmodified documents
- Quantifiable (can use text similarity metrics)

**Disadvantages:**
- Requires two full agent runs per question (2x cost)
- Model non-determinism means answers will always differ somewhat
- The agent might refuse to answer without a workspace, making comparison
  impossible
- Requires prompt engineering to handle the "empty workspace" case

**Verdict:** The conceptual foundation is sound (this is what RePCS does
at the token probability level). At the full-answer level, it is noisier
but still informative. Worth implementing as a diagnostic tool for specific
suspect questions, not as a routine eval.

---

## 6. Practical Implementation Plan

Given the research above, here is a concrete plan for building counterfactual
evaluation into our test suite.

### 6.1 Approach: Three-Layer Grounding Eval

**Layer 1: Document Withholding (easiest, do first)**

Remove specific documents from the workspace and verify the agent says
"I could not find information about this" rather than answering from memory.

```python
WITHHOLDING_CASES = [
    {
        "question": "What does Federalist No. 10 argue about factions?",
        "remove_files": ["federalist-10-the-same-subject-continued.txt"],
        "expect_behavior": "not_found",
        # Agent should indicate the information is not available
    },
    {
        "question": "What does Federalist No. 51 say about checks and balances?",
        "remove_files": ["federalist-51-the-structure-of-the-government.txt"],
        "expect_behavior": "not_found",
    },
]

def test_withholding(case, agent_runner, workspace_path):
    # Temporarily remove the target files
    removed = {}
    for filename in case["remove_files"]:
        filepath = workspace_path / filename
        if filepath.exists():
            removed[filename] = filepath.read_text()
            filepath.unlink()

    try:
        result = agent_runner(case["question"])

        if case["expect_behavior"] == "not_found":
            # Agent should NOT provide a confident answer
            answer_lower = result.answer.lower()
            confidence_markers = [
                "not find", "not found", "no information",
                "could not locate", "not available",
                "not in the workspace", "unable to find",
            ]
            found_hedge = any(m in answer_lower for m in confidence_markers)
            assert found_hedge, (
                f"Agent answered confidently despite missing document: "
                f"{result.answer[:200]}"
            )
    finally:
        # Restore removed files
        for filename, content in removed.items():
            (workspace_path / filename).write_text(content)
```

**Layer 2: Entity Substitution (most diagnostic, do second)**

Modify documents to change key facts, then verify the agent reports the
modified facts.

```python
import re
import shutil

COUNTERFACTUAL_CASES = [
    {
        "question": "Who wrote Federalist No. 10?",
        "target_file": "federalist-10-the-same-subject-continued.txt",
        "modifications": [
            {"find": "MADISON", "replace": "JAY"},
            {"find": "Madison", "replace": "Jay"},
        ],
        "expected_in_answer": "Jay",
        "unexpected_in_answer": "Madison",
    },
    {
        "question": "What does Federalist No. 10 say is the primary cause "
                    "of faction?",
        "target_file": "federalist-10-the-same-subject-continued.txt",
        "modifications": [
            {
                "find": "the most common and durable source of factions "
                        "has been the various and unequal distribution of "
                        "property",
                "replace": "the most common and durable source of factions "
                           "has been the various and unequal distribution of "
                           "religious belief",
            },
        ],
        "expected_in_answer": "religious",
        "unexpected_in_answer": "property",
    },
]


def test_counterfactual(case, agent_runner, workspace_path):
    target = workspace_path / case["target_file"]
    original_content = target.read_text()

    # Apply modifications
    modified_content = original_content
    for mod in case["modifications"]:
        modified_content = modified_content.replace(mod["find"], mod["replace"])

    target.write_text(modified_content)

    try:
        result = agent_runner(case["question"])
        answer_lower = result.answer.lower()

        # Agent SHOULD report the modified fact
        assert case["expected_in_answer"].lower() in answer_lower, (
            f"Agent did not follow document modification. "
            f"Expected '{case['expected_in_answer']}' in answer. "
            f"Got: {result.answer[:300]}"
        )

        # Agent should NOT report the original (training data) fact
        if case.get("unexpected_in_answer"):
            # Allow for the case where agent mentions both (noting discrepancy)
            # but flag if ONLY the original fact appears
            has_expected = case["expected_in_answer"].lower() in answer_lower
            has_unexpected = case["unexpected_in_answer"].lower() in answer_lower

            if has_unexpected and not has_expected:
                raise AssertionError(
                    f"Agent appears to use training data instead of document. "
                    f"Found '{case['unexpected_in_answer']}' but not "
                    f"'{case['expected_in_answer']}'. "
                    f"Answer: {result.answer[:300]}"
                )
    finally:
        target.write_text(original_content)
```

**Layer 3: Synthetic Document Test (cleanest signal, do third)**

Create documents the model has never seen and verify it can answer questions
about them only when they are present.

```python
SYNTHETIC_DOCUMENT = """
FEDERALIST No. 86

On the Regulation of Interstate Commerce

By PUBLIUS (attributed to Alexander Hamilton)

Published March 15, 1788

The regulation of commerce between the several states presents difficulties
not yet fully addressed in these papers. I propose that the federal
government must possess exclusive authority over the establishment of
commercial tariffs between states, as the alternative -- permitting each
state to erect its own barriers to trade -- would reduce this union to a
collection of rival principalities.

The experience of the German Confederacy instructs us on this point. The
multiplicity of toll stations along the Rhine rendered commerce between the
German states impractical, to the detriment of all. Merchants found
themselves paying duties at every border, their goods diminishing in value
at each crossing.

I therefore propose three principles for interstate commerce regulation:
First, that no state shall impose duties on goods originating in another
state. Second, that the federal legislature shall have power to establish
uniform commercial standards. Third, that disputes between states regarding
commerce shall be adjudicated by the federal judiciary.
"""

SYNTHETIC_CASES = [
    {
        "question": "What does Federalist No. 86 argue about interstate "
                    "commerce?",
        "synthetic_file": "federalist-86-on-the-regulation-of-interstate-commerce.txt",
        "synthetic_content": SYNTHETIC_DOCUMENT,
        "expected_keywords": ["tariff", "commerce", "Rhine", "German"],
        "expect_with_document": "answers_with_content",
        "expect_without_document": "not_found",
    },
]


def test_synthetic_with_document(case, agent_runner, workspace_path):
    """Agent should answer correctly when synthetic document is present."""
    filepath = workspace_path / case["synthetic_file"]
    filepath.write_text(case["synthetic_content"])

    try:
        result = agent_runner(case["question"])
        answer_lower = result.answer.lower()
        found_keywords = [
            kw for kw in case["expected_keywords"]
            if kw.lower() in answer_lower
        ]
        assert len(found_keywords) >= 2, (
            f"Agent did not use synthetic document content. "
            f"Found {len(found_keywords)}/{len(case['expected_keywords'])} "
            f"keywords. Answer: {result.answer[:300]}"
        )
    finally:
        filepath.unlink(missing_ok=True)


def test_synthetic_without_document(case, agent_runner, workspace_path):
    """Agent should NOT answer when synthetic document is absent."""
    result = agent_runner(case["question"])
    answer_lower = result.answer.lower()

    # Federalist No. 86 does not exist -- agent should say so
    hedge_markers = [
        "not find", "does not exist", "no federalist no. 86",
        "only 85", "there is no", "could not locate",
    ]
    found_hedge = any(m in answer_lower for m in hedge_markers)
    assert found_hedge, (
        f"Agent answered about nonexistent Federalist No. 86 without "
        f"the synthetic document present. Likely using training data or "
        f"hallucinating. Answer: {result.answer[:300]}"
    )
```

### 6.2 Implementation Priority

1. **Week 1: Document withholding tests** (Layer 1)
   - 5-10 test cases, remove one file each
   - Verify agent says "not found" rather than answering from memory
   - Easiest to implement, no document modification needed
   - Also valuable for testing "I don't know" behavior generally

2. **Week 2: Synthetic document tests** (Layer 3)
   - Create 3-5 fictional Federalist-style documents
   - Test with and without the document present
   - Cleanest signal for retrieval grounding
   - Doubles as a test of the agent's search-and-read pipeline

3. **Week 3: Entity substitution tests** (Layer 2)
   - 5-10 counterfactual modifications to real documents
   - Most diagnostic but most complex to maintain
   - Requires careful selection of modifications that are plausible but
     distinguishable

### 6.3 Minimal Viable Implementation

If you want the absolute minimum to detect memorization, implement ONE
test from Layer 1 and ONE test from Layer 3:

**Minimal withholding test:**
Remove federalist-10 from the workspace. Ask "What does Federalist No. 10
argue about factions?" If the agent answers confidently, it is using
training data.

**Minimal synthetic test:**
Add a fictional Federalist No. 86 to the workspace. Ask "What does
Federalist No. 86 argue?" If the agent answers correctly using content from
the synthetic document, retrieval is working. Then remove the synthetic
document and ask again. If the agent still answers (about a paper that does
not exist), it is hallucinating.

These two tests, together, provide a lower bound and upper bound on
retrieval grounding quality with minimal effort.

---

## 7. What We Could Not Find Good Answers To

1. **Optimal perturbation magnitude.** ClashEval shows that small
   perturbations are more diagnostic than large ones, but does not give
   guidance on exactly how "small" to go for text-based modifications (as
   opposed to numerical ones). How different should "Jay" be from "Madison"
   in the model's embedding space for the test to be maximally informative?

2. **Interaction between counterfactual testing and system prompts.** Our
   system prompt instructs the agent to base answers on document content.
   Does this instruction make counterfactual testing more or less reliable?
   Models following system prompt instructions to "only use document content"
   should perform better on counterfactual tests, but we did not find
   research measuring this directly.

3. **Counterfactual test stability across model versions.** When the model
   is updated (e.g., Claude 3.5 to Claude 4), do counterfactual test
   results change significantly? A model with stronger training data recall
   might be harder to steer toward modified content. No longitudinal studies
   found.

4. **Cost of comprehensive counterfactual testing.** Each counterfactual
   test requires a full agent run with tool calls. At ~$0.10-0.50 per run
   (depending on model and conversation length), a 20-case counterfactual
   suite costs $2-10 per run. Multiplied by multiple runs for
   non-determinism, this adds up. No guidance found on how to budget for
   this.

5. **Whether models are "learning" to detect counterfactual tests.** As
   counterfactual evaluation becomes more common, model providers may
   (intentionally or not) train models to be more sensitive to
   document-knowledge conflicts. This would reduce the diagnostic value of
   counterfactual tests over time.

---

## 8. Recommendations Summary

| Approach | When to Use | Diagnostic Value | Implementation Cost |
|----------|------------|------------------|---------------------|
| Document withholding | First | High for "I don't know" | Low |
| Synthetic documents | Second | Very high for grounding | Medium |
| Entity substitution | Third | High for memorization detection | Medium |
| Numerical perturbation | For structured data | High, easy to automate | Low |
| Content addition | For specific claims | Very high | Medium (manual) |
| Content removal | For specific passages | High | Low |
| Phrasing analysis | Supplementary | Medium | Medium |
| Tool call timing | Supplementary | Low-Medium | Low |
| Dual-run comparison | Diagnostic tool | Medium | High (2x cost) |
| RePCS | Production monitoring | High | High (needs token probs) |

**Start with document withholding and synthetic documents.** These provide
the highest signal-to-noise ratio with the lowest implementation cost. Add
entity substitution when you need more granular memorization detection for
specific documents.

---

## Sources

### Core Research Papers

- [ClashEval: Quantifying the tug-of-war between an LLM's internal prior and external evidence](https://arxiv.org/abs/2404.10198) -- Systematic perturbation study, 1200+ questions, six domains
- [RGB: Benchmarking Large Language Models in Retrieval-Augmented Generation](https://arxiv.org/abs/2309.01431) -- Four-ability RAG benchmark including counterfactual robustness (AAAI 2024)
- [ConflictBank: A Benchmark for Evaluating Knowledge Conflicts in LLMs](https://arxiv.org/abs/2408.12076) -- 7.4M claim-evidence pairs, entity substitution methodology (NeurIPS 2024)
- [ToolQA: A Dataset for LLM Question Answering with External Tools](https://arxiv.org/abs/2306.13304) -- Anti-memorization dataset design, tool-use evaluation (NeurIPS 2023)
- [RePCS: Diagnosing Data Memorization in LLM-Powered RAG](https://arxiv.org/abs/2506.15513) -- Black-box memorization detection via KL divergence
- [RARE: Retrieval-Aware Robustness Evaluation](https://arxiv.org/abs/2506.00789) -- Time-sensitive robustness evaluation (CMU, 2025)
- [FACTS Grounding Benchmark](https://deepmind.google/blog/facts-grounding-a-new-benchmark-for-evaluating-the-factuality-of-large-language-models/) -- Google DeepMind factuality benchmark
- [FreshLLMs: Refreshing Large Language Models with Search Engine Augmentation](https://arxiv.org/abs/2310.03214) -- Time-sensitive QA evaluation
- [Knowledge Conflicts for LLMs: A Survey](https://aclanthology.org/2024.emnlp-main.486.pdf) -- Comprehensive survey of context-memory conflicts (EMNLP 2024)
- [Can LLMs Reconcile Knowledge Conflicts in Counterfactual Reasoning?](https://arxiv.org/abs/2506.15732) -- Limitations of counterfactual forcing approaches

### Evaluation Frameworks and Tools

- [RAGAS: Automated Evaluation of Retrieval Augmented Generation](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/) -- Includes counterfactual robustness metric
- [DeepEval](https://deepeval.com/) -- Pytest-native LLM evaluation framework
- [Braintrust: RAG Evaluation Metrics](https://www.braintrust.dev/articles/rag-evaluation-metrics) -- Practical RAG evaluation guide
- [Evidently AI: RAG Evaluation Guide](https://www.evidentlyai.com/llm-guide/rag-evaluation) -- Complete guide to RAG evaluation

### Practitioner Guides

- [Hamel Husain: LLM Evals FAQ](https://hamel.dev/blog/posts/evals-faq/) -- Practical evaluation guidance
- [Hamel Husain: Your AI Product Needs Evals](https://hamel.dev/blog/posts/evals/) -- Error analysis first approach
- [Red Hat: Synthetic Data for RAG Evaluation](https://developers.redhat.com/articles/2026/02/23/synthetic-data-rag-evaluation-why-your-rag-system-needs-better-testing) -- Synthetic data generation for RAG testing

### Benchmarks Repository

- [ToolQA GitHub](https://github.com/night-chen/ToolQA) -- Full dataset and tools
- [ConflictBank GitHub](https://github.com/pillowsofwind/Knowledge-Conflicts-Survey) -- Survey repository with benchmark links
- [FACTS Grounding Dataset](https://huggingface.co/datasets/google/FACTS-grounding-public) -- Public evaluation set
