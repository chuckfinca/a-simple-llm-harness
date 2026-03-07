# Research: Giving an LLM Agent File Exploration Capabilities

Date: 2026-03-06

## Context

The harness (`src/llm_harness/`) is a simple agent loop with tool calling via
the OpenAI-compatible API (through litellm), a Docker sandbox for code
execution, and output truncation at 4000 characters. The goal is to let the
agent explore and search through a folder of text files (.txt, .md) to answer
user questions, without naively dumping all file contents into the context
window.

---

## 1. How Leading Tools Handle File Context

### Claude Code: Agentic Search, No Index

Claude Code uses **zero pre-indexing**. It gives the LLM three search tools
arranged in a cost hierarchy:

1. **Glob** (cheapest) -- returns only file paths matching a pattern. No file
   contents loaded. Used for discovering what exists.
2. **Grep** (medium) -- regex search across files, returns matching lines with
   context. Narrows down candidates without loading full files.
3. **Read** (most expensive) -- loads a full file into context. Reserved for
   files already identified as relevant by Glob/Grep.

The agent chains these iteratively: "each search informed by the previous
result, progressively narrowing toward the relevant files." This mimics how a
developer would use a terminal.

**Sub-agent isolation**: Claude Code spawns a separate "Explore" sub-agent
running on a cheaper model (Haiku) with its own isolated context window. This
prevents exploration from consuming the main conversation's context budget. The
explore agent can Glob, Grep, Read, and run limited Bash -- but it is
read-only.

**Prompt caching makes this viable**: Claude Code achieves 92% prefix reuse
across turns. The system prompt + tool definitions + CLAUDE.md form a stable
prefix (~18K tokens) that is cached. Processing 2M tokens without caching would
cost $6.00; with caching it drops to $1.15 (81% savings). Cache reads cost
1/10th of base input price.

Sources:
- [Claude Code Doesn't Index Your Codebase](https://vadim.blog/claude-code-no-indexing)
- [Context Engineering Under the Hood of Claude Code](https://blog.lmcache.ai/en/2025/12/23/context-engineering-reuse-pattern-under-the-hood-of-claude-code/)

### Aider: The Repo Map Pattern

Aider generates a **concise map** of the entire repository that fits within a
small token budget. The map includes file names and key symbol signatures
(classes, functions, type signatures) -- but **not** implementation bodies.

**How it works:**

1. **Tree-sitter** parses every source file to extract symbol definitions
   (function names, class names, signatures).
2. A **NetworkX MultiDiGraph** is built where nodes are source files and edges
   represent dependencies (one file references a symbol defined in another).
3. **PageRank with personalization** ranks which files/symbols are most
   important -- the ones most frequently referenced by other parts of the code
   get higher scores.
4. A **binary search** finds the maximum number of ranked symbols that fit
   within the token budget.
5. The result is a **formatted string** showing file paths and their key
   symbols -- a table of contents for the codebase.

**Token budget**: defaults to **1,024 tokens** via `--map-tokens`. Aider
adjusts dynamically -- expanding the map when no files are in the chat and the
agent needs broader awareness. Compared to loading full file contents (which
could be 1.2M tokens for a project), the repo map achieves roughly a **98%
reduction** in token usage.

**Tradeoffs**: The repo map is brilliant for code (where tree-sitter can parse
structure) but **not directly applicable to plain text files** (.txt, .md) that
lack function/class structure. For a document corpus, you would need a different
summarization strategy -- perhaps file names + first-N-lines, or explicit
document summaries.

Sources:
- [Aider Repository Map Docs](https://aider.chat/docs/repomap.html)
- [Building a Better Repo Map with Tree-Sitter](https://aider.chat/2023/10/22/repomap.html)
- [Aider Architecture Deep Dive](https://simranchawla.com/understanding-ai-coding-agents-through-aiders-architecture/)
- [Repository Mapping DeepWiki](https://deepwiki.com/Aider-AI/aider/4.1-repository-mapping)

### Cursor: On-Demand Context Loading

Cursor processes context **on-demand**, pulling relevant files into an
~8,000-line context window when you highlight code or ask a question. It uses
dynamic context loading rather than pre-indexing the full repo. For larger
projects, it fetches files just-in-time based on the current task.

### Sourcegraph Cody: RAG with Code Intelligence

Cody uses a **search-first RAG architecture**:
1. Query preprocessing and tokenization.
2. BM25 ranking (keyword-based) combined with learned signals tuned to the
   task.
3. File snippet retrieval ranked by relevance.
4. A global ranking that combines remote search results with local context
   (open files in IDE).

Cody has moved **away from embeddings** for context retrieval, citing the
complexity of sending code to third-party embedding APIs and maintenance burden.
Instead, it relies on Sourcegraph's code search engine with BM25-style ranking.

Source:
- [How Cody Understands Your Codebase](https://sourcegraph.com/blog/how-cody-understands-your-codebase)

### Continue.dev: Plugin-Based Context Providers

Continue uses a plugin architecture where `@` context providers inject content
into the LLM prompt. In agent mode, any data returned from tool calls is
automatically fed back as context. They deprecated their `@Codebase` embedding
provider in favor of rules files and MCP servers.

Source:
- [Continue Context Providers Docs](https://docs.continue.dev/customize/deep-dives/custom-providers)

---

## 2. The "Repo Map" Pattern -- Applicability to Text Files

Aider's repo map works because code has **parseable structure** (functions,
classes, signatures). Plain text files (.txt, .md) lack this structure, so a
direct port does not work. However, the underlying principle is sound: **give
the LLM a compressed table of contents so it knows what exists and where to
look, without reading everything.**

**Adaptations for a text/markdown corpus:**

| Strategy | Token Cost | Quality |
|----------|-----------|---------|
| File listing only (names + sizes) | ~5-20 tokens/file | Low -- agent knows what exists but not what's in each file |
| File listing + first 3-5 lines of each file | ~50-100 tokens/file | Medium -- agent gets a preview of each document's topic |
| File listing + LLM-generated summaries (pre-computed) | ~50-150 tokens/file | High -- but requires a preprocessing step |
| Full file contents of everything | ~500-2000 tokens/file | Highest -- but context window explosion |

For a 50-file corpus:
- File listing only: ~500 tokens total
- First-lines preview: ~3,000-5,000 tokens total
- Pre-computed summaries: ~5,000-7,500 tokens total
- Full dump: ~50,000-100,000+ tokens total

**Recommendation for the harness**: Start with the simplest approach that is
"good enough" -- a `list_files` tool that returns file names (and optionally
first few lines). The LLM can then decide which files to read. This avoids
any preprocessing pipeline.

---

## 3. Search-Then-Read vs. Read-Everything

### LlamaIndex Benchmark (2026)

LlamaIndex published a direct comparison of filesystem tools vs. vector search
(RAG) for document question-answering:

| Metric | Filesystem Agent | RAG |
|--------|-----------------|-----|
| Correctness (0-10) | **8.4** | 6.4 |
| Relevance (0-10) | **9.6** | 8.0 |
| Average latency | 11.17s | **7.36s** |

**Why filesystem tools won on quality**: The agent had access to full file
content and could interleave search with read operations. RAG suffered from
chunking artifacts and suboptimal retrieval that lost context.

**Why RAG won on speed**: Vector search returns results in a single lookup.
The filesystem agent needed multiple tool calls (list, search, read) adding
~3.8 seconds of overhead.

**Scaling behavior**: At 100-1000 documents, RAG pulled ahead on both speed
and correctness. The filesystem agent's advantage disappears when files are
too numerous or too large to feasibly explore through iterative tool calls.

**Key insight**: For 10-100 text files, search-then-read with tools is
simpler and produces higher quality answers. For 1000+ documents, RAG or
hybrid approaches become necessary.

Source:
- [Vector Search vs. Filesystem Tools: 2026 Benchmarks](https://www.llamaindex.ai/blog/did-filesystem-tools-kill-vector-search)

### Augment Code / Jason Liu Findings (2025)

Augment Code found that for SWE-Bench tasks, **grep and find outperformed
embedding-based retrieval**. The key insight: agent persistence compensates
for suboptimal tools. The agent will retry, refine queries, and eventually find
what it needs -- even with simple grep.

However, SWE-Bench repos are smaller than real-world codebases. In more complex
environments, embeddings become more valuable.

Source:
- [Why Grep Beat Embeddings in Our SWE-Bench Agent](https://jxnl.co/writing/2025/09/11/why-grep-beat-embeddings-in-our-swe-bench-agent-lessons-from-augment/)

---

## 4. Tool-Based File Exploration: Best Practices

### Recommended Tool Set (3-4 tools)

For a simple harness with text files, the minimum viable tool set is:

**`list_files`** -- List files in a directory with optional pattern matching.
Returns names and sizes only. This is the cheapest possible exploration tool.

**`read_file`** -- Read a file's contents. Must include truncation for large
files. Return the first N characters/lines with a note about how much was
omitted.

**`search_files`** -- Grep-like regex search across all files. Returns matching
lines with file name and line number. Must truncate results if too many matches.

Optional: **`file_info`** -- Return metadata (size, line count, first few
lines) for a specific file without loading the whole thing. Useful for the agent
to decide whether a file is worth reading in full.

### Output Truncation

This is critical. Your harness already truncates `run_python` output at 4000
characters with a middle-cut strategy. Apply the same pattern to file tools:

- **`read_file`**: Cap at ~8,000 characters (~2,000 tokens). If the file is
  larger, return the first half and last portion with an omission notice, or
  support `offset`/`limit` parameters to let the agent read in pages.
- **`search_files`**: Cap at ~20-30 matching lines. If there are more matches,
  return the first batch plus "N more matches not shown. Refine your query."
- **`list_files`**: Unlikely to need truncation for 10-100 files, but cap at
  ~100 entries for safety.

The truncation message should **always tell the agent what was omitted** so it
can decide to refine its query or read a specific section.

### Search Result Formatting

Return structured results that are token-efficient:

```
filename.md:42: The matching line content here
filename.md:43: Adjacent context line
---
other_file.txt:17: Another matching line
(12 more matches not shown. Refine your search or use read_file.)
```

This format gives the agent enough to decide which file to read in full.
JSON wrapping adds overhead but is fine for consistency with existing tools.

### Limiting Per-Turn Reading

Two complementary strategies:

1. **Hard limits on tool output size**: Each tool call returns at most N
   characters. This is the safety net. Your harness already does this for
   `run_python`.

2. **System prompt guidance**: Tell the agent explicitly how to explore
   efficiently. Example instruction: "When answering questions about the
   documents, start by listing available files, then search for relevant
   terms, then read only the specific files that match. Do not read files
   one by one sequentially."

### Preventing Sequential File Reading

The system prompt is the primary lever. Instruct the agent:
- "Use `search_files` to find relevant content before reading full files."
- "Do not read every file. Search first, read only what is relevant."
- "If your search returns no results, try different search terms before
  reading files directly."

Without this guidance, LLMs will often default to reading every file in
order -- especially smaller models. The instruction to search first is
essential.

---

## 5. RAG vs. Tool-Based Exploration

### Decision Matrix for 10-100 Text Files

| Factor | Tool-Based (grep/read) | RAG (embeddings + vector DB) |
|--------|----------------------|------------------------------|
| Setup complexity | Minimal -- just add 3 tool definitions | Significant -- embedding pipeline, vector store, chunking strategy |
| Answer quality (small corpus) | Higher (LlamaIndex benchmark: 8.4 vs 6.4) | Lower due to chunking artifacts |
| Latency | Higher (~11s vs ~7s) | Lower |
| Token cost per query | Higher (multiple tool calls) | Lower per query, but amortized indexing cost |
| Maintenance | Zero -- always reads current file state | Must re-index when files change |
| Handles vocabulary mismatch | No -- grep is literal | Yes -- embeddings find semantic matches |
| Handles large files | Needs pagination/truncation | Chunking handles this naturally |
| Infrastructure | None beyond LLM API | Vector database, embedding model |

### The Verdict for This Harness

For 10-100 text files in a Docker sandbox, **tool-based exploration is the
clear winner**:

1. **Simplest to implement** -- add 3 tool definitions and handlers.
2. **Higher quality answers** at this scale per benchmarks.
3. **No infrastructure** -- no vector DB, no embedding model, no chunking
   pipeline.
4. **Always fresh** -- reads current filesystem state, no stale index.
5. **Fits the existing pattern** -- the harness already has tool definitions
   and a Docker sandbox with filesystem access.

RAG becomes worth considering when:
- The corpus exceeds ~500 files or individual files exceed ~50K tokens.
- Users need semantic search ("find documents about revenue growth" when files
  say "increased sales").
- Latency per query is critical (sub-2-second responses needed).
- The corpus is stable (infrequent changes, so re-indexing cost is amortized).

---

## 6. Context Window Management

### The Quadratic Cost Problem

In an agent loop, **every turn re-sends the entire conversation history**. If
the agent reads files across multiple turns, the accumulated file contents stay
in the message history and get re-sent (and re-billed) on every subsequent API
call.

The cost curve is **quasi-quadratic**: cost = tokens_per_turn * number_of_turns.
With prompt caching, cache reads dominate once you exceed ~20K tokens of
context. At Anthropic's pricing, cache reads cost 1/10th of base input, so the
pain is reduced but not eliminated.

Concrete example with the harness:
- System prompt: ~500 tokens
- User question: ~50 tokens
- Turn 1: agent calls list_files, gets 200 tokens back
- Turn 2: agent calls search_files, gets 500 tokens back
- Turn 3: agent calls read_file, gets 2,000 tokens back
- Turn 4: agent calls read_file again, gets 2,000 tokens back
- Turn 5: agent generates answer

By turn 5, the context contains ~5,250 tokens of accumulated tool results,
all re-sent. Over a multi-question session, this compounds fast.

Source:
- [Expensively Quadratic: The LLM Agent Cost Curve](https://blog.exe.dev/expensively-quadratic)

### Strategies for Managing Context Growth

**Strategy 1: Observation Masking (recommended for simplicity)**

Replace old tool results with a short placeholder while keeping the tool call
record. The agent remembers *what* it did but the bulky output is removed.

JetBrains Research (NeurIPS 2025) found this achieves **50%+ cost reduction**
while **matching or exceeding** the solve rate of LLM-based summarization.
With a 10-turn rolling window, the agent saw a 2.6% improvement in solve rate
while being 52% cheaper.

Implementation: after each agent response, walk backward through the message
history. For any tool result older than N turns, replace its content with
`"[Output from {tool_name} — omitted. Call the tool again if needed.]"`

**Strategy 2: Context Compaction**

Strip unnecessary detail from tool outputs without rewriting. Examples:
- After the agent has used file listing results to decide which files to
  search, replace the full listing with "[Listed 47 files in /docs]".
- After a search result has been used to identify a file to read, the search
  results can be compacted.

This is **reversible** -- the agent can always re-call the tool.

**Strategy 3: Conversation Summarization**

Use a cheaper model to summarize older conversation turns into a condensed
form. More complex than masking, adds API calls (which themselves cost tokens),
and JetBrains found it runs ~15% more turns than masking without performance
gain.

**Strategy 4: Session Reset / Sub-Agent**

For each new user question, start a fresh sub-conversation. The sub-agent
explores files with a clean context, finds the answer, and returns a concise
response to the main conversation. This is what Claude Code does with its
Explore sub-agent.

Source:
- [JetBrains: Cutting Through the Noise](https://blog.jetbrains.com/research/2025/12/efficient-context-management/)
- [The Complexity Trap (NeurIPS 2025)](https://arxiv.org/abs/2508.21433)
- [Context Engineering Part 2 - Phil Schmid](https://www.philschmid.de/context-engineering-part-2)

---

## 7. Token Cost Analysis

### Per-Query Cost Estimates

Assumptions: Claude Sonnet 4 pricing ($3/M input, $15/M output), 50 markdown
files averaging 1,000 tokens each (50K total corpus).

**Approach A: Dump Everything Into Prompt**
- Input: 50,000 tokens + system prompt + question = ~51,000 tokens
- Cost per query: ~$0.15 input + ~$0.03 output = **~$0.18/query**
- Multi-turn: second question sends 51K + prior response = ~52K tokens. Third
  question: ~53K. Grows linearly per question.
- With caching: drops to ~$0.02-0.04/query after first turn.
- Feasible for small corpora, but wasteful -- most content is irrelevant to
  any given question.

**Approach B: Tool-Based Exploration (recommended)**
- Turn 1 (list_files): ~700 tokens input, ~200 tokens result
- Turn 2 (search_files): ~1,000 tokens input, ~500 tokens result
- Turn 3 (read_file): ~1,700 tokens input, ~2,000 tokens result
- Turn 4 (answer): ~3,700 tokens input, ~500 tokens output
- Total input tokens: ~7,100 (summed across 4 API calls)
- Cost: ~$0.02 input + ~$0.01 output = **~$0.03/query**
- **6x cheaper** than dumping everything, and the agent only reads what is
  relevant.
- Without caching, each turn re-sends prior messages. With caching, turns
  2-4 benefit from prefix reuse.

**Approach C: RAG**
- Embedding the corpus once: ~50K tokens * embedding model cost (~$0.0001/K)
  = ~$0.005
- Per query: embedding the question (~$0.0001) + LLM call with ~3K retrieved
  tokens = ~$0.01/query
- **Cheapest per query**, but has setup/maintenance cost and lower answer
  quality for small corpora.

### Multi-Turn Session Costs

Over a 10-question session with tool-based exploration, assuming 3-4 tool calls
per question and observation masking after each answer:

- Without masking: context grows to ~30K tokens by question 10. Total session
  cost: ~$0.50-1.00
- With masking (10-turn window): context stays under ~10K tokens. Total session
  cost: ~$0.15-0.30
- With session reset per question: each question starts fresh. Total session
  cost: ~$0.30 (no compounding, but loses conversational continuity)

---

## 8. Practical Recommendation for This Harness

### The Simplest Approach That Works Well

Given the constraints (simple harness, Docker sandbox, 10-100 text files, developer/research use), the recommended approach is **three file tools + system prompt guidance + output truncation**. No RAG, no embeddings, no preprocessing.

### Tool Definitions

Add three tools to `TOOL_DEFINITIONS` in `tools.py`:

**`list_files`**
- Parameters: `path` (string, optional, default "/workspace/docs")
- Returns: JSON array of `{name, size_bytes, line_count}` for each .txt/.md file
- Truncation: cap at 100 entries
- Implementation: runs in Docker sandbox or on host filesystem

**`read_file`**
- Parameters: `path` (string, required), `offset` (int, optional, line to start
  from), `limit` (int, optional, max lines to return, default 200)
- Returns: file contents with line numbers, truncated with omission notice
- Truncation: cap at ~8,000 characters. If file is larger, include a message
  like "Showing lines 1-200 of 847. Use offset parameter to read more."
- Key: the `offset`/`limit` parameters let the agent paginate through large
  files without loading everything at once.

**`search_files`**
- Parameters: `query` (string, regex pattern), `path` (string, optional,
  directory to search), `include` (string, optional, glob pattern like "*.md")
- Returns: matching lines with file name, line number, and 1 line of context
- Truncation: cap at 30 matches. If more exist, return count and suggest
  refining the query.
- Implementation: `grep -rn` in the Docker sandbox, or Python's `re` module

### System Prompt Addition

Add to the system prompt for any persona that needs file exploration:

```
You have access to a folder of reference documents. When answering questions
about these documents:

1. Start by calling list_files to see what documents are available.
2. Use search_files to find relevant content by searching for key terms.
3. Only call read_file on files that your search identified as relevant.
4. Do NOT read every file sequentially. Search first, then read selectively.
5. If search_files returns no results, try alternative search terms before
   falling back to reading files directly.
```

### Context Management

For the initial implementation, **observation masking** is the recommended
context management strategy due to its simplicity and proven effectiveness:

- After the agent produces a final response to a user question, walk backward
  through the message history.
- For any tool result message older than the last 6-8 messages, replace its
  `content` with a short placeholder: `"[Previous {tool_name} output omitted]"`
- Keep the tool call messages intact so the agent remembers what it searched
  for.

This can be implemented in ~15 lines of code in the agent loop and provides the
50%+ cost reduction that JetBrains validated.

### What to Skip (for now)

- **RAG / embeddings**: overkill for <100 text files. Adds infrastructure
  (vector DB, embedding model) and maintenance (re-indexing) for marginal
  benefit at this scale.
- **Repo map pattern**: designed for code with parseable structure. For plain
  text, a simple file listing serves the same purpose.
- **LLM-based summarization of old context**: adds API calls and cost. Masking
  is simpler and performs equally well per research.
- **Pre-computed document summaries**: requires a preprocessing pipeline. The
  agent can read file headers/first lines on-demand instead.
- **Sub-agent architecture**: adds significant complexity. Worth considering
  later if multi-question sessions with heavy file exploration become the
  primary use case.

### Implementation Priority

1. **Add the three file tools** -- this is the core value. The agent goes from
   blind to capable.
2. **Truncation on all tool outputs** -- prevent a single large file from
   blowing up context.
3. **System prompt guidance** -- steer the agent toward search-first behavior.
4. **Observation masking** -- add only if multi-turn sessions show cost
   compounding issues.

---

## Open Questions

1. **Where do the files live?** If files are mounted into the Docker sandbox,
   the agent can use `run_python` to search/read them today (via Python's os
   and re modules). Adding dedicated tools is cleaner but the Python sandbox
   is a zero-effort starting point for validation.

2. **How large are individual files?** If most files are under 2K tokens, the
   truncation strategy matters less. If some files are 10K+ tokens, pagination
   via offset/limit becomes essential.

3. **Semantic search needs?** If users will ask conceptual questions ("what
   documents discuss risk mitigation?") where grep on keywords fails, a future
   enhancement could add a lightweight semantic search tool using a small
   embedding model. But start without it and see if grep suffices.

4. **File mutation?** If the agent only needs to read files (not write/edit),
   the tool set is simpler and the Docker sandbox's `--read-only` flag provides
   safety. If writing is needed, that is a separate concern with its own
   permission model.

5. **Prompt caching with litellm?** The cost analysis assumes prompt caching is
   available. Verify whether litellm + your chosen provider supports automatic
   prompt caching. Anthropic's API does this automatically; OpenAI's is also
   automatic. This significantly affects the multi-turn cost profile.

---

## Sources

### Leading Tool Architectures
- [Claude Code Doesn't Index Your Codebase](https://vadim.blog/claude-code-no-indexing)
- [Context Engineering Under the Hood of Claude Code](https://blog.lmcache.ai/en/2025/12/23/context-engineering-reuse-pattern-under-the-hood-of-claude-code/)
- [Claude Code Tool Search Explained](https://www.aifreeapi.com/en/posts/claude-code-tool-search)
- [Aider Repository Map Docs](https://aider.chat/docs/repomap.html)
- [Building a Better Repo Map with Tree-Sitter](https://aider.chat/2023/10/22/repomap.html)
- [Aider Architecture Deep Dive](https://simranchawla.com/understanding-ai-coding-agents-through-aiders-architecture/)
- [Repository Mapping DeepWiki](https://deepwiki.com/Aider-AI/aider/4.1-repository-mapping)
- [How Cody Understands Your Codebase](https://sourcegraph.com/blog/how-cody-understands-your-codebase)
- [Continue Context Providers Docs](https://docs.continue.dev/customize/deep-dives/custom-providers)

### Benchmarks and Comparisons
- [Vector Search vs. Filesystem Tools: 2026 Benchmarks (LlamaIndex)](https://www.llamaindex.ai/blog/did-filesystem-tools-kill-vector-search)
- [Files Are All You Need (LlamaIndex)](https://www.llamaindex.ai/blog/files-are-all-you-need)
- [Why Grep Beat Embeddings (Jason Liu / Augment)](https://jxnl.co/writing/2025/09/11/why-grep-beat-embeddings-in-our-swe-bench-agent-lessons-from-augment/)
- [Against Claude Code's Grep-Only Retrieval (Milvus)](https://milvus.io/blog/why-im-against-claude-codes-grep-only-retrieval-it-just-burns-too-many-tokens.md)

### Context Management Research
- [Expensively Quadratic: The LLM Agent Cost Curve](https://blog.exe.dev/expensively-quadratic)
- [JetBrains: Cutting Through the Noise (NeurIPS 2025)](https://blog.jetbrains.com/research/2025/12/efficient-context-management/)
- [The Complexity Trap: Observation Masking vs Summarization](https://arxiv.org/abs/2508.21433)
- [Context Engineering Part 2 - Phil Schmid](https://www.philschmid.de/context-engineering-part-2)
- [Google ADK Context Compaction](https://google.github.io/adk-docs/context/compaction/)

### Agent Design and File Exploration
- [Programming with Agents (crawshaw)](https://crawshaw.io/blog/programming-with-agents)
- [How Dust Taught AI Agents to Navigate Data Like a Filesystem](https://dust.tt/blog/how-we-taught-ai-agents-to-navigate-company-data-like-a-filesystem)
- [AI Agents with Filesystems and Bash](https://supergok.com/ai-agents-with-filesystems-and-bash/)

### Cost and Caching
- [Anthropic Prompt Caching Docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- [How Prompt Caching Works in Claude Code](https://www.claudecodecamp.com/p/how-prompt-caching-actually-works-in-claude-code)
- [AI IDE Comparison 2026](https://www.sitepoint.com/ai-ides-compared-cursor-claude-code-cody-2026/)
