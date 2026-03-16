# Research: "Grep Killed Vector Search" -- What's Real, What's Hype

Date: 2026-03-15

## Context

This investigates the claim that simple text search tools (grep, ripgrep, find)
have made vector/embedding-based retrieval obsolete for LLM agent systems.
The question matters for our harness: should we give the agent bash/grep access
in addition to (or instead of) Python-only file tools?

---

## 1. The Argument: Why Grep Beats Embeddings

### What Practitioners Are Actually Saying

**Boris Cherny (Claude Code creator, Anthropic):** "Early versions of Claude
Code used RAG + a local vector db, but we found pretty quickly that agentic
search generally works better." The team tried local vector databases,
recursive model-based indexing, and other approaches. All had downsides --
stale indexes, permission complexity, sync overhead. Plain glob and grep,
driven by the model's reasoning, outperformed everything.

The insight came from observing engineers at Instagram: when Meta's internal
IDE's click-to-definition broke, engineers fell back to grep and find. They
were still productive. The tools were primitive but the human intelligence
driving them compensated.

Source: [Building Claude Code with Boris Cherny -- Pragmatic Engineer](https://newsletter.pragmaticengineer.com/p/building-claude-code-with-boris-cherny)

**Colin Flaherty (Augment Code, SWE-Bench):** Their agent reached the top of
the SWE-Bench leaderboard using only grep and find -- no embeddings. The
agent "used simple tools persistently, trying different approaches until it
found what it needed." Embeddings did not fail outright; they simply were not
necessary. Agent persistence compensated for search quality.

Source: [Why Grep Beat Embeddings in Our SWE-Bench Agent](https://jxnl.co/writing/2025/09/11/why-grep-beat-embeddings-in-our-swe-bench-agent-lessons-from-augment/)

**Varun (Windsurf / Codeium):** "Embedding search becomes unreliable as the
size of the codebase grows ... we must rely on a combination of techniques like
grep/file search, knowledge graph based retrieval, and a re-ranking step."

Source: [Context Engineering for Agents](https://rlancemartin.github.io/2025/06/23/context_engineering/)

### The Four Failure Modes of Vector Search That Grep Avoids

1. **Staleness.** Code and documents change constantly. Embedding indexes
   require re-chunking, re-embedding, and re-indexing on every change. Grep
   always searches the current filesystem state. Zero maintenance.

2. **Exactness.** Code work demands exact symbol names, import paths, and call
   sites. Semantic similarity ("things like this") is the wrong retrieval mode
   for debugging and refactoring. Grep finds exactly what you search for.

3. **Infrastructure complexity.** Vector search requires an embedding model,
   a vector database, a chunking strategy, sync logic, and permission handling.
   Grep requires nothing beyond the filesystem.

4. **Decontextualization.** RAG chunking strips code from its surrounding
   context -- callers, tests, configuration files. The agent gets a snippet
   but loses the "why." When an agent reads a full file via grep + read, it
   gets the complete picture.

### The Core Insight

The argument is not really "grep is better than vector search." It is:

**When an intelligent agent can iteratively refine its search strategy, simple
tools become sufficient.** The model compensates for grep's lack of semantic
understanding by trying multiple queries, refining keywords, and following
references across files. This iterative strategy makes the sophistication of
the retrieval tool less important than the reasoning driving it.

This only works because:
- The agent can retry (persistence compensates for recall failures)
- Code has distinctive, searchable keywords (function names, class names)
- The repositories being searched are small enough to explore iteratively
- The agent has context about what it is looking for (the user's question
  provides intent that informs search terms)

---

## 2. The Counter-Argument: When Grep Falls Short

### The Milvus/Zilliz Critique

Zilliz (makers of the Milvus vector database) published a direct rebuttal,
arguing that grep-only retrieval "shovels massive amounts of irrelevant code
into the LLM, driving up costs that scale horribly with repo size." Their
specific claims:

- Finding 10 relevant lines can require processing 500 lines of noise
- Grep cannot find code that accomplishes the same purpose but uses different
  naming conventions
- The system re-greps the entire repository on each search, creating
  scalability problems

Their solution (Claude Context MCP plugin) claims a **40% token reduction**
with equivalent retrieval quality by using AST-based code chunking and vector
embeddings.

**Caveat:** This is a vector database company arguing for vector search. The
40% claim needs independent verification.

Source: [Why I'm Against Claude Code's Grep-Only Retrieval](https://zilliz.com/blog/why-im-against-claude-codes-grep-only-retrieval-it-just-burns-too-many-tokens)

### LlamaIndex Benchmarks: Nuanced Results

LlamaIndex tested filesystem tools vs. RAG on academic papers with curated Q&A:

| Metric | Filesystem Agent | RAG | Winner |
|--------|-----------------|-----|--------|
| Correctness (0-10) | **8.4** | 6.4 | Filesystem |
| Relevance (0-10) | **9.6** | 8.0 | Filesystem |
| Latency | 11.17s | **7.36s** | RAG |

At 5 documents, the filesystem agent won decisively on quality. But:
- At 100 documents, RAG pulled ahead on speed and matched on correctness
- At 1000 documents, RAG's advantage grew substantially

**Key finding:** The filesystem agent's advantage disappears at scale. It
excels with smaller datasets where the agent can feasibly explore everything.

Source: [Vector Search vs. Filesystem Tools: 2026 Benchmarks](https://www.llamaindex.ai/blog/did-filesystem-tools-kill-vector-search)

### The Nuanced View

A careful analysis by nuss-and-bolts.com demonstrates that grep with
LLM-generated keywords (having the model generate search terms before
grepping) improved retrieval **nearly 10x** over naive keyword grep. This
suggests the real breakthrough is not grep itself but the LLM's ability to
generate good search queries.

Embeddings remain superior for the "continuous domain" -- when you cannot
easily derive the exact keyword but can describe what you are looking for
obliquely. The right framing is not grep vs. embeddings but rather
**latency vs. flexibility**.

Source: [On the Lost Nuance of Grep vs. Semantic Search](https://www.nuss-and-bolts.com/p/on-the-lost-nuance-of-grep-vs-semantic)

---

## 3. What Leading Agent Systems Actually Use

### Claude Code: Grep + Glob + Read (No Vector Search)

Tools: Glob, Grep (backed by ripgrep), Read, Edit, Write, Bash, LS,
NotebookRead, NotebookEdit, WebFetch, WebSearch, plus sub-agent tools
(Task/Agent for spawning Haiku-class exploration agents).

Search strategy: Zero pre-indexing. The model chains Glob (find files by
pattern) -> Grep (search content by regex) -> Read (load full file). Each
search is informed by the previous result, progressively narrowing toward
relevant files. A sub-agent on a cheaper model handles exploration with its
own isolated context window.

**Critical instruction in Claude Code's system prompt:** "Avoid using bash
to run find, grep, cat, head, tail, sed, awk, or echo commands. Instead, use
the appropriate dedicated tool." Claude Code wraps grep/find behind dedicated
tool abstractions rather than giving raw bash for search.

Source: [Claude Code Tools and System Prompt](https://gist.github.com/wong2/e0f34aac66caf890a332f7b6f9e2ba8f)

### Cursor: Hybrid (Vector Search + Grep)

Tools: Semantic search (embedding-based), file/folder search (pattern-based),
read files, edit files, run shell commands, browser, web search.

Cursor maintains a vector index of the codebase using AI-generated embeddings.
Files are broken into meaningful chunks (functions, classes, logical blocks),
embedded, and stored for similarity search. The index auto-refreshes every
~5 minutes. The agent chooses between semantic search (for conceptual queries)
and grep (for exact pattern matches).

Cursor is the notable exception that uses **both** approaches.

Source: [Cursor Agent Tools](https://cursor.com/docs/agent/tools)

### OpenAI Codex CLI: Shell-First

The Codex model "receives a limited set of tools during training and learns
instead to use the shell to search, read files, and make edits." It prefers
ripgrep (`rg`) for search because it is much faster than grep. Codex is
explicitly shell-oriented -- the model learns to use standard Unix tools
rather than purpose-built abstractions.

Source: [OpenAI Codex CLI](https://developers.openai.com/codex/cli/)

### Aider: AST-Based Repo Map (Neither Grep Nor Vector)

Aider uses a third approach: Tree-sitter AST parsing with NetworkX PageRank
to build a dependency graph of the codebase. It generates a compressed "repo
map" (default 1,024 tokens) that shows file paths and key symbol signatures
without implementation bodies. This gives the model architectural awareness
at minimal token cost.

Aider achieves the lowest token consumption among major coding agents:
8.5-13K tokens per task vs. Claude Code's 108-117K.

Source: [Aider Repository Map](https://aider.chat/docs/repomap.html)

### Sourcegraph Cody: BM25 (Moved Away From Embeddings)

Cody moved **away from embeddings** for context retrieval, citing the
complexity of sending code to third-party embedding APIs and maintenance
burden. It now uses Sourcegraph's code search engine with BM25-style
keyword ranking.

Source: [How Cody Understands Your Codebase](https://sourcegraph.com/blog/how-cody-understands-your-codebase)

### Summary Table

| Tool | Search Method | Uses Vector Search | Uses Grep/Text Search |
|------|--------------|-------------------|----------------------|
| Claude Code | Agentic (glob + grep + read) | No | Yes (ripgrep) |
| Codex CLI | Shell tools (rg, find) | No | Yes (ripgrep) |
| Cursor | Hybrid semantic + pattern | Yes (embeddings) | Yes |
| Aider | AST repo map + PageRank | No | Limited |
| Cody | BM25 keyword search | No (removed) | Yes (BM25) |

The trend is clear: 4 out of 5 major coding agents have either never used
vector search or actively moved away from it.

---

## 4. Speed: Grep vs Python for File Search

### Raw Performance

**grep vs Python re:** grep is approximately **50x faster** than Python's
`re` module for simple pattern matching, even when grep reads the file 20
times and Python reads it once. For complex regex with backreferences, grep
is **100x+ faster**.

The reason is fundamental: GNU grep uses a hand-rolled finite automata engine
(Thompson NFA) with 30+ years of optimization. Python's `re` module uses a
recursive backtracking algorithm with worse asymptotic behavior.

Source: [Compare the Speed of Grep with Python Regexes](https://python.code-maven.com/compare-the-speed-of-grep-with-python-regex)

**ripgrep vs grep:** ripgrep is **5-100x faster** than GNU grep depending on
the workload. Searching the Linux kernel source: ripgrep 0.06s vs GNU grep
0.67s (11x faster). With line numbers: ripgrep 1.66s vs GNU grep 9.48s (5.7x
faster).

ripgrep achieves this through: SIMD vectorized literal matching (16-32 bytes
per CPU cycle), work-stealing thread pool across CPU cores, automatic
.gitignore filtering, and Rust's regex engine with finite automata
optimizations.

Source: [ripgrep is faster than {grep, ag, git grep, ucg, pt, sift}](https://burntsushi.net/ripgrep/)

### What This Means for Our Harness

Our current `search_files` tool uses Python's `re` module inside the Docker
container. For our use case (10-100 text files, each <50KB), the speed
difference is negligible -- Python regex finishes in milliseconds on small
corpora. The 50x speed advantage of grep matters for large codebases
(millions of lines), not for small document collections.

However, if we ever scale to larger corpora or want to search faster for
latency-sensitive use cases, the path forward is clear: ripgrep.

---

## 5. What Would It Take to Give Our Agent Bash?

### Option A: subprocess.run from Python (Simplest)

The agent already has `run_python`. It could call `subprocess.run(["grep",
"-rn", "pattern", "/workspace/docs"])` from Python code. This works today
with zero code changes.

**Pros:**
- No new tool needed
- Agent already knows how to write Python
- subprocess.run with a list (no shell=True) avoids shell injection

**Cons:**
- Indirect -- the model has to wrap grep in Python boilerplate
- Models sometimes use `shell=True` with string concatenation, creating
  injection risks
- Not as natural as a dedicated bash tool
- grep may not be installed in the Docker image (but can be added)

### Option B: Dedicated run_bash Tool

Add a new tool that accepts a command string and executes it in the Docker
container via `subprocess.run(command, shell=True, ...)`.

**Pros:**
- Natural for the model -- just write the command
- Enables the full Unix toolkit: grep, find, wc, head, tail, sort, etc.
- Matches what Claude Code and Codex do

**Cons:**
- shell=True with arbitrary commands is inherently unsafe
- The Docker sandbox mitigates this (filesystem/network isolation), but
  it is still a wider attack surface than Python-only
- Need to handle command timeouts, output capture, and truncation
- The model might try destructive commands (rm, chmod, etc.)

### Option C: Constrained Command Execution (Middle Ground)

Add a tool that accepts a command but runs it through a whitelist:

```python
ALLOWED_COMMANDS = {"grep", "rg", "find", "wc", "head", "tail", "ls", "cat"}

def run_command(command_parts: list[str]) -> str:
    if command_parts[0] not in ALLOWED_COMMANDS:
        return f"Error: {command_parts[0]} is not an allowed command"
    return subprocess.run(command_parts, capture_output=True, text=True, ...).stdout
```

**Pros:**
- No shell injection (command passed as list, not string)
- Restricted to read-only exploration tools
- Easy to audit and extend

**Cons:**
- Cannot compose commands with pipes (grep | sort | head)
- More restrictive than what Claude Code and Codex offer
- Model may be confused by the constrained interface

### How Other Sandboxed Agent Systems Handle This

**Claude Code:** OS-level sandboxing via Seatbelt (macOS) or bubblewrap
(Linux). The bash tool runs arbitrary commands but filesystem and network
access are restricted at the kernel level. Write access is limited to the
working directory by default. Network access requires explicit domain
allowlisting.

Source: [Claude Code Sandboxing](https://code.claude.com/docs/en/sandboxing)

**Docker Sandbox (Anthropic, Nov 2025):** Mounts only the project directory
into the container, enabling `--dangerously-skip-permissions` because the
agent cannot access the host filesystem. The container provides a clean
shell environment stripped of personal customizations.

Source: [Docker Sandbox for LLM Coding Agents](https://blog.hartleybrody.com/docker-sandbox/)

**Anthropic's sandbox-runtime npm package:** Open-source sandboxing runtime
that can wrap any process. Uses OS-level primitives for filesystem and
network isolation. Available for use in custom agent projects.

**Security principle across all systems:** Filesystem isolation + network
isolation together. Either alone is insufficient. Without network isolation,
an agent could exfiltrate data. Without filesystem isolation, an agent could
backdoor system resources.

### Recommendation for This Harness

**Our Docker sandbox already provides the isolation needed.** The agent runs
inside a container with only the workspace mounted. Adding bash access inside
this container is low risk because:

1. Filesystem scope is already limited to the workspace
2. Network access is already restricted by the Docker network configuration
3. The agent cannot escape the container to affect the host

The simplest path:

1. **Do nothing new** -- the agent can already use `subprocess.run` from
   Python to call grep, find, etc. This is the zero-effort approach.

2. **If dedicated tools are needed** -- add a `search_files` tool backed by
   `subprocess.run(["grep", "-rn", ...])` in the container. This is what we
   already have, just with Python `re` instead of grep. Swapping the
   implementation to use grep would be transparent to the model.

3. **If full bash is needed** -- add a `run_bash` tool with output truncation
   and a timeout. The Docker container is the sandbox. This matches what
   Claude Code and Codex do, but we should not need it for our current
   document-search use case.

---

## 6. For Our Use Case: Is Grep Actually Better Than Python Regex?

### Document Search (Our Current Use Case)

For searching 10-100 text files of <50KB each:

- **Speed:** Irrelevant. Python regex finishes in <100ms on this corpus.
  grep would be faster, but the bottleneck is the LLM API call (seconds),
  not the search (milliseconds).

- **Accuracy:** Equivalent. For literal string matching and simple patterns,
  grep and Python `re` return identical results. Python `re` actually
  supports more regex features (lookahead, lookbehind, named groups).

- **Reliability:** Python `re` is already working. Switching to grep gains
  nothing and introduces a new dependency.

- **Integration:** Python `re` fits naturally into the existing `run_python`
  tool. grep would require either subprocess plumbing or a new tool.

**Verdict for document search: Python regex is fine. Do not change it.**

### When Grep/Ripgrep Would Matter

- Searching codebases with thousands of files
- Searching files larger than 1MB
- Latency-sensitive applications where milliseconds count
- When you want .gitignore-aware search (ripgrep)
- When the model needs to compose search with other Unix tools (pipes)

### Data Analysis

Python is essential and irreplaceable for data analysis. Pandas, numpy,
matplotlib -- these have no bash equivalents. The question is not "bash or
Python" but "should we add bash alongside Python?"

For our current use case, the answer is no. Python alone is sufficient.

---

## 7. The Bigger Picture: What This Trend Means

### The Real Insight Is About Simplicity

The "grep killed vector search" narrative is really about a broader principle:
**as models get smarter, infrastructure gets simpler.** The model's reasoning
ability compensates for crude tools. You do not need a sophisticated retrieval
pipeline when the model can iteratively refine its own search strategy.

This maps to a pattern Anthropic describes in their context engineering guide:
the most effective agent architectures are the ones with the simplest tool
interfaces. Give the model basic primitives and let it compose them.

### The RAG Obituary Is Premature

RAG is not dead. What is dying is **mandatory RAG** -- the assumption that
every LLM application needs an embedding pipeline. For many use cases
(especially code, especially smaller corpora), tool-based exploration is
simpler and produces better results.

RAG remains valuable when:
- The corpus is too large to explore iteratively (1000+ documents)
- Semantic search is needed (vocabulary mismatch between query and content)
- Latency per query must be sub-second
- The corpus is stable (amortized indexing cost)

### The Hybrid Future

The most capable system (Cursor) uses both grep and vector search. The model
chooses the right tool for each query. This is likely where the field converges:
agentic search as the default with vector search available as one more tool
the agent can reach for when keyword matching fails.

---

## Summary: Implications for This Harness

| Question | Answer |
|----------|--------|
| Should we switch from Python to grep? | No. Python regex is fine for our corpus size. |
| Should we add bash access? | Not yet. The agent can use subprocess from Python if needed. |
| Should we add vector search? | No. Overkill for 10-100 text files. |
| What should we do? | Keep the current Python-based file tools. They work. |
| When would we reconsider? | If we scale to 500+ files, need semantic search, or need sub-second retrieval. |

The "grep killed vector search" narrative is mostly right for code search in
agentic systems. For our document search use case with a small corpus, it is
irrelevant -- both grep and Python regex work fine, and the bottleneck is
model reasoning, not retrieval speed.

---

## Sources

### Primary Sources (Practitioner Experience)
- [Building Claude Code with Boris Cherny -- Pragmatic Engineer](https://newsletter.pragmaticengineer.com/p/building-claude-code-with-boris-cherny)
- [Why Grep Beat Embeddings in Our SWE-Bench Agent (Jason Liu / Augment)](https://jxnl.co/writing/2025/09/11/why-grep-beat-embeddings-in-our-swe-bench-agent-lessons-from-augment/)
- [Settling the RAG Debate: Why Claude Code Dropped Vector DB-Based RAG](https://smartscope.blog/en/ai-development/practices/rag-debate-agentic-search-code-exploration/)
- [Context Engineering for Agents (Lance Martin)](https://rlancemartin.github.io/2025/06/23/context_engineering/)

### Benchmarks and Analysis
- [Vector Search vs. Filesystem Tools: 2026 Benchmarks (LlamaIndex)](https://www.llamaindex.ai/blog/did-filesystem-tools-kill-vector-search)
- [On the Lost Nuance of Grep vs. Semantic Search](https://www.nuss-and-bolts.com/p/on-the-lost-nuance-of-grep-vs-semantic)
- [The RAG Obituary: Killed by Agents, Buried by Context Windows](https://www.nicolasbustamante.com/p/the-rag-obituary-killed-by-agents)
- [GrepRAG: Empirical Study of Grep-Like Retrieval for Code Completion](https://arxiv.org/html/2601.23254v1)

### Counter-Arguments
- [Why I'm Against Claude Code's Grep-Only Retrieval (Milvus/Zilliz)](https://zilliz.com/blog/why-im-against-claude-codes-grep-only-retrieval-it-just-burns-too-many-tokens)

### Tool Architecture
- [Claude Code Tools and System Prompt](https://gist.github.com/wong2/e0f34aac66caf890a332f7b6f9e2ba8f)
- [Cursor Agent Tools](https://cursor.com/docs/agent/tools)
- [OpenAI Codex CLI](https://developers.openai.com/codex/cli/)
- [Aider Repository Map](https://aider.chat/docs/repomap.html)
- [How Cody Understands Your Codebase](https://sourcegraph.com/blog/how-cody-understands-your-codebase)

### Sandboxing and Security
- [Claude Code Sandboxing Docs](https://code.claude.com/docs/en/sandboxing)
- [Docker Sandbox for LLM Coding Agents](https://blog.hartleybrody.com/docker-sandbox/)
- [A New Approach for Coding Agent Safety (Docker)](https://www.docker.com/blog/docker-sandboxes-a-new-approach-for-coding-agent-safety/)

### Performance
- [ripgrep is faster than {grep, ag, git grep, ucg, pt, sift}](https://burntsushi.net/ripgrep/)
- [Compare the Speed of Grep with Python Regexes](https://python.code-maven.com/compare-the-speed-of-grep-with-python-regex)
- [Ripgrep vs Grep Performance](https://www.codeant.ai/blogs/ripgrep-vs-grep-performance)

### Context Engineering
- [Effective Context Engineering for AI Agents (Anthropic)](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [Anthropic's Surprise Hit: How Claude Code Became an AI Coding Powerhouse (Podcast)](https://creators.spotify.com/pod/profile/firstmark/episodes/Anthropics-Surprise-Hit-How-Claude-Code-Became-an-AI-Coding-Powerhouse-e36ibnh)
