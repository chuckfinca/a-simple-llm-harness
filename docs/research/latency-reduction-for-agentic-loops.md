# Latency Reduction for Agentic Tool-Use Loops

**Date:** 2026-03-15
**Context:** Our harness sends system prompt + conversation history + tool definitions
to an LLM (via OpenRouter, currently Qwen3-Coder) in a sequential loop. Each eval
question takes 20-140 seconds across 6-20 tool calls. We migrated to a single
`run_python` tool (code-as-tool-use) which reduced tool definitions but increased
average tool calls per question. This document catalogs proven techniques for
reducing end-to-end latency.

---

## 1. Where Our Latency Goes

Our agent loop (in `agent.py`) is strictly sequential:

```
for each turn (up to max_turns):
    1. Send messages + tools to LLM  (TTFT wait + generation)
    2. Parse response
    3. For each tool_call in response:
        a. Execute tool (Docker sandbox)
        b. Append result to messages
    4. Go to 1
```

For a 10-turn question, we pay 10 round-trip LLM calls plus 10+ tool executions.
The dominant cost is LLM inference: TTFT (prefill) grows with input length, and
each turn adds previous tool calls to the context. Tool execution (Docker sandbox)
adds 500ms-2s per call on top.

The latency equation per turn is roughly:

    turn_latency = TTFT(context_length) + generation_time(output_tokens) + tool_execution_time

Total latency = sum of all turns. TTFT increases each turn as context grows.

---

## 2. Prompt Caching / Prefix Caching

### What It Is

LLM providers cache the KV tensors computed during the prefill phase. When a
subsequent request shares the same prefix (system prompt, tool definitions, early
conversation history), the provider skips recomputing those tensors. This directly
reduces TTFT.

### Impact on Agentic Loops

A January 2026 paper ("Don't Break the Cache") measured prompt caching across
providers for long-horizon agent tasks:

- **Cost reduction:** 45-80% depending on provider/model
- **TTFT reduction:** 13-31% across providers
- **Agents are the best case for caching:** Input-to-output ratios exceed 100:1
  in typical agent loops. The static prefix (tools + system prompt) is resent
  every turn, and the conversation history grows monotonically.

Each cached input token saves approximately 0.15ms of TTFT. For our harness,
the static prefix (system prompt + 1 tool definition) is only ~400-600 tokens.
But by turn 10, conversation history could be 5,000-20,000 tokens, and the
prefix of that history (turns 1-9) is identical to what was sent in turns 2-9.
This is where caching pays off most.

### Critical Gotcha: Don't Cache Dynamic Content

The paper found that "naively enabling full-context caching can paradoxically
increase latency." Tool results are session-specific and won't be reused across
different agent runs. On providers with explicit caching (Anthropic), placing
cache breakpoints on dynamic content wastes cache write budget.

**Recommended pattern:** Cache only the stable prefix (tools + system prompt).
Let automatic prefix caching handle the growing conversation history -- the
provider will naturally cache the shared prefix between consecutive turns within
the same conversation.

### Provider Support (March 2026)

| Provider | Caching Type | Min Tokens | Read Discount | Write Cost | Notes |
|----------|-------------|------------|---------------|------------|-------|
| Anthropic | Explicit (breakpoints) | 1,024 | 90% | 1.25x (5min TTL) | Most configurable |
| OpenAI | Automatic | 1,024 | 50-75% | Free | 128-token granularity |
| DeepSeek | Automatic | 64 | ~90% | 1x (standard) | Best granularity |
| Google | Automatic | Varies | ~75% | Free | Gemini models |
| Qwen (direct) | Explicit | 1,024 | Unknown | Unknown | Marker-based |
| OpenRouter | Pass-through | Depends on backend | Depends on backend | Depends on backend | Sticky routing keeps cache warm |

### What This Means for Us

Our setup (Qwen3-Coder via OpenRouter) should get automatic prefix caching via
OpenRouter's sticky routing, which hashes the system message to route consecutive
requests to the same backend. However, we have `cache_hit=None` in our telemetry,
so we cannot confirm this is working.

**Immediate action:** The caching benefit is real but we need to verify it is
actually happening. See `token-caching-and-tool-definitions.md` for the full
analysis. The biggest wins come from keeping our static prefix stable across turns
(already done -- our tool definitions and system prompt are fixed).

---

## 3. Reducing Round-Trips

This is the highest-leverage technique for our harness. Every LLM round-trip adds
TTFT + generation time + tool execution. Fewer turns = less latency.

### 3a. Code-as-Tool-Use (Already Done)

We already migrated to `run_python` as the single tool. The CodeAct research
showed **up to 30% fewer turns** compared to individual tool calls because the
model can chain multiple operations in a single code block.

Our specific pattern: instead of separate `list_files`, `read_file`, `search_files`
calls that each require a round-trip, the model writes Python that calls all three
as functions within one `run_python` invocation. One LLM turn does the work of 3.

**Caveat observed in our traces:** The migration increased average tool calls
because the model sometimes writes shorter, more incremental code blocks. This is a
prompt engineering problem, not an architecture problem. The system prompt should
encourage the model to batch operations into single code blocks.

### 3b. Prompt the Model to Batch

Explicit instructions to batch operations can meaningfully reduce turns:

```
When you need to read multiple files or perform multiple operations,
combine them into a single run_python call rather than separate calls.
```

This is a free optimization -- zero infrastructure cost, just prompt text.

### 3c. Dynamic Turn Limits

Research from Anthropic (via LangChain's compilation): Dynamic turn limits based
on estimated probability of success cut costs by 24% while maintaining solve
rates. The idea: if the model has been going in circles for 5 turns without
progress, exit early rather than burning through remaining budget.

For evals, this is less about latency reduction and more about avoiding the long
tail -- cutting off the 140-second runs that were going to fail anyway.

### 3d. Parallel Tool Calls

When a model emits multiple tool calls in a single response, the harness can
execute them in parallel rather than sequentially.

**Model support (March 2026):**
- OpenAI GPT-4o/5: Full support, well-documented
- Anthropic Claude: Full support
- Open-source (DeepSeek, Qwen): Minimal benefit -- a Feb 2026 paper (W&D) found
  "open-source models showed minimal improvements" from parallel calling, suggesting
  training limitations

**Measured impact (from W&D paper):**
- 3 parallel tool calls: 40.6% wall-clock reduction, 35.9% cost reduction
- Scales consistently -- more parallel width = better performance
- Reduces total turns needed (fewer sequential steps)

**Our situation:** Our agent loop in `agent.py` already handles multiple tool calls
per response (the `for tool_call in assistant_msg["tool_calls"]` loop). But it
executes them sequentially. Parallel execution would help if the model emits
multiple `run_python` calls, though with a single tool type this is less common
than with multiple specialized tools. More importantly, Qwen3-Coder may not
reliably emit parallel calls due to the open-source training limitation noted above.

**Implementation if we pursue it:** Replace the sequential tool call loop with
`concurrent.futures.ThreadPoolExecutor` or `asyncio.gather()`. Low engineering
effort, but the benefit depends on how often the model actually emits parallel
calls.

---

## 4. Model Selection for Speed

### The Speed/Quality Landscape (March 2026)

Model selection is probably the easiest lever to pull. Latency varies 10x+ across
models for similar quality.

**Fastest models for tool use via OpenRouter:**

| Model | TTFT (median) | Throughput (tok/s) | Tool-Use Quality | Notes |
|-------|---------------|-------------------|------------------|-------|
| Claude Haiku 4.5 | ~600ms | ~79 | Excellent | Fastest premium tool-use |
| Gemini 3.1 Flash Lite | Very low | Very high | Good | 2.5x faster TTFT than 2.5 Flash |
| o4-mini | Low | High | Excellent | Optimized for tool use specifically |
| Gemini 2.5 Flash | Medium | ~147 | Good | Best raw throughput |
| Qwen3-Coder-Next (3B active) | ~430ms (Together) | ~127 | Good for code | MoE, very efficient |
| DeepSeek V3.2 | Medium | Medium | Good | Cheapest per token |

**Key insight:** For sequential agentic loops, TTFT matters more than throughput.
Each turn is a new request. A model with 400ms TTFT and 80 tok/s generating a
100-token response takes 1.65s per turn. A model with 1200ms TTFT and 150 tok/s
takes 1.87s. Over 10 turns, the TTFT-optimized model saves 2.2 seconds -- and
the gap widens with fewer output tokens per turn (common in tool-calling responses
which are often just a function call with arguments).

### OpenRouter Routing Variants

OpenRouter offers routing variants that affect latency:

- **`:nitro`** -- Sorts providers by throughput (tokens/second). Append to model
  ID: `qwen/qwen3-coder:nitro`. Best for maximizing generation speed.
- **`:exacto`** -- Routes to providers with highest tool-calling accuracy based on
  real-world telemetry. Use for reliability-critical agentic workflows.
- Default routing balances cost and quality.

**For our eval runs:** `:nitro` is worth testing. It costs nothing to add and may
route to faster Qwen3-Coder providers.

### Mercury 2 (Diffusion Model)

Inception Labs' Mercury 2 achieves 756 tokens/second -- 5x faster than standard
autoregressive models -- using parallel refinement instead of sequential decoding.
However, it is a specialized model and tool-use capability is unverified. Worth
watching but not actionable for us today.

---

## 5. Token Budget Engineering

Every token in the input adds to TTFT. Every token in the output adds to
generation time. Reducing token count is a direct latency reduction.

### 5a. Compact Tool Results

Our code-as-tool-use pattern already helps here: intermediate results from
`list_files`, `read_file`, etc. stay inside the Docker sandbox and only the final
`print()` output enters the context window. This is the "37-99% token reduction"
finding from our `code-as-tool-orchestration.md` research.

**But:** The model still prints more than necessary. System prompt guidance to
print only what's needed (not entire file contents when a summary would do) can
further reduce context growth.

### 5b. Observation Masking

JetBrains Research (Dec 2025) compared three approaches:

1. **Raw (no management):** Baseline. Context grows unbounded.
2. **Observation masking:** Replace older tool results with placeholders after
   a rolling window (e.g., 10 turns). Keep reasoning/action history intact.
3. **LLM summarization:** Compress older interactions with a separate LLM call.

**Results with Qwen3-Coder 480B:**
- Observation masking: **52% cost reduction, +2.6% solve rate improvement**
- LLM summarization: Similar cost reduction but agents ran **15% longer** --
  summaries "smoothed over signs the agent should stop trying"

Observation masking is the clear winner for latency because it requires no
additional LLM calls and it reduces context length for subsequent turns.

**Implementation for us:** After turn N, replace tool result content in messages
older than the last K turns with a placeholder like `"[previous result omitted]"`.
This is a simple modification to the message list before each LLM call, requiring
~10 lines of code in `agent.py`.

### 5c. Large Result Offloading (LangChain Deep Agents Pattern)

When a tool result exceeds a threshold (LangChain uses 20,000 tokens), move it to
the filesystem and substitute a reference + preview:

```
[Full result written to /tmp/result_3.txt. First 10 lines shown below:]
...
```

This prevents a single large tool result from blowing up context for all
subsequent turns. Less relevant for us currently (our results are typically small)
but worth knowing for future spreadsheet/data work.

### 5d. Acon: Agent Context Optimization

An October 2025 paper introduced Acon, a systematic framework for adaptive context
compression:

- Reduces peak token usage by **26-54%** while maintaining task performance
- The compression can be distilled into smaller models (no LLM call needed)
- Uses learned policies to decide what to compress vs. keep

This is more complex than observation masking but shows the ceiling for context
compression approaches.

### 5e. Prompt Conciseness

Every token in the system prompt is paid on every turn. Our system prompt is
~200-400 tokens, which is reasonable. But if it were 2,000 tokens, we would be
paying 2,000 extra tokens * 10 turns = 20,000 extra input tokens per question.

The tool description for `run_python` is short (~50 tokens). Good -- this was one
benefit of collapsing to a single tool.

---

## 6. Streaming and Early Termination

### Streaming

Streaming shows the model's output as it generates, reducing *perceived* latency
but not *actual* latency. For agentic loops running evals, streaming does not help
because we need the complete response before we can execute tools.

**Exception:** If we build a user-facing mode, streaming the model's reasoning/
text to the user while tools execute in parallel would help UX. The Vercel AI SDK
provides clean abstractions for this, including abort signals and tool-call
detection during streaming.

### Stop Sequences / Early Termination

When the model outputs a tool call, there is no wasted generation -- the model
stops at the tool call boundary (finish_reason = "tool_calls"). This is handled
by the API provider.

For text responses, models sometimes generate verbose answers after arriving at
the conclusion. A `max_tokens` limit on completion can prevent this, but risks
truncating useful content.

**Not actionable for us:** Our bottleneck is number of turns, not generation
length per turn. Tool-call responses are typically short (just the function call
arguments).

---

## 7. Infrastructure-Level Optimizations

### Speculative Decoding

Speculative decoding uses a smaller "draft" model to predict tokens, then
verifies them with the target model in parallel. 2026 state of the art:

- **ArcticInference (Snowflake):** Up to 4.5x latency reduction for agent tasks.
  Built on SuffixDecoding, which exploits the repetitive/predictable nature of
  agent inference requests.
- **Mirror-SD (Apple):** 2.8-5.8x wall-time speedups.
- **Saguaro:** Up to 5x faster than autoregressive decoding.

**For us:** These are inference-engine optimizations. We do not control this -- our
provider (OpenRouter -> Qwen backend) decides whether to use speculative decoding.
But it matters for model/provider selection: providers using SGLang or vLLM with
speculative decoding will have lower TTFT for the same model.

### SGLang's RadixAttention

SGLang automatically reuses KV cache for shared prompt prefixes across requests.
For agentic workflows where every request starts with the same 1,000+ token
prefix, this provides lower TTFT than standard vLLM. SGLang and LMDeploy are the
fastest inference engines in 2026, both delivering ~16,200 tokens/second on H100.

**For us:** If we ever self-host or choose providers, prefer those running SGLang.
Via OpenRouter, this is opaque -- we cannot see which inference engine a provider
uses.

### OpenRouter-Specific Optimizations

1. **Keep account balance above $10-20.** Low balances trigger additional database
   checks that add latency to every request.
2. **Use `:nitro` variant** for throughput-optimized routing.
3. **Use `:exacto` variant** for tool-calling accuracy (may trade latency for
   reliability).
4. **Sticky routing is automatic** -- OpenRouter hashes the first system message
   to route consecutive requests to the same provider, keeping KV caches warm.

---

## 8. What We Should Do (Ranked by Effort/Impact)

### Tier 1: Free or Near-Free (Do Now)

1. **Try `:nitro` routing.** Change model string from `qwen/qwen3-coder` to
   `qwen/qwen3-coder:nitro`. Zero code change, potentially faster provider.
   Measure TTFT before and after.

2. **Prompt the model to batch operations.** Add guidance to the system prompt
   encouraging multi-operation code blocks. Reduces turns, which is the biggest
   latency lever. Costs nothing but prompt iteration time.

3. **Verify prompt caching is working.** Check OpenRouter dashboard or response
   headers for cache hit metrics. The `cache_hit=None` in telemetry is the
   biggest unknown -- if caching is not working, fixing it could cut TTFT by
   13-31% on every turn after the first.

### Tier 2: Low Effort, High Impact (This Week)

4. **Implement observation masking.** After each turn, truncate tool results
   older than the last K turns (start with K=5). JetBrains measured 52% cost
   reduction and improved solve rates with Qwen3-Coder. This directly reduces
   TTFT on later turns by shrinking the context.

5. **Test alternative models.** Run the eval suite against Claude Haiku 4.5 and
   Gemini 2.5 Flash via OpenRouter. Both have much lower TTFT than Qwen3-Coder
   and strong tool-use capabilities. Compare latency * quality.

### Tier 3: Medium Effort (This Month)

6. **Parallelize tool execution.** Modify the tool call loop in `agent.py` to
   use `concurrent.futures.ThreadPoolExecutor` when the model emits multiple tool
   calls. Benefit depends on how often this happens (may be rare with a single
   `run_python` tool).

7. **Dynamic turn limits.** Track progress between turns (is the model making
   progress or going in circles?) and exit early if probability of success is
   low. Cuts the long tail of 100+ second runs.

8. **Context window monitoring.** Add per-turn context length tracking to
   telemetry. This gives visibility into whether context growth is actually
   driving latency increases, and whether observation masking is helping.

### Tier 4: Larger Investment (Future)

9. **Model routing / tiering.** Use a cheap/fast model (Haiku, Flash) for simple
   turns (file listing, reading) and a capable model (Qwen3-Coder, Sonnet) for
   complex reasoning. Requires a router or heuristic to classify turn complexity.
   Anthropic's pattern: "Opus reaches optimal in 4 iterations vs 10 for Sonnet,
   cutting orchestration overhead by 60%." Sometimes a more capable model is
   faster because it needs fewer turns.

10. **Self-hosted inference with SGLang.** If we need maximum control over TTFT
    and caching, self-hosting with SGLang + RadixAttention gives the best prefix
    caching behavior. Major infrastructure investment.

---

## 9. The Counter-Intuitive Insight

**Sometimes a more expensive model is faster.** Anthropic found that Opus reaches
optimal solutions in 4 iterations vs 10 for Sonnet. If our Qwen3-Coder takes 12
turns at 8 seconds each (96 seconds total), and Claude Sonnet takes 6 turns at
12 seconds each (72 seconds total), the "slower" model per-turn is faster
end-to-end.

This means model selection for latency is not just about TTFT and throughput --
it's about turns-to-solution. A model that reasons better needs fewer round-trips.

**Implication:** When benchmarking models for our harness, measure total
end-to-end time per eval question, not per-turn latency. The model that minimizes
total time may not be the one with the lowest TTFT.

---

## Sources

### Papers
- [Don't Break the Cache: Prompt Caching for Agentic Tasks](https://arxiv.org/html/2601.06007v1) (Jan 2026)
- [W&D: Scaling Parallel Tool Calling for Deep Agents](https://arxiv.org/pdf/2602.07359) (Feb 2026)
- [Acon: Optimizing Context Compression for Long-Horizon Agents](https://arxiv.org/html/2510.00615v2) (Oct 2025)
- [Trajectory Reduction for LLM Agent Efficiency](https://arxiv.org/html/2509.23586v1) (Sep 2025)
- [CodeAct: Executable Code Actions](https://arxiv.org/html/2402.01030v4) (Feb 2024, updated)

### Production Experience
- [LangChain: How Do I Speed Up My Agent?](https://blog.langchain.com/how-do-i-speed-up-my-agent/)
- [LangChain: Context Management for Deep Agents](https://blog.langchain.com/context-management-for-deepagents/)
- [JetBrains Research: Efficient Context Management](https://blog.jetbrains.com/research/2025/12/efficient-context-management/)
- [Anthropic: Advanced Tool Use](https://www.anthropic.com/engineering/advanced-tool-use)
- [Can Boluk: The Harness Problem](https://blog.can.ac/2026/02/12/the-harness-problem/)

### Model Benchmarks
- [Artificial Analysis: Model Leaderboard](https://artificialanalysis.ai/leaderboards/models)
- [LLM API Latency Benchmarks 2026](https://www.kunalganglani.com/blog/llm-api-latency-benchmarks-2026)
- [Qwen3-Coder-Next Provider Benchmarks](https://artificialanalysis.ai/models/qwen3-coder-next/providers)
- [SiliconFlow: Fastest Open Source LLMs 2026](https://www.siliconflow.com/articles/en/fastest-open-source-LLMs)

### OpenRouter
- [OpenRouter: Latency and Performance](https://openrouter.ai/docs/guides/best-practices/latency-and-performance)
- [OpenRouter: Nitro Variant](https://openrouter.ai/docs/guides/routing/model-variants/nitro)
- [OpenRouter: Exacto Variant](https://openrouter.ai/docs/guides/routing/model-variants/exacto)
- [OpenRouter: Provider Routing](https://openrouter.ai/docs/guides/routing/provider-selection)
- [OpenRouter: Prompt Caching](https://openrouter.ai/docs/guides/best-practices/prompt-caching)

### Inference Infrastructure
- [Snowflake ArcticInference / SuffixDecoding](https://www.cs.cmu.edu/~csd-phd-blog/2025/suffix-decoding/)
- [vLLM vs SGLang vs LMDeploy: Fastest Inference 2026](https://blog.premai.io/vllm-vs-sglang-vs-lmdeploy-fastest-llm-inference-engine-in-2026/)
- [KV Cache Wins: Prefix Caching in vLLM](https://llm-d.ai/blog/kvcache-wins-you-can-see)
- [Inception Labs: Mercury 2](https://www.inceptionlabs.ai/blog/introducing-mercury-2)

### Our Previous Research
- [Token Caching and Tool Definitions](./token-caching-and-tool-definitions.md)
- [Code-as-Tool Orchestration](./code-as-tool-orchestration.md)
- [Code Mode 2026 Landscape](./code-mode-2026-landscape.md)
- [Context Window Management](./context-window-management.md)
