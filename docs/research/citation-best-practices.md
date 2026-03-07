# Citation Best Practices for LLM Agents

How should an LLM agent cite sources when answering questions from a document
corpus? This research covers citation formats used by leading AI systems,
tradeoffs between citation styles, granularity choices, faithfulness concerns,
and practical patterns implementable through system prompt instructions.

## Context

Our harness has an agent that searches and reads ~85 plain text files
(Federalist Papers). When answering questions, it should cite the specific
documents and locations it drew from. The current system prompt says:

> Cite sources with filename and line number, e.g.
> (federalist-10-the-same-subject-continued.txt:42).

This document researches what good citation practices look like and recommends
improvements.

---

## 1. How Leading AI Systems Cite Sources

### Perplexity

Perplexity is the gold standard for citation-forward AI answers. Every factual
claim gets a numbered inline reference like `[1]`, `[2]` that maps to a
references section. A Sources panel shows titles, favicons, and metadata for
quick relevance scanning. Perplexity averages 5+ citations per answer
(BrightEdge data). Users can click citations to visit the source directly.

Key design choices:
- Numbered brackets inline, placed immediately after the claim they support
- References section at the bottom with full source details
- Metadata (title, site favicon) for quick relevance assessment
- Every claim gets at least one citation

Known weaknesses: "citation overreach" (linking to a broadly relevant page
rather than the specific detail) and "over-aggregation" (one citation applied
to a whole paragraph instead of individual claims).

### Google AI Overviews

Google synthesizes an explanation with 3-5 source cards at the bottom. Sources
are shown as clickable cards with titles and site icons rather than inline
numbered references. The approach prioritizes clean readability over
fine-grained attribution. Google does not use inline citation numbers in the
generated text itself.

### Microsoft Copilot

Copilot uses inline clickable citations within the chat response. A "Show all"
reference pane consolidates all sources in a side panel. Citations are
prominently highlighted at the bottom of responses and also available inline.
The approach blends inline references with a consolidated reference panel.

### ChatGPT with Search

ChatGPT with browsing uses inline superscript-style links after claims. These
are often not numbered sequentially. Citations link to source URLs but ChatGPT
is known to hallucinate citations -- the model may generate plausible-looking
references that are entirely fabricated when not using its browse tool.

### Claude (Anthropic)

Anthropic built a first-party Citations API (launched January 2025) that
returns structured citation data at the API level. Rather than relying on
prompt-based citation instructions, the API itself chunks documents into
sentences and returns exact character indices, page numbers, or content block
indices alongside cited text. This is discussed in detail in Section 7.

### Summary Table

| System              | Format                     | Placement          | Granularity        |
|---------------------|----------------------------|--------------------|--------------------|
| Perplexity          | `[1]`, `[2]` numbered      | Inline + refs list | Per-claim          |
| Google AI Overviews | Source cards                | End of response    | Per-response       |
| Microsoft Copilot   | Inline links + side panel  | Inline + panel     | Per-claim          |
| ChatGPT + Search    | Superscript links          | Inline             | Per-claim          |
| Claude Citations API| Structured JSON spans       | API-level          | Per-sentence       |

---

## 2. Inline Citations vs. End-of-Response Citations

### Inline Citations

Place the reference marker immediately after the claim it supports.

**Advantages:**
- Tight coupling between claim and source. The reader never has to wonder
  "which source supports this particular point?"
- Encourages per-claim attribution, which research shows builds user trust
- Matches academic conventions readers are already familiar with
- Perplexity, Copilot, and academic writing all use this pattern

**Disadvantages:**
- Can clutter the response if overused, especially in prose-heavy answers
- Requires the model to track which source supports each claim during
  generation, which increases complexity
- If citations are long (filename + line number), they break reading flow

### End-of-Response Citations

List all sources at the bottom without connecting specific claims to specific
sources.

**Advantages:**
- Cleaner, more readable prose
- Simpler for the model to generate (just list what it read)
- Works well for questions that draw from a single source

**Disadvantages:**
- User cannot tell which claim comes from which source
- Research consistently shows this approach reduces user trust and makes
  verification harder
- Google AI Overviews uses this pattern and receives criticism for it

### Hybrid Approach (Recommended)

Use short inline markers (numbered references like `[1]`) within the text,
with a references section at the bottom that maps numbers to full source
details. This is the Perplexity model and the approach most praised in UX
research on AI citations.

This balances readability (short markers do not break flow) with verifiability
(each claim is traceable). The references section provides full context for
anyone who wants to check.

### What Research Says

The ShapeofAI citation patterns guide identifies four citation approaches
ranked by increasing specificity: lightweight links, multi-source references,
direct quotations, and inline highlights. The recommendation is that
"specificity matters contextually: point to exact passages for factual claims;
use broader references for discovery-oriented queries."

RAG research consistently emphasizes that citations are "table stakes for
agentic applications. Without them, users can't trust the output." Future RAG
systems are expected to further emphasize interpretability through footnotes,
explanations, and user control over source weighting.

---

## 3. Citation Granularity

### Levels of Granularity

1. **Document level**: "Federalist No. 10"
2. **Section/paragraph level**: "Federalist No. 10, paragraph 5"
3. **Line level**: "federalist-10.txt:42"
4. **Sentence level**: exact sentence cited
5. **Subsentence level**: specific clause or phrase within a sentence

### Research Findings

The LongCite paper (2024) trained models to generate sentence-level citations
and found this granularity outperformed GPT-4o by 6.4% in citation F1 scores.
The key finding: "sentence-level citations ensure semantic integrity better"
than chunk-level alternatives and provide more user-friendly verification.

A subsentence-level citation study found that "existing sentence-level
citations are unable to indicate which part of the sentence is supported by
each referenced source document, leaving effort to users to infer the
connection between content and its citation." Analysis of Wikipedia showed
that more frequently viewed pages use citations with finer granularity,
suggesting users find granular citations more useful.

The research consensus: finer granularity significantly improves users' ability
to verify information, with sentence-level and subsentence-level citations
providing substantially better verification than document-level citations.

### Recommendation for Our Use Case

**Use document name + line range, not just document name.** Our agent already
has line numbers from search_files and read_file. The practical sweet spot for
a plain text corpus is:

- Cite at the **line level** (the line number where the relevant passage
  starts)
- Include the **document name** in a human-readable form
- When a passage spans multiple lines, cite a **line range**

Document-level citations ("Federalist No. 10") are too vague for verification.
The reader would have to re-read the entire document to find the supporting
passage. Line-level citations let them jump straight to the relevant text.

---

## 4. Citation Format for File-Based Corpora

### Our Constraints

- Documents are plain text files with line numbers
- Filenames are slugified titles (e.g., `federalist-10-the-same-subject-continued.txt`)
- The agent reads files and sees line numbers in tool results
- Users see citations as plain text in a terminal (no hyperlinks or tooltips)

### Format Options Considered

**Option A: Current format**
```
(federalist-10-the-same-subject-continued.txt:42)
```
Problem: filenames are long and hard to read inline. Breaks reading flow.

**Option B: Short name + line number**
```
[Federalist No. 10, line 42]
```
More readable but requires mapping from filename to display name.

**Option C: Numbered references with details at bottom**
```
Madison argues that factions are inevitable [1].

Sources:
[1] federalist-10-the-same-subject-continued.txt, lines 42-47
```
Best readability. Separates the citation marker from the full reference.

**Option D: Academic parenthetical**
```
Madison argues that factions are inevitable (Madison, Federalist No. 10).
```
Familiar format but loses line-level specificity.

### Recommendation

**Option C (numbered references) is best for our use case.** Rationale:

1. Short inline markers `[1]` do not break reading flow in the response text
2. The references section at the bottom provides full filename and line range
   for anyone who wants to verify
3. The format matches what users expect from Perplexity and academic writing
4. It scales well when the answer draws from many sources
5. It works well in a terminal where there are no hyperlinks

The agent should use the actual filename in the references section (since
that is what the user would need to find the file) but can use a friendlier
name in the inline text if it helps readability.

### Recommended Format

Inline in the response body:
```
Madison argues that factions are sown in the nature of man [1], and that
controlling their effects is preferable to removing their causes [1]. He
identifies two methods of removing causes: destroying liberty, or giving
every citizen the same opinions [2].
```

At the end of the response:
```
Sources:
[1] federalist-10-the-same-subject-continued.txt, lines 42-58
[2] federalist-10-the-same-subject-continued.txt, lines 15-28
```

When multiple statements come from the same passage, they should share the
same reference number. When different claims come from different passages in
the same document, they should get separate reference numbers pointing to
their respective line ranges.

---

## 5. Faithfulness and Hallucinated Citations

### The Problem is Real and Significant

Citation hallucination is one of the most well-documented failure modes of
LLMs:

- Research benchmarking 13 LLMs found hallucination rates from 14% to 95%
  depending on model and domain
- Stanford research found ChatGPT hallucates 28.6% of legal citations
- Even with RAG, around 30% of individual statements may be unsupported and
  25% of citations may not support the claimed response (GPT-4 study)
- 41% of AI tool users report encountering hallucinated citations "often" or
  "very often"
- LLMs can find and cite existing "ghost references" (previously hallucinated
  citations that made it into real documents), compounding the problem

### Why Agents Hallucinate Citations

1. **Fabrication from training data**: The model generates plausible-looking
   citations from patterns seen in training, not from the actual documents
2. **Citation overreach**: The model cites a source that is broadly relevant
   but does not actually contain the specific claim
3. **Conflation**: The model merges content from multiple sources and attributes
   the merged content to one source
4. **Line number guessing**: The model cites a reasonable-sounding line number
   without actually having read that specific line

### Best Practices for Our System

Since we are not building a citation verification system, these are
prompt-level techniques to reduce hallucinated citations:

**1. Only cite what was actually read.** The system prompt should instruct the
agent to only cite documents it accessed through tool calls during the current
conversation. Never cite a document by memory or assumption.

**2. Quote before citing.** Anthropic's own prompting guide recommends asking
the model to "quote relevant parts of the documents first before carrying out
its task." This forces the model to ground its claims in actual text before
making assertions. The act of quoting acts as a self-check.

**3. Use line numbers from tool results.** The agent's read_file and
search_files tools return line numbers. Instruct the agent to use these actual
line numbers rather than estimating or remembering them.

**4. Distinguish between "the document says" and "therefore."** Instruct the
agent to clearly separate direct claims from the source ("Madison writes
that...") from the agent's own synthesis or interpretation ("This suggests
that..."). Only the direct claims should carry citations.

**5. Prefer direct quotes for critical claims.** When a claim is central to the
answer, include a brief direct quote alongside the citation. This makes it
obvious whether the citation actually supports the claim.

**6. Say "I did not find" rather than fabricating.** Instruct the agent to
explicitly state when it could not find information rather than citing a
vaguely related passage.

---

## 6. Structured vs. Natural Citations

### The Tradeoff

**Machine-parseable (structured) citations** use a consistent format that
could be parsed programmatically:
```json
{"source": "federalist-10.txt", "lines": [42, 58], "claim": "factions are inevitable"}
```

**Human-readable (natural) citations** are embedded in flowing prose:
```
Madison argues that factions are inevitable (Federalist No. 10, lines 42-58).
```

### Analysis

For our use case (terminal-based CLI output), structured citations add
complexity without clear benefit:

- There is no UI layer to render tooltips, hyperlinks, or highlights
- Users read the output as plain text
- Adding JSON to the response would hurt readability

However, the **numbered reference format is implicitly structured** without
being machine-hostile. The pattern `[1]` in the body and
`[1] filename, lines X-Y` in the references section is both human-readable
and trivially parseable with a regex if we later want to:
- Render citations as clickable links in a web UI
- Automatically verify that cited line ranges exist in the files
- Extract a structured citation graph

### Recommendation

Use the numbered reference format. It is human-readable in a terminal today
and machine-parseable tomorrow if needed. Do not use JSON or XML in the
agent's response text.

If we later build a verification layer or web UI, the numbered reference
format can be parsed with a simple pattern like:
```
\[(\d+)\]\s+(.+?),\s+lines?\s+(\d+)(?:-(\d+))?
```

---

## 7. What Anthropic Recommends

### The Citations API

Anthropic launched a first-party Citations API (January 2025) that handles
citation generation at the API level rather than through prompt engineering.
Key details:

- Documents are passed as structured content blocks with
  `citations: {enabled: true}`
- Plain text documents are automatically chunked into sentences
- Responses include structured citation data with exact character indices,
  document indices, and cited text
- The `cited_text` field does not count toward output tokens
- Citations are "guaranteed to contain valid pointers to the provided
  documents" -- they cannot hallucinate nonexistent locations

Anthropic's internal evaluations found the API-based approach:
- Outperforms prompt-based citation approaches
- Increases recall accuracy by up to 15%
- Eliminates source hallucinations (one customer, Endex, went from 10%
  hallucination rate to 0%)
- Is "significantly more likely to cite the most relevant quotes"

### When to Use the API vs. Prompt-Based Citations

The Citations API is the right choice when:
- You are using the Anthropic API directly
- Your documents can be passed as content blocks in the request
- You want guaranteed citation validity

Prompt-based citations are necessary when:
- You are using a different LLM provider or the litellm abstraction layer
- Documents are too large or too numerous to pass in a single request
- The agent discovers documents dynamically through tool calls (our case)

**Our harness uses litellm and discovers documents through search/read tool
calls**, so we cannot use the Citations API directly. We must rely on
prompt-based citation instructions.

### Anthropic's Prompt-Based Recommendations

Anthropic's prompting guide offers a relevant pattern for long-context
document tasks: "ask Claude to quote relevant parts of the documents first
before carrying out its task. This helps Claude cut through the noise of the
rest of the document's contents."

They recommend wrapping documents in XML tags with source metadata:
```xml
<documents>
  <document index="1">
    <source>document_name.txt</source>
    <document_content>
      {{CONTENT}}
    </document_content>
  </document>
</documents>
```

This structure is not directly applicable to our tool-based approach (where
the agent reads documents through tool calls), but the principle applies:
ground claims in actual quoted text before synthesizing.

---

## 8. Practical Recommendations for Our System Prompt

Based on this research, here are the specific citation instructions
recommended for our system prompt. These replace the current single-line
instruction.

### Recommended Citation Instructions

```
## Citing Sources

When answering questions, cite the specific documents and passages you used.

Format: Use numbered references. Place short markers like [1] in your
response text immediately after the claim they support. At the end of your
response, include a Sources section listing each reference with the filename
and line numbers.

Example:
  Madison argues that factions arise from the nature of man [1], and that
  a pure democracy cannot cure the mischiefs of faction [2].

  Sources:
  [1] federalist-10-the-same-subject-continued.txt, lines 42-58
  [2] federalist-10-the-same-subject-continued.txt, lines 120-135

Rules:
- Only cite documents you actually read during this conversation using
  read_file or found via search_files. Never cite from memory.
- Use the line numbers returned by your tools. Do not estimate or guess
  line numbers.
- When a claim is central to your answer, include a brief direct quote:
  Madison writes that factions are "sown in the nature of man" [1].
- When you synthesize or interpret beyond what a source directly states,
  do not attach a citation. Make clear which parts are from the source
  and which are your analysis.
- If you cannot find information to answer part of the question, say so
  rather than citing a loosely related passage.
- Multiple claims from the same passage share one reference number.
  Different passages get separate numbers even if from the same file.
```

### Key Changes from Current Approach

| Aspect                | Current                              | Recommended                              |
|-----------------------|--------------------------------------|------------------------------------------|
| Format                | `(filename:line)` inline             | `[n]` inline + Sources section at bottom |
| Readability           | Long filenames break flow            | Short markers; details at bottom         |
| Granularity           | Single line number                   | Line range                               |
| Faithfulness guidance | None                                 | "Only cite what you read" + quoting rule |
| Multiple sources      | No guidance                          | Numbered references scale naturally      |
| Interpretation        | No distinction                       | Separate sourced claims from analysis    |

---

## Sources Consulted

- [Anthropic Citations API Documentation](https://platform.claude.com/docs/en/build-with-claude/citations)
- [Anthropic Blog: Introducing Citations API](https://claude.com/blog/introducing-citations-api)
- [Anthropic Prompting Best Practices](https://platform.claude.com/docs/en/resources/prompt-library/cite-your-sources)
- [Simon Willison: Anthropic's New Citations API](https://simonw.substack.com/p/anthropics-new-citations-api)
- [ShapeofAI: Citation UX Patterns](https://www.shapeof.ai/patterns/citations)
- [LongCite: Fine-Grained Citations in Long-Context QA](https://arxiv.org/html/2409.02897v3)
- [Verifiable Generation with Subsentence-Level Fine-Grained Citations](https://arxiv.org/html/2406.06125v1)
- [Building Trustworthy RAG Systems with In-Text Citations](https://haruiz.github.io/blog/improve-rag-systems-reliability-with-citations)
- [Citation-Aware RAG: Fine-Grained Citations (Tensorlake)](https://www.tensorlake.ai/blog/rag-citations)
- [GhostCite: Citation Validity Analysis in the Age of LLMs](https://arxiv.org/html/2602.06718)
- [Microsoft Copilot Search: AI Answers with Citations](https://windowsforum.com/threads/copilot-search-ai-answers-with-prominent-citations-and-show-all.388674/)
- [Perplexity Citation Quality and Transparency](https://www.datastudios.org/post/does-perplexity-always-show-sources-citation-quality-and-transparency)
- [Stanford Legal RAG Hallucinations Study](https://dho.stanford.edu/wp-content/uploads/Legal_RAG_Hallucinations.pdf)
