# Context Window Management for Tool-Use Agent Loops

**Date:** 2026-03-10
**Focus:** How production LLM agent systems manage context windows, with emphasis on tool-use loops

---

## The Problem in This Harness

The current agent loop (`src/llm_harness/agent.py`) sends the full conversation
history -- system prompt + all user/assistant/tool messages -- on every LLM call.
Tool results (file contents, search results, code execution output) can be large.
This works fine for short sessions but creates three escalating problems:

1. **Cost**: Input tokens dominate agent costs (~100:1 input-to-output ratio per
   Manus production data). Every tool result stays in context for every subsequent
   call, so costs compound quadratically with conversation length.
2. **Quality degradation**: "Context rot" -- model performance degrades as input
   length increases, even within the advertised context window. Research from
   Chroma shows this affects all models, with degradation accelerating when
   multi-step reasoning is required.
3. **Hard limits**: Eventually you hit the context window ceiling and the API
   rejects the request.

The question is when to start managing this, and what approaches actually work.

---

## How Production Systems Handle Context

### Tier 1: Do Nothing (Append-Only History)

**Who uses this:** Most MVPs, simple chatbots, short-lived agent sessions.

This is what the harness does now. It works when:
- Sessions are short (under ~10 tool calls)
- Tool results are small (under ~2K tokens each)
- Cost is not a concern
- The model's context window is large relative to total session tokens

**When it breaks:** JetBrains research (SWE-bench, Dec 2025) tested unbounded
context growth as a baseline. Both observation masking and summarization "cut
costs by over 50%" compared to the raw baseline. With Qwen3-Coder 480B,
observation masking boosted solve rates by 2.6% while being 52% cheaper --
meaning the raw approach was both more expensive and less effective.

**Threshold to watch:** Above ~25K tokens of context, most models "start to
become distracted and become less likely to conform to their system prompt"
(Aider documentation). The effective quality window is often much smaller than
the advertised token limit. Beyond 12-15 conversation turns, efficiency
degradation accelerates, with "50% conversation length increases yielding 3-5%
efficiency losses" that compound.

### Tier 2: Tool Result Clearing / Observation Masking

**Who uses this:** Claude Code, SWE-agent, JetBrains agents.

The lightest-touch intervention. Old tool results are replaced with short
placeholders while preserving the conversation structure (user messages,
assistant reasoning, tool call decisions).

**Anthropic's own recommendation:** "Tool result clearing is one of the safest,
lightest-touch forms of compaction." Once tool calls execute deep in history,
agents rarely need raw outputs again. The reasoning about those outputs
(captured in assistant messages) carries the important information forward.

**Claude Code's implementation:**
- Clears older tool outputs first, before summarizing conversation
- Keeps the five most recently accessed files alongside compressed context
- Auto-compaction triggers at ~83.5% of the context window (~167K of 200K)
- Reserves ~33K tokens as a buffer for the summarization process itself
- Configurable via `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` environment variable

**JetBrains research findings (SWE-agent, Dec 2025):**
- Rolling window of the latest 10 turns gave the best balance
- Older observations replaced with placeholders indicating content was omitted
- Cost reduction: over 50% vs. unbounded baseline
- Solve rate improvement: +2.6% with Qwen3-Coder 480B
- Significantly faster than LLM summarization (no extra API calls needed)

**Why this is the recommended first step:** It preserves the conversation
structure that models depend on (the chain of user -> assistant -> tool_call ->
tool_result), it does not require an extra LLM call, it is deterministic and
debuggable, and it avoids the information loss risks of summarization.

### Tier 3: Offload to Filesystem

**Who uses this:** Cursor, LangChain Deep Agents, Manus.

Instead of truncating large tool results, write them to a file and replace the
context entry with a file path reference. The agent can read the file again if
it needs the full content.

**Cursor's approach:**
- Writes long tool output to a file, gives the agent the ability to read it
- Agent calls `tail` to check the end and reads more if needed
- Chat history is also accessible as files during context compression
- Agent can search through history files to recover summarized details
- MCP tool descriptions synced to folders instead of included statically,
  reducing total agent tokens by 46.9%

**LangChain Deep Agents (three-tier compression):**
1. When tool responses exceed 20K tokens: offload to filesystem, substitute
   with file path reference and a preview of the first 10 lines
2. When context crosses 85% of model window: truncate older tool calls,
   replace with pointers to files on disk
3. When offloading is exhausted: LLM summarization with full original
   messages preserved on disk as canonical record

**Manus's approach:**
- Treats filesystem as "unlimited in size, persistent by nature, and directly
  operable by the agent itself"
- Compression strategy is always "restorable" -- preserves URLs and file paths
  even when dropping content, allowing recovery without permanent loss
- A typical task requires ~50 tool calls on average

**Tradeoff:** Requires the agent to have file read/write tools (this harness
already has `read_file`). Adds a tool call round-trip when the agent needs old
data, but avoids the lossy compression of summarization.

### Tier 4: LLM Summarization / Compaction

**Who uses this:** Claude Code (after tool clearing), Anthropic API (beta
feature), LangGraph, OpenAI Agents SDK.

Uses an LLM to generate a compressed summary of the conversation history,
replacing older messages with the summary.

**Anthropic's server-side compaction (beta, Jan 2026):**
- API parameter: `context_management.edits` with type `compact_20260112`
- Default trigger: 150K input tokens (configurable, minimum 50K)
- Generates a `compaction` block containing the summary
- On subsequent requests, API automatically drops all message blocks prior to
  the compaction block
- Supports custom summarization instructions
- Available on Claude Opus 4.6 and Sonnet 4.6

**What Anthropic recommends preserving in summaries:**
- Architectural decisions
- Unresolved bugs
- Implementation details
- The five most recently accessed files

**What gets lost:** "Specific variable names, exact error messages, nuanced
decisions" from early interactions get compressed into high-level summaries.
This is the fundamental tradeoff.

**JetBrains research on LLM summarization (Dec 2025):**
- Summarization batch size: 21 turns at a time
- Always retained the most recent 10 turns in full
- Cost: summary-generation API calls consumed more than 7% of total cost
- Agents ran 15% longer than with observation masking (Gemini 2.5 Flash)
- Increased trajectory length = more total tokens despite compression
- Conclusion: observation masking is the better first-line defense

**Goal drift risk:** The most dangerous failure mode of summarization is the
agent losing track of the user's original intent. The summary may capture the
gist but lose the specifics that guide subsequent decisions. Manus addresses
this with "constantly rewriting" todo lists that keep objectives in the model's
recent attention span.

### Tier 5: Sub-Agent Context Isolation

**Who uses this:** Manus, Anthropic's multi-agent research system, Claude Code
(for some operations).

Delegate work to a sub-agent with its own context window. The sub-agent returns
a condensed summary of its work (typically 1,000-2,000 tokens) rather than the
parent maintaining full project state.

**Anthropic's guidance:** This is the recommended approach when a single task
requires exploring large amounts of data. The sub-agent does the heavy lifting,
fills its own context window, and returns only the distilled result.

**Manus:** "The primary goal of sub-agents is to isolate context." Each
sub-agent gets its own context window scoped to a specific task.

**Cost tradeoff:** Multi-agent architectures use ~15x more tokens than chat
(Anthropic production data), but without context isolation a single agent
would hit quality degradation or context limits even faster on complex tasks.

---

## Framework-by-Framework Summary

| System | Primary Strategy | Tool Result Handling | Trigger Threshold |
|--------|-----------------|---------------------|-------------------|
| **Claude Code** | Tool clearing, then summarization | Clears old tool outputs first | ~83.5% of window (~167K/200K) |
| **Anthropic API** | Server-side compaction (beta) | Part of compaction summary | Configurable (default 150K, min 50K) |
| **Cursor** | File offloading + conversation summarization | Writes to file, agent re-reads as needed | Near context limit |
| **Aider** | User-controlled file selection + repo map | User manages what enters context | ~25K tokens quality threshold |
| **LangChain Deep Agents** | Three-tier (offload, truncate, summarize) | >20K tokens: offload to file with 10-line preview | 85% of model window |
| **AutoGen** | TransformMessages pipeline | MessageHistoryLimiter + token-based truncation | Configurable per agent |
| **Manus** | Filesystem as memory + cache optimization | Restorable compression, file references | Task-dependent |
| **OpenAI Agents SDK** | Truncation strategies (auto/disabled) | Auto-truncation or fail-fast | Configurable |
| **SWE-agent** | Observation masking (rolling window) | Replace with placeholders | Latest 10 turns |
| **Factory.ai** | Five-layer context stack | Repo summaries + targeted file ops | Budget-based |

---

## Token Budget Strategies

### Fixed Budget

Set a hard token limit for the entire conversation. When approaching it,
apply compression. Simple to implement, predictable costs.

- Claude Code: ~167K usable of 200K window
- Deep Agents: 85% of model window
- Anthropic API compaction: configurable threshold (default 150K)

### Priority-Based Eviction

Not all context is equally valuable. A practical priority ordering:

1. **System prompt** -- never evict (defines agent behavior)
2. **Tool definitions** -- never evict (required for tool calling)
3. **Recent user messages** -- high priority (current intent)
4. **Recent assistant reasoning** -- high priority (chain of thought)
5. **Recent tool results** -- medium priority (may still be referenced)
6. **Old assistant reasoning** -- low priority (decisions already made)
7. **Old tool results** -- lowest priority (evict first)

This is exactly what Claude Code does: clear old tool outputs first, then
summarize conversation if still over budget.

### Dynamic Allocation

Reserve token budgets for different context sections:

- Factory.ai: repo overview (fixed allocation at session start), semantic
  search results (dynamic per query), targeted file reads (on demand)
- Manus: stable prefix (system prompt + tools, cached), append-only history,
  filesystem for overflow

---

## Cost Implications

### The Math on Naive "Send Everything"

For a session with 20 tool calls averaging 2K tokens each:

- Turn 1: system prompt (~2K) + user message (~200) = ~2.2K input tokens
- Turn 10: ~2.2K + 10 * (assistant ~500 + tool_call ~200 + tool_result ~2K) =
  ~29.2K input tokens
- Turn 20: ~2.2K + 20 * ~2.7K = ~56.2K input tokens
- **Cumulative input tokens across all 20 turns: ~584K tokens**

With Claude Sonnet at $3/MTok input: ~$1.75 per session.
With prompt caching at $0.30/MTok: ~$0.18 per session (assuming 90% cache hit).

If tool results are larger (10K each -- common for file reads):
- Turn 20: ~2.2K + 20 * (500 + 200 + 10K) = ~216K input tokens
- Cumulative across 20 turns: ~2.18M input tokens
- Without caching: ~$6.54 per session
- With caching (90% hit): ~$0.65 per session

### Cost Reduction from Context Management

| Technique | Cost Reduction | Complexity | Source |
|-----------|---------------|------------|--------|
| Prompt caching (stable prefix) | Up to 90% on cached portion | Low | Anthropic docs |
| Tool result clearing | ~50%+ total cost | Low | JetBrains research |
| File offloading (>20K results) | Variable, prevents worst cases | Medium | LangChain Deep Agents |
| LLM summarization | ~50%+ but adds 7%+ overhead | High | JetBrains research |
| Model routing (cheap for simple) | ~60-70% on model costs | Medium | RouteLLM paper |

### When to Invest in Context Management

**Not yet worth it (keep sending everything):**
- Sessions under 10 tool calls with small results (<2K tokens each)
- Total session tokens stay under ~50K
- Low volume (under 100 sessions/day)
- Cost per session under ~$0.10

**Worth implementing tool result clearing:**
- Sessions regularly exceed 15 tool calls
- Tool results frequently exceed 5K tokens
- Total session tokens approach 100K+
- Quality degradation becomes noticeable

**Worth implementing file offloading or summarization:**
- Sessions regularly hit context window limits
- Individual tool results exceed 20K tokens
- Complex multi-step tasks requiring 30+ tool calls
- Cost per session exceeds $1.00

---

## What to Implement in This Harness (Recommended Order)

### Step 1: Prompt Caching (Do This Immediately)

Structure messages for maximum cache hits. The harness already has the right
ordering (system prompt first, then conversation history). Specific actions:

- Remove any dynamic content from the system prompt (no timestamps)
- Use `cache_control` breakpoints at end of system prompt and tool definitions
- Use deterministic JSON serialization (`sort_keys=True`) for any structured
  content in messages
- Track `cached_tokens` in telemetry to measure cache hit rate

**Expected impact:** 50-90% reduction in input token costs with no quality
tradeoff. This is pure upside.

### Step 2: Tool Result Clearing (Low Effort, High ROI)

Add a function that replaces old tool result content with a short placeholder
before sending messages to the LLM. Keep the conversation structure intact.

Concrete approach:
- Before each LLM call, create a copy of messages for submission
- For tool results older than N turns (start with N=5), replace content with
  `"[Result from {tool_name} — cleared from context. Key findings were captured in the assistant's subsequent response.]"`
- Preserve the `tool_call_id` and role so the API accepts the message structure
- Keep the original messages list untouched for logging/replay

This is what Anthropic explicitly recommends as "the safest, lightest-touch
form of compaction."

### Step 3: Large Result Truncation (Medium Effort)

Cap individual tool results at a maximum size before they enter the message
history. The harness tools (`read_file`, `search_files`) already have natural
size limits (search capped at 30 results, read_file supports offset/limit),
but the `run_python` tool could produce arbitrarily large output.

Approach:
- Set a per-result cap (e.g., 10K tokens / ~40K characters)
- If a result exceeds the cap, truncate and append a note:
  `"[Output truncated at 10,000 tokens. Full output: {n} tokens.]"`
- For file reads, the agent can re-read with offset/limit to get more

### Step 4: Anthropic Server-Side Compaction (When Available)

When the beta stabilizes, switch to Anthropic's API-level compaction. This
is the path of least resistance for long-running sessions:

```python
context_management={
    "edits": [
        {
            "type": "compact_20260112",
            "trigger": {"type": "input_tokens", "value": 100000},
        }
    ]
}
```

This handles summarization server-side with no application logic needed.

### Step 5: File Offloading (If Needed)

If sessions regularly involve reading large files or producing large outputs,
implement the Cursor/Deep Agents pattern: write large results to a temp file,
put the path in context, let the agent re-read as needed. Only worth the
complexity if Step 2-3 are insufficient.

---

## Common Pitfalls

### 1. Summarizing Too Aggressively

**The failure mode:** Agent loses track of the user's original intent or
forgets critical details from early in the conversation. Goal drift is the
most dangerous failure mode of summarization.

**Manus's mitigation:** Constantly rewriting todo lists to keep objectives in
the model's recent attention span. The todo list acts as a persistent anchor
for the agent's goals, surviving summarization.

### 2. Breaking Tool Call Chains

**The failure mode:** Removing a `tool_call` message without removing the
corresponding `tool` result (or vice versa) causes API errors. OpenAI and
Anthropic APIs require matched pairs.

**AutoGen's solution:** When limiting messages, if the splitting point falls
between a `tool_calls` and `tool` pair, the complete pair is included.

**Rule:** Always evict tool_call + tool_result as a unit. Never split them.

### 3. Destroying Cache Locality

**The failure mode:** Modifying or removing messages from the middle of the
conversation invalidates prefix caching for everything after that point.

**Manus's rules:**
- Make conversation history append-only (never edit in place)
- If you must compress, replace the entire history with a summary block
- Never remove messages from the middle
- Use deterministic serialization (sort_keys=True) to avoid subtle cache misses

### 4. Removing Error Context

**The failure mode:** Summarization drops failed tool calls and errors. The
agent then repeats the same mistakes because it no longer has evidence that
the approach failed.

**Manus's principle:** "Leaving the wrong turns in the context helps models
implicitly update internal beliefs." Deliberately preserve failed actions.

### 5. Overengineering Before You Need It

**The failure mode:** Building a complex context management system before
understanding actual usage patterns. The system adds latency, cost (LLM
summarization calls), and bugs for marginal benefit.

**Anthropic's advice:** "Do the simplest thing that works." Model capabilities
improve faster than most context management code. Start with tool result
clearing and add complexity only when measurements justify it.

### 6. Timestamp in System Prompt

**The failure mode:** Including `Current time: 2026-03-10T14:23:11Z` in the
system prompt destroys prefix caching for the entire request. Every single
request gets a cache miss on the system prompt.

**Fix:** Move time awareness to a tool (`get_current_time`, which this harness
already has) or include it in the user message, never in the system prompt.

---

## Key Numbers to Remember

| Metric | Value | Source |
|--------|-------|--------|
| Input-to-output token ratio (agents) | ~100:1 | Manus production data |
| Cache hit cost vs. cache miss | 10x cheaper | Anthropic pricing |
| Quality degradation onset | ~25K tokens | Aider docs |
| Compounding efficiency loss | 3-5% per 50% context increase | Multiple studies |
| Optimal observation window | Latest 10 turns | JetBrains research |
| Tool result offloading threshold | >20K tokens | LangChain Deep Agents |
| Context budget trigger (Deep Agents) | 85% of model window | LangChain |
| Claude Code auto-compaction | ~83.5% of window | Claude Code internals |
| Cost of LLM summarization overhead | >7% of total cost | JetBrains research |
| Average tool calls per complex task | ~50 | Manus production data |
| Enterprise AI failures from context issues | 65% | Industry survey 2025 |

---

## Sources

- [Manus: Context Engineering for AI Agents](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus) -- Production context engineering playbook
- [Anthropic: Effective Context Engineering for AI Agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) -- Anthropic's official guidance on agent context management
- [Anthropic: Compaction API Docs](https://platform.claude.com/docs/en/build-with-claude/compaction) -- Server-side compaction beta documentation
- [JetBrains Research: Efficient Context Management](https://blog.jetbrains.com/research/2025/12/efficient-context-management/) -- SWE-bench benchmarks of context strategies
- [LangChain: Context Management for Deep Agents](https://blog.langchain.com/context-management-for-deepagents/) -- Three-tier compression implementation
- [Cursor: Dynamic Context Discovery](https://cursor.com/blog/dynamic-context-discovery) -- File-based tool output handling
- [Chroma Research: Context Rot](https://research.trychroma.com/context-rot) -- Empirical study of performance degradation across 18 LLMs
- [Factory.ai: The Context Window Problem](https://factory.ai/news/context-window-problem) -- Five-layer context stack for coding agents
- [Claude Code Context Buffer Management](https://claudefa.st/blog/guide/mechanics/context-buffer-management) -- Internal compaction thresholds and buffer mechanics
- [AutoGen: TransformMessages](https://microsoft.github.io/autogen/0.2/docs/topics/handling_long_contexts/intro_to_transform_messages/) -- Message history limiting and truncation
- [LangChain: Context Engineering for Agents](https://blog.langchain.com/context-engineering-for-agents/) -- LangGraph memory and context strategies
- [Aider](https://aider.chat/) -- Repository mapping and context management for coding agents
- [OpenAI Agents SDK: Truncation](https://github.com/openai/openai-agents-python/issues/1494) -- Auto vs. disabled truncation strategies
