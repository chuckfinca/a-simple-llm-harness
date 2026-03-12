# Context Engineering for Agent Loops

Research date: 2026-03-10

## What the Community Calls This

The term **context engineering** has become the dominant framing, displacing
"prompt engineering" as the preferred description of this work. Simon Willison
endorsed the term in mid-2025, noting that unlike "prompt engineering" it has
an inferred definition much closer to the intended meaning. Andrej Karpathy
popularized the analogy: "the context window is like RAM" -- it is the model's
working memory, and managing it is an engineering discipline.

Related terms still in use:
- **Context window management** -- the narrower mechanical concern of staying
  within token limits
- **Context compaction** -- Anthropic's specific term for their summarization
  approach
- **Memory management** -- used when discussing persistent storage across
  sessions (long-term memory)
- **Agentic memory** -- Anthropic's term for structured note-taking within
  agent loops

The key insight behind the terminology shift: the problem is not writing better
prompts. The problem is designing the entire information environment the model
operates in -- system prompts, tool definitions, conversation history, tool
results, retrieved documents, and working notes -- as a coherent system with an
explicit attention budget.

## The Core Problem for Tool-Use Agents

Looking at the current harness (in `src/llm_harness/agent.py`), the agent loop
appends every message -- user turns, assistant turns, tool calls, and tool
results -- to a single `messages` list that gets sent in full on every API
call. This is the simplest possible approach and it works, but it has three
failure modes that emerge as conversations grow:

1. **Attention degradation**: Every token competes for the model's attention.
   Anthropic's engineering team documents that critical constraints get buried
   under noise, causing agents to "forget" -- not because they run out of
   space, but because signal gets drowned by accumulation. Putting important
   information in the middle of a massive prompt can drop accuracy from ~75%
   to ~55%.

2. **Cost scaling**: Token consumption directly determines API costs. A 50%
   increase in average context length translates to 50% higher inference
   costs. Manus reports average input-to-output token ratios of ~100:1 for
   agentic tasks, meaning input tokens dominate spend.

3. **Tool results dominate**: Research shows tool outputs (observations) can
   reach 83.9% of total context usage in typical agent trajectories. A single
   `read_file` call returning a large file can consume more tokens than dozens
   of conversation turns.

## When Naive "Send Everything" Works Fine

Before implementing any context management, it is worth understanding when the
simple approach is sufficient:

- **Short tasks** (under ~10 tool calls): Context stays well within limits and
  attention degradation is minimal. Most simple Q&A with a few tool lookups
  fits here.

- **Small tool results**: If tools return compact JSON (timestamps, calculator
  results, short search snippets), accumulation is slow.

- **Modern large-context models**: With 200K token windows (Claude) or 128K
  (GPT-4), you can sustain surprisingly long conversations before hitting
  limits.

- **Cost is not a constraint**: For internal tools or low-volume use cases,
  the simplicity of sending everything may outweigh optimization savings.

**Rule of thumb from practitioners**: Start with naive full-context. Add
context management when you observe one of these symptoms:
- Tasks regularly exceed 50% of the context window
- Tool results frequently return large payloads (file contents, search results)
- Agent behavior degrades noticeably in longer conversations
- API costs become material

## Proven Production Strategies (Ranked by Maturity)

### 1. Tool Result Truncation / Offloading (Highest ROI, Simplest)

The single most impactful optimization for tool-use agents. Tool outputs are
the biggest context consumers, and most of their content becomes irrelevant
after the model has processed it.

**What production teams do:**

- **LangChain Deep Agents**: When tool responses exceed 20,000 tokens, offload
  to filesystem and substitute a file path reference plus a 10-line preview.
  The agent can retrieve the full content later if needed.

- **Manus**: Treats the file system as "unlimited, persistent, directly
  operable" context. Web page URLs preserve content recoverability; document
  paths maintain accessibility. Compression remains restorable -- avoid
  irreversible information loss.

- **Claude Code**: Microcompaction offloads bulky tool results early. Recent
  tool results stay inline for continued reasoning while older results become
  stored on disk, retrievable by path.

**Implementation pattern for the harness:**

```python
MAX_TOOL_RESULT_TOKENS = 20_000  # rough character estimate

def maybe_truncate_tool_result(result: str) -> str:
    if len(result) > MAX_TOOL_RESULT_TOKENS:
        preview = result[:2000]
        # Store full result somewhere retrievable
        return f"{preview}\n\n[Result truncated. {len(result)} chars total.]"
    return result
```

This is the lowest-risk, highest-return optimization. It preserves the
architecture of "send everything" while capping the worst-case tool result
sizes.

### 2. Observation Masking (Simple, Proven, Often Better Than Summarization)

Replace older tool results with short placeholders while keeping the reasoning
and actions intact. JetBrains Research (December 2025) tested this against LLM
summarization on SWE-bench Verified and found:

- Both strategies cut costs by over 50% versus unmanaged context
- Observation masking **matched or exceeded** LLM summarization in 4 of 5
  test settings
- With Qwen3-Coder 480B: observation masking achieved 2.6% higher solve rates
  while being 52% cheaper
- Summarization caused agents to run 13-15% longer (trajectory elongation) and
  summary generation itself consumed over 7% of total costs

**Implementation pattern:**

Keep the N most recent tool results intact. Replace older tool results with a
brief marker like `[Previous tool result for read_file("config.py") -- see
above for details]`. This preserves the conversation flow (the model can see
it called a tool and got a result) without the full payload.

```python
OBSERVATION_WINDOW = 10  # keep last N tool results intact

def mask_old_observations(messages: list[Message]) -> list[Message]:
    tool_result_indices = [
        i for i, m in enumerate(messages) if m["role"] == "tool"
    ]
    old_indices = set(tool_result_indices[:-OBSERVATION_WINDOW])

    masked = []
    for i, msg in enumerate(messages):
        if i in old_indices:
            masked.append({
                "role": "tool",
                "tool_call_id": msg["tool_call_id"],
                "content": "[Previous result omitted for brevity]",
            })
        else:
            masked.append(msg)
    return masked
```

This is the key finding from JetBrains: **simplicity often outperforms
sophistication**. Observation masking is deterministic, cache-friendly, and
introduces no additional API calls.

### 3. Context Compaction / Summarization (Production-Proven, More Complex)

When conversations get long enough that even observation masking is
insufficient, compress the conversation history into a summary.

**Anthropic's server-side compaction** (beta, launched January 2026):

The Claude API now offers built-in compaction. Enable it by adding
`compact_20260112` to `context_management.edits` in API requests. When input
tokens exceed a threshold, Claude automatically:
1. Generates a summary of the conversation
2. Creates a `compaction` block containing the summary
3. Drops all message blocks prior to the compaction block
4. Continues with compacted context

This is the recommended approach for Anthropic API users because it requires
minimal integration work and is handled server-side.

**Claude Code's implementation**: Auto-compact triggers at 95% context window
capacity (configurable via `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`). Uses recursive
or hierarchical summarization across agent trajectories. The auto-compact
buffer was reduced to ~33,000 tokens (16.5% of window) in v2.1.21.

**Factory.ai's anchored iterative summarization**: Rather than re-summarizing
the entire conversation each time, maintains anchor points at specific messages
with persisted summaries. When compression triggers, only newly-dropped spans
get summarized and merged into existing summaries. This avoids redundant
re-summarization and scored highest in their evaluation (3.70/5.0 overall vs
3.44 for Anthropic's approach and 3.35 for OpenAI's).

**Performance data from Anthropic**: Combining the memory tool with context
editing improved performance by 39% over baseline in a 100-turn web search
evaluation, while reducing token consumption by 84%.

**Key tradeoffs:**

- Summarization risks losing specific details (file paths, error messages,
  exact decisions). Factory.ai found all methods scored only 2.19-2.45/5.0 on
  artifact tracking despite explicit sections for files.
- LLM summarization adds cost and latency (the summarization call itself).
- Summaries can mask stopping signals, causing agents to continue
  unnecessarily (13-15% trajectory elongation per JetBrains).
- The right metric is "tokens per task" not "tokens per request" -- aggressive
  compression that causes re-fetching may cost more overall.

### 4. Structured Note-Taking / Scratchpads (For Complex Multi-Step Tasks)

Give the agent a tool to write persistent notes outside the context window.
The agent decides what to remember.

**Who does this:**

- **Anthropic's memory tool** (public beta): File-based system where agents
  create, read, update, and delete files in a dedicated memory directory.
  Storage is entirely client-side with developers managing the backend.

- **Manus**: Automatically creates and updates `todo.md` files, pushing task
  objectives into the model's recent attention window. This combats
  "lost-in-the-middle" drift during ~50-tool-call tasks.

- **Claude playing Pokemon**: Demonstrated structured note-taking maintaining
  progress across thousands of steps in a multi-hour operation.

**Implementation is straightforward** -- add a `write_note` / `read_notes`
tool that writes to a dictionary or file:

```python
notes: dict[str, str] = {}

def write_note(key: str, content: str) -> str:
    notes[key] = content
    return f"Note saved: {key}"

def read_notes() -> str:
    return json.dumps(notes, indent=2)
```

Then inject current notes into the system prompt or as the first user message
on each turn. The agent learns to externalize important state rather than
relying on everything staying in context.

### 5. Sub-Agent / Context Isolation (For Token-Heavy Subtasks)

Spawn a sub-agent with a clean context window for focused work, then return
only a condensed summary (typically 1,000-2,000 tokens) to the parent agent.

**Who does this:**

- **Anthropic's multi-agent researcher**: Multiple specialized sub-agents with
  isolated contexts outperformed single-agent approaches, largely because each
  sub-agent's context window could be allocated to a narrower sub-task.

- **OpenAI Swarm**: "Separation of concerns" where specialized agents handle
  sub-tasks with their own tools, instructions, and context windows.

- **Manus Wide Research**: Up to 100 parallel sub-agents operating
  simultaneously.

**The cost tradeoff**: Multi-agent architectures can use 15x more tokens than
single-agent approaches. This is worth it when the alternative is a single
agent drowning in a context window full of search results from 20 different
queries. It is overkill for simple sequential tasks.

**Cognition (Devin) counterpoint**: Single agents with long-context compression
deliver greater stability and lower costs than multi-agent setups for many
tasks. The industry has not settled this debate.

## What Is NOT Working

### Over-Reliance on LLM Summarization

JetBrains Research found that LLM summarization, despite being more
sophisticated, often underperforms simple observation masking. The summarization
call itself adds cost, and the summaries can cause trajectory elongation
(agents running 13-15% longer because summarized context masks natural stopping
signals).

### Naive Truncation (Dropping Oldest Messages)

Simply removing the oldest messages creates "jarring user experiences where
agents appear to forget previously discussed topics." Context loss from naive
truncation is well-documented as a failure mode.

### Artifact Tracking Through Summarization

All evaluated compression methods scored poorly (2.19-2.45/5.0) at tracking
which files were created, modified, or referenced. This remains an unsolved
problem. Dedicated artifact-tracking mechanisms outside the summarization
pipeline are needed.

### Generic Compression

Factory.ai found that "generic summarization treats all content as equally
compressible" when in reality different types of information have very different
importance. Structured summaries with explicit sections (session intent, file
modifications, decisions, next steps) significantly outperform unstructured
summaries.

## Recommended Approach for This Harness

Given the current architecture (simple agent loop, tools that return file
contents and search results, max 20 turns), a layered approach ordered by
implementation priority:

### Phase 1: Tool Result Caps (Immediate, High ROI)

Cap tool result sizes. The `read_file` and `search_files` tools can return
large payloads. Truncate results above a threshold and include a note about
total size so the agent knows to paginate if needed. This is a one-function
change.

### Phase 2: Observation Masking (When Tasks Get Longer)

Before sending messages to the API, mask tool results older than the last N
turns. Keep the tool call structure (so the model knows what it did) but
replace the content with a brief placeholder. This is a pre-processing step
on the messages list before each API call -- it does not modify the canonical
message history.

### Phase 3: Compaction (When Conversations Span Many Tasks)

Either use Anthropic's server-side compaction API (if using Claude models) or
implement client-side summarization that triggers at a configurable token
threshold. The server-side approach is strongly preferred because it requires
minimal code and avoids the pitfalls of client-side summarization.

### Phase 4: Scratchpad Tool (If Needed for Complex Multi-Step Work)

Add a note-taking tool that lets the agent externalize important state. Inject
current notes at the start of each turn. This becomes valuable when tasks
routinely involve 20+ tool calls where the agent needs to track progress,
decisions, and file modifications.

## KV-Cache Optimization (Cost Multiplier)

Manus identifies KV-cache hit rate as the single most important production
cost metric. With Claude, cached tokens cost $0.30/MTok versus $3/MTok
uncached -- a 10x savings.

**Practices that preserve cache hits:**

- Keep prompt prefixes stable (avoid timestamps or randomized content at the
  start of the system prompt)
- Make context append-only (never reorder messages)
- Use deterministic serialization for tool definitions
- Observation masking preserves cache better than summarization (masking only
  changes content later in the sequence, while summarization replaces the
  entire prefix)

**Practices that destroy cache hits:**

- Dynamically removing/reordering tools mid-conversation
- Regenerating system prompts with variable content
- Summarization that replaces the conversation prefix

This means observation masking is not just simpler -- it is also cheaper per
token because it preserves more of the KV-cache.

## What Leading Practitioners Say

**Anthropic** (engineering blog): "Find the smallest set of high-signal tokens
that maximize the likelihood of your desired outcome." Context engineering is
about curating an attention budget, not stuffing a context window. Tool result
clearing is "one of the safest, lightest-touch forms of compaction."

**Simon Willison**: Doing context engineering well "is both a science and an
art because of the guiding intuition around LLM psychology." The craft involves
task descriptions, few-shot examples, RAG, tools, state, history, and
compacting -- and doing it well is highly non-trivial.

**Lance Martin (LangChain)**: The four strategies are write, select, compress,
isolate. Context engineering is "effectively the number one job of engineers
building AI agents" (quoting Cognition). Recommends observability (tracing)
and evaluation as the foundation -- you cannot improve what you cannot measure.

**Manus team**: Treat the file system as infinite memory. Preserve error
traces in context (the model learns from its failures). Use `todo.md`
recitation to combat attention drift. KV-cache optimization provides 10x cost
reduction.

**JetBrains Research**: "Keeping things simple not only works, but works more
efficiently." Observation masking should be the default strategy. LLM
summarization should be used selectively, not universally.

**Martin Fowler / Thoughtworks**: Start minimal. Models have become powerful
enough that configurations necessary six months ago might not be necessary
anymore. Many teams effectively operate with just a project-level config file
and path-scoped rules.

## Open Questions

1. **When exactly does attention degradation become material?** There is no
   consensus on the token count at which "send everything" starts hurting
   quality. It depends on the model, the task, and the distribution of
   important information in the context.

2. **Is server-side compaction good enough?** Anthropic's API-level compaction
   is very new (January 2026 beta). Early benchmarks look strong, but
   production experience is limited.

3. **Artifact tracking**: No approach reliably tracks file modifications
   through compression. This matters for coding agents and is still unsolved.

4. **Single-agent + compression vs multi-agent**: Anthropic and Cognition
   disagree on which is better. The answer is likely task-dependent, but the
   boundary conditions are not well characterized.

5. **Optimal observation window size**: JetBrains found this needs tuning per
   agent architecture. There is no universal "keep the last N" number.

## Sources

- [Effective Context Engineering for AI Agents (Anthropic)](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [Context Management on Claude Developer Platform](https://claude.com/blog/context-management)
- [Compaction API Docs](https://platform.claude.com/docs/en/build-with-claude/compaction)
- [Context Engineering for Agents (Lance Martin / LangChain)](https://rlancemartin.github.io/2025/06/23/context_engineering/)
- [Context Engineering (LangChain Blog)](https://blog.langchain.com/context-engineering-for-agents/)
- [Context Management for Deep Agents (LangChain)](https://blog.langchain.com/context-management-for-deepagents/)
- [Context Engineering (Simon Willison)](https://simonwillison.net/2025/jun/27/context-engineering/)
- [Context Engineering for AI Agents: Lessons from Building Manus](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)
- [Compressing Context (Factory.ai)](https://factory.ai/news/compressing-context)
- [Evaluating Context Compression for AI Agents (Factory.ai)](https://factory.ai/news/evaluating-compression)
- [Efficient Context Management for LLM-Powered Agents (JetBrains Research)](https://blog.jetbrains.com/research/2025/12/efficient-context-management/)
- [Context Engineering for Coding Agents (Martin Fowler / Thoughtworks)](https://martinfowler.com/articles/exploring-gen-ai/context-engineering-coding-agents.html)
- [State of Agent Engineering (LangChain)](https://www.langchain.com/state-of-agent-engineering)
- [Context Window Management Strategies (Maxim)](https://www.getmaxim.ai/articles/context-window-management-strategies-for-long-context-ai-agents-and-chatbots/)
