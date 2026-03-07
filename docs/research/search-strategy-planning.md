# Research: Search Strategy Planning for Tool-Use Agents

Date: 2026-03-06

## The Problem

When a user asks "Which papers discuss the judiciary?", the agent does a single
`search_files("judiciary")` call and stops. It misses documents that use related
terms like "judicial", "court", "judge", "bench", "tribunal", or "legal system."
The agent has no search *strategy* -- it treats each question as a single lookup
rather than an information-seeking task that requires multiple passes.

This is not a retrieval-engine problem (we are not building a vector store or
BM25 index). The agent has simple regex/keyword tools: `list_files`,
`search_files`, and `read_file`. The question is how to make the agent *use
those tools more effectively* through planning, iteration, and query expansion.

---

## 1. Query Decomposition and Planning

### How Leading Systems Do It

Every major agentic search system -- from Perplexity to Azure AI Search's
agentic retrieval to LangChain's plan-and-execute agents -- uses a **pre-search
planning step** where the LLM generates multiple queries before executing any
search.

The pattern is consistent:

1. User asks a question
2. The LLM analyzes the question and generates 3-5 targeted sub-queries
3. Sub-queries are executed (often in parallel)
4. Results are synthesized

This is called **query fanout** in the answer-engine world. Profound's analysis
of millions of prompts confirms that systems like Claude, ChatGPT, and Gemini
routinely transform a single user prompt into multiple search queries internally,
adding terms like synonyms, year references, and domain-specific vocabulary.

Sources:
- [Introducing Query Fanouts (Profound)](https://www.tryprofound.com/blog/introducing-query-fanouts)
- [Agentic Retrieval (Azure AI Search)](https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-overview)
- [Context Engineering Deep Dive (Prompt Engineering Guide)](https://www.promptingguide.ai/agents/context-engineering-deep-dive)

### The Plan-and-Execute Pattern

LangChain's plan-and-execute pattern separates planning from execution:

- **Planner**: An LLM generates a multi-step plan with all the searches needed
- **Executor**: A lighter agent (or direct tool calls) executes each step
- **Synthesizer**: Results are combined into a final answer

This outperforms ReAct for search tasks because it forces the model to think
about *all* the angles upfront rather than myopically pursuing one thread. The
planner explicitly "thinks through" all steps required, which avoids the ReAct
failure mode of stopping after the first successful search.

The cost structure is favorable: the expensive planning call happens once, and
execution can use smaller models or direct tool calls.

Sources:
- [Plan-and-Execute Agents (LangChain)](https://blog.langchain.com/planning-agents/)
- [ReAct vs Plan-and-Execute (DEV Community)](https://dev.to/jamesli/react-vs-plan-and-execute-a-practical-comparison-of-llm-agent-patterns-4gh9)

### The ReWOO Pattern (Plan All, Execute All)

ReWOO (Reasoning Without Observation) takes planning further: the LLM produces
an entire execution script in one pass -- all tool calls with placeholders for
intermediate results -- then executes them all without consulting the LLM again
until synthesis.

Three phases:
1. **Plan**: Generate all tool calls and evidence placeholders in one LLM call
2. **Execute**: Run all tool calls, replacing placeholders with actual results
3. **Solve**: One final LLM call synthesizes all evidence into an answer

This costs exactly 2 LLM calls regardless of the number of tool invocations
(vs. ReAct's N+1 calls for N tools). For our use case -- where we know upfront
that we need multiple search terms -- this is highly relevant.

Sources:
- [ReWOO Agent Pattern (Agent Patterns docs)](https://agent-patterns.readthedocs.io/en/stable/patterns/rewoo.html)
- [What is ReWOO? (IBM)](https://www.ibm.com/think/topics/rewoo)

---

## 2. Iterative Search and Refinement

### The ReAct Loop

ReAct (Reasoning + Acting) interleaves reasoning with tool calls in a
thought-action-observation loop:

1. **Thought**: "The search for 'judiciary' returned 2 results. I should also
   check for related terms like 'court' and 'judge'."
2. **Action**: `search_files("court")`
3. **Observation**: 5 new results found
4. **Thought**: "I now have results from two searches. Let me also check..."

The explicit reasoning step is what makes this work for search refinement.
Without it, the agent has no mechanism to evaluate whether its results are
complete. The thought step forces the model to ask "did I find enough?" and
"what am I still missing?"

When a search returns irrelevant results, the thought process acknowledges the
mismatch and reformulates with better keywords. This self-correcting loop is
ReAct's primary advantage over single-shot tool calling.

Sources:
- [ReAct Pattern (Brenndoerfer)](https://mbrenndoerfer.com/writing/react-pattern-llm-reasoning-action-agents)
- [ReAct Agent Pattern (Agent Patterns docs)](https://agent-patterns.readthedocs.io/en/stable/patterns/react.html)
- [What is a ReAct Agent? (IBM)](https://www.ibm.com/think/topics/react-agent)

### When Does Refinement Trigger?

In practice, refinement triggers come from:

- **Empty or sparse results**: "The search returned 0 results, try broader terms"
- **Partial coverage**: "I found 3 documents but the user asked about multiple
  aspects of the topic"
- **Explicit reasoning**: The model's chain-of-thought identifies gaps in
  coverage

The key insight from the Augment/SWE-Bench study: agents using simple grep
tools achieved strong results through **persistence** -- trying different search
approaches repeatedly until finding what they needed. The agent's willingness to
retry with different terms compensated for the simplicity of the tools.

Sources:
- [Why Grep Beat Embeddings (Jason Liu / Augment)](https://jxnl.co/writing/2025/09/11/why-grep-beat-embeddings-in-our-swe-bench-agent-lessons-from-augment/)

---

## 3. Query Expansion Techniques

### LLM-Driven Query Expansion

The most practical approach for our case: **use the LLM itself to generate
expanded search terms before searching**. This is well-established:

- The LLM generates synonyms, related terms, and alternate phrasings
- Chain-of-thought prompting is especially effective here, since the verbose
  reasoning naturally produces a wider variety of keywords
- The expanded terms are used alongside (not replacing) the original query

Example for "judiciary":
- Synonyms: judicial, court, judge, bench, tribunal
- Related concepts: legal system, rule of law, separation of powers
- Morphological variants: judges, courts, judicial review

This does NOT require a thesaurus, embedding model, or external knowledge base.
The LLM's training data already contains the lexical knowledge needed to
generate related terms.

Sources:
- [Query Expansion with LLMs (Jina AI)](https://jina.ai/news/query-expansion-with-llms-searching-better-by-saying-more/)
- [Query Rewriting Strategies (Elasticsearch Labs)](https://www.elastic.co/search-labs/blog/query-rewriting-llm-search-improve)
- [Query Expansion in RAG (Haystack)](https://haystack.deepset.ai/blog/query-expansion)

### Key Finding: Combine Expanded Terms with the Original

Elasticsearch Labs found that combining LLM-expanded terms *with* the original
query consistently outperformed using LLM-generated terms alone. The original
query anchors relevance; the expansions improve recall. This means: always
include the user's exact terms in addition to generated synonyms.

### Approaches That Do NOT Apply Here

These are search-engine-level techniques that require infrastructure we don't
have and don't need:

- **BM25 scoring**: Requires a pre-built inverted index
- **Embedding-based similarity**: Requires vectorization of the corpus
- **Stemming at index time**: Requires a tokenizer pipeline
- **Synonym maps in the search engine**: Requires configuration of the engine

Our agent operates above the retrieval layer. It has grep. The expansion must
happen in the agent's reasoning, not in the search tool.

---

## 4. How Coding Agents Handle This

### Claude Code: Persistence, Not Planning

Claude Code does NOT pre-plan multiple search queries. It uses a ReAct-style
loop with Glob, Grep, and Read tools, where each search informs the next. Its
effectiveness comes from:

1. **Tool hierarchy**: Glob (cheap, file names) -> Grep (medium, content
   matching) -> Read (expensive, full file). The agent cascades through these.
2. **Sub-agents**: Broad exploration runs in a separate context window (on a
   cheaper model) to avoid consuming the main session's token budget.
3. **Persistence**: Claude Code will retry searches with different patterns.
   The system prompt and tool descriptions guide this behavior.
4. **No pre-built index**: Everything is searched in real-time using the tools.

Claude Code's effectiveness depends heavily on the system prompt providing
context about the working directory, available tools, and behavioral guidance
like "use Grep for pattern matching, use Glob for file discovery."

Sources:
- [Search and Indexing Strategies (Developer Toolkit)](https://developertoolkit.ai/en/shared-workflows/context-management/codebase-indexing/)
- [Claude Code vs Cursor (Qodo)](https://www.qodo.ai/blog/claude-code-vs-cursor/)

### Cursor: Grep + Semantic Search

Cursor combines traditional grep with a custom-trained semantic embedding model.
The agent decides which approach to use based on the query: exact patterns use
grep, conceptual queries use semantic search. Cursor trained its embedding model
using agent session traces -- analyzing what content the agent *should have*
found earlier in successful sessions and training the model to surface that
content.

The key insight: "the combination of grep and semantic search leads to the best
outcomes." Neither alone is sufficient.

Sources:
- [Improving Agent with Semantic Search (Cursor)](https://cursor.com/blog/semsearch)

### Aider: Structural Map, Not Search

Aider takes a fundamentally different approach: it builds a repository map using
tree-sitter AST parsing and a dependency graph, giving the LLM a bird's-eye
view of the codebase structure. This is not a search strategy -- it's a context
strategy that reduces the need for search by providing structural awareness
upfront.

### Common Pattern Across All Three

None of these tools use a dedicated "query planning" step for search. They all
rely on the LLM's inherent ability to iterate -- to look at results, reason
about what's missing, and try again. The quality comes from:

1. Good tool descriptions that explain capabilities and limitations
2. System prompts that set expectations about the environment
3. The LLM's reasoning ability to recognize incomplete results
4. Multiple tool calls in a loop (ReAct pattern)

---

## 5. System Prompt vs. Architecture

### The Prompt-Only Approach

The simplest intervention: instruct the agent to generate multiple search terms
before searching. This can be done entirely in the system prompt:

```
When asked to find information in the workspace, ALWAYS:
1. Generate 3-5 alternative search terms (synonyms, related words, variant
   spellings) before executing any search
2. Search for each term separately
3. Also check filenames using list_files for relevant-sounding documents
4. Synthesize results across all searches before answering
```

**Advantages:**
- Zero code changes
- Immediately testable
- Easy to iterate on the instructions

**Limitations:**
- The model may ignore long instructions or follow them inconsistently
- No guarantee the model generates good search terms
- No structural enforcement -- it's a suggestion, not a constraint

### The Tool-Based Approach

Add a dedicated `plan_searches` tool (or fold planning into the existing flow):

```
Tool: plan_searches
Description: Given a user question, generate a list of search queries to
  execute. Returns a JSON list of search terms. ALWAYS call this before
  calling search_files.
Input: { "question": "Which papers discuss the judiciary?" }
Output: ["judiciary", "judicial", "court", "judge", "legal system", "tribunal"]
```

The tool itself can be implemented as an LLM call (using the same or a cheaper
model) or as a simple function that asks the LLM to generate terms.

**Advantages:**
- Creates an explicit step in the workflow that cannot be skipped
- The tool's output is visible in the conversation, making the strategy auditable
- Can be tested independently of the main agent loop

**Limitations:**
- Adds an extra LLM call (cost and latency)
- The tool call itself requires the model to recognize when to use it

### The Hybrid: Prompt Instructions + Tool Descriptions

The most practical approach combines both:

1. **System prompt** instructs the agent to always think about multiple search
   terms before searching
2. **Tool descriptions** for `search_files` explicitly say "this tool searches
   for exact regex matches -- consider searching for synonyms and related terms
   separately"
3. **No new tools required** -- the expansion happens in the agent's reasoning

This mirrors how Claude Code works: the system prompt provides behavioral
guidance, and tool descriptions provide tactical guidance about each tool's
capabilities and limitations.

Source:
- [Writing Tools for Agents (Anthropic)](https://www.anthropic.com/engineering/writing-tools-for-agents)
- [11 Prompting Techniques for Better Agents (Augment Code)](https://www.augmentcode.com/blog/how-to-build-your-agent-11-prompting-techniques-for-better-ai-agents)

---

## 6. Practical Recommendation for Our Harness

Given that this is a simple Python harness with regex-based search tools, here
is the simplest effective approach, ordered from least to most effort:

### Level 1: System Prompt Only (start here)

Add search strategy instructions to the system prompt. This is the minimum
viable intervention.

```
You have access to a workspace containing text documents. When asked to find
information:

1. THINK about what terms might appear in relevant documents. Generate at
   least 3-5 search terms including synonyms, related words, and alternate
   phrasings.
2. Search for EACH term separately using search_files. A single search only
   finds exact regex matches -- it will miss documents that use different
   words for the same concept.
3. Check filenames with list_files -- document titles often reveal relevance
   that content search misses.
4. Read promising files to verify relevance before answering.
5. Synthesize results across ALL searches. Do not stop after the first
   successful search.
```

Also update the `search_files` tool description to make its limitations
explicit:

```
search_files: Search for a regex pattern across all text files in the
workspace. Returns matching lines with filenames. NOTE: This is exact regex
matching -- it will NOT find synonyms or related terms. If you are looking
for a concept (e.g., "judiciary"), you must also search for related terms
(e.g., "court", "judge", "judicial") in separate calls.
```

### Level 2: Explicit Reasoning Step

If Level 1 is insufficient, add a lightweight planning mechanism. This does
not require new tools -- it requires the system prompt to enforce a reasoning
step:

```
Before searching, you MUST write out your search plan in a <search_plan> block:

<search_plan>
Question: Which papers discuss the judiciary?
Primary terms: judiciary, judicial
Synonyms: court, judge, bench, tribunal
Related concepts: legal system, rule of law, separation of powers
Filename keywords: law, legal, court, justice
</search_plan>

Then execute searches for each term. Do not skip this planning step.
```

The explicit structured output forces the model to expand its search vocabulary
before acting. This is essentially prompt-enforced ReWOO: plan all searches
first, then execute them all.

### Level 3: Dedicated Planning Tool

If the model consistently fails to follow prompt instructions (which is
unlikely with strong models like Claude or GPT-4 but possible with smaller
models), add a `plan_searches` tool that makes the planning step mandatory
and auditable:

- Input: the user's question
- Output: a list of search terms to execute
- Implementation: a single LLM call with a focused prompt, or even a
  rule-based expansion using a small synonym dictionary

This should be a last resort. The overhead of an extra tool (and extra LLM
call) is justified only if the prompt-based approach fails in practice.

---

## 7. Key Takeaways

1. **This is a solved problem.** Every serious agentic search system generates
   multiple queries. The only question is how to implement it given our
   constraints.

2. **Start with the system prompt.** Anthropic, Augment, and other agent
   builders consistently find that clear behavioral instructions in the system
   prompt have outsized impact. The agent already has the lexical knowledge to
   generate synonyms -- it just needs to be told to do so.

3. **Make tool limitations explicit.** The `search_files` tool description
   should say it does exact matching. When the model knows the tool is literal,
   it compensates by generating multiple queries. Anthropic's tool design
   guidance emphasizes this: tools should explain what they cannot do.

4. **The ReAct loop already handles refinement.** If the agent is allowed to
   make multiple tool calls (which it is in our harness), it can naturally
   iterate. The prompt just needs to tell it not to stop after the first search.

5. **Query expansion before search is the highest-leverage change.** The model
   generating 5 search terms instead of 1 is a 5x improvement in recall for
   zero architectural cost. This is the single most impactful thing we can do.

6. **Filename checking is free and valuable.** `list_files` costs almost
   nothing and document titles often reveal relevance. The agent should always
   check filenames as part of its search strategy.

7. **Architecture changes are overkill for this use case.** A full
   plan-and-execute framework, sub-agents, or embedding-based retrieval would
   all improve search quality, but they add complexity disproportionate to the
   problem. The prompt-based approach should be tried and evaluated first.
