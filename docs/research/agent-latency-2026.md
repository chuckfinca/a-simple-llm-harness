# Making Agentic LLM Systems Faster: 2026 Research

**Date:** 2026-03-15
**Context:** Our harness averages 6-20 sequential LLM round-trips per question,
taking 20-140 seconds total. We use OpenRouter with Qwen3-Coder (480B MoE,
35B active parameters). We recently collapsed 6 tools into a single `run_python`
tool. This document covers what's actually working to reduce agent latency in
2026, grounded in practitioner evidence.

---

## 1. What Practitioners Are Converging On

### The dominant latency insight: reduce round-trips, not token speed

Every significant latency win in 2026 comes from the same place: doing fewer
LLM inference passes. Each round-trip includes network overhead, queue wait
time on the provider, prefill computation over the full context, and sequential
token generation. For a prefill-heavy workload like ours (high input-to-output
token ratio), the prefill cost grows with every turn as conversation history
accumulates.

The math is straightforward. If each LLM call takes 3-7 seconds and we make
6-20 calls, the agent spends 18-140 seconds just waiting for inference. Tool
execution itself (running Python in Docker) is sub-second. The LLM is the
bottleneck, and the only way to meaningfully reduce wall-clock time is to
reduce the number of inference passes.

**Three convergent strategies for reducing round-trips:**

1. **Fewer, more capable tools** -- Vercel removed 80% of their tools (17 down
   to 2) and got 3.5x faster (274.8s to 77.4s average), 42% fewer steps, 37%
   fewer tokens, and success went from 80% to 100%. The mechanism: fewer tools
   means fewer decision points, less confusion, and the model batches more work
   per turn.

2. **Code-as-action** -- Let the model write code that calls multiple functions
   in a single tool invocation. Anthropic's Programmatic Tool Calling
   documentation states: "When Claude orchestrates 20+ tool calls in a single
   code block, you eliminate 19+ inference passes." Code-Mode benchmarks show
   67-88% latency reduction depending on complexity.

3. **Prompt engineering for planning** -- Pre-Act and Plan-and-Solve prompting
   techniques encourage the model to create a multi-step plan and execute it
   in fewer, more productive turns rather than one-action-per-turn ReAct style.

**Sources:**
- [Vercel: We removed 80% of our agent's tools](https://vercel.com/blog/we-removed-80-percent-of-our-agents-tools)
- [Anthropic: Advanced Tool Use](https://www.anthropic.com/engineering/advanced-tool-use)
- [UTCP Code Mode](https://github.com/universal-tool-calling-protocol/code-mode)
- [Pre-Act paper](https://arxiv.org/html/2505.09970v2)

---

## 2. Code-as-Tool-Use and Latency

### Our situation: we already collapsed to a single `run_python` tool

We moved from 6 tools (run_python, list_files, search_files, read_file,
calculator, get_current_time) to 1 tool (run_python, with the file operations
available as importable functions inside the sandbox). This is directionally
correct and aligns with the strongest practitioner pattern of 2026.

### Does collapsing tools inherently help latency?

**Yes, for two independent reasons:**

**Reason 1: Fewer tool definitions reduce decision overhead.** When a model
sees 6 tools, each turn involves a classification step: "which tool should I
call?" This classification can cause unnecessary intermediate turns ("let me
first list the files, then search, then read..."). With 1 tool, there is no
classification -- the model always calls `run_python` and batches the file
operations inside the code.

Vercel's data is the strongest evidence. Their agent went from averaging 12
steps to 7 steps just by reducing tool count. Each eliminated step is one fewer
LLM inference pass.

**Reason 2: Code lets the model compose operations.** When operations are
Python functions, the model can write `search_files("keyword")` followed by
`read_file(results[0])` in a single code block. When they are separate tools,
the model must make one tool call, receive the result, then make another tool
call. Two inference passes become one.

Anthropic measured 37% token reduction on complex research tasks. Code-Mode
benchmarks from UTCP show:
- Simple scenarios (2-3 tools): 67% faster
- Medium complexity (4-7 tools): 75% faster
- Complex workflows (8+ tools): 88% faster

### Are models actually batching more work into single code calls?

**The evidence says yes, with the right prompting.** Models trained on code
(which Qwen3-Coder specifically is) naturally write multi-step scripts. The
key insight from the Code-as-Action research (ICML 2024): "Python syntax
appears ubiquitously in training data, whereas custom tool schemas are novel
per-application." The model is more fluent at writing Python that chains
operations than at producing a sequence of JSON tool calls.

However, this is not automatic. Without prompting guidance, models may still
default to one-operation-per-call patterns, especially if the system prompt
or examples demonstrate single-step usage. The model needs signals that
batching is expected and rewarded.

### What to do: prompting for batch execution

The system prompt should explicitly encourage multi-step code blocks. The
Manus team's lesson is relevant: "the model tends to repeat patterns it sees
in context." If early turns show single-operation code blocks, the model will
continue that pattern. Conversely, if the system prompt shows or describes
multi-step execution, the model will follow suit.

Concrete prompting strategies that practitioners report working:
- "Combine multiple operations into a single code block when possible"
- "Search, read, and analyze in one step rather than separate steps"
- "Minimize the number of tool calls by doing more work per call"
- Showing a multi-step example in the system prompt (few-shot)

**Sources:**
- [Code as Action: The Pattern Behind Programmatic Tool Calling](https://www.ikangai.com/code-as-action-the-pattern-behind-programmatic-tool-calling/)
- [Manus: Context Engineering for AI Agents](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)
- [Vercel: We removed 80% of our agent's tools](https://vercel.com/blog/we-removed-80-percent-of-our-agents-tools)

---

## 3. Multi-Step Reasoning in One Call

### Can models do multiple steps per code block in 2026?

**Yes, and 2026 models are substantially better at this than 2024 models.**
Qwen3-Coder is specifically trained for "agentic coding tasks such as function
calling, tool use, and long-context reasoning over repositories." Its 256k
context window and MoE architecture are designed for the pattern of writing
multi-step scripts.

### Prompting techniques that encourage fewer turns

**Plan-and-Solve Prompting:** Ask the model to plan before executing. "First,
outline the steps needed, then execute them all in a single code block." The
research shows this reduces missing-step errors and produces more complete
single-turn solutions.

**Pre-Act:** Creates a multi-step execution plan with detailed reasoning for
each step, then executes incrementally. The planning phase identifies which
steps can be combined, leading to fewer but more productive turns.

**Structured instructions:** The simplest and most reliable technique. Make the
system prompt explicit about expectations:
- "Complete as much work as possible in each code block"
- "Do not make separate tool calls for operations that can be chained in code"
- "When researching, search AND read the relevant results in the same step"

**What does NOT help:** Asking the model to do everything in one giant step.
The anti-pattern research is clear: "Trying to pack too many distinct tasks
into a single LLM request often leads to hallucination, missing tasks, or
producing low-quality output." The goal is fewer turns, not one turn.

**The sweet spot** appears to be 3-6 productive turns for complex questions,
down from 8-20 turns with naive one-action-per-turn approaches. Each turn
does real analytical work rather than mechanical file operations.

**Sources:**
- [Plan-and-Solve Prompting](https://learnprompting.org/docs/advanced/decomposition/plan_and_solve)
- [Pre-Act paper](https://arxiv.org/html/2505.09970v2)
- [Agents At Work: The 2026 Playbook](https://promptengineering.org/agents-at-work-the-2026-playbook-for-building-reliable-agentic-workflows/)

---

## 4. Model Routing / Cascading

### Is using faster models for simple calls practical?

**Theoretically yes, practically complex for our architecture.**

The industry data: 60-70% of production LLM queries are "simple enough" for
cheaper models. RouteLLM demonstrates 85% cost reduction while maintaining 95%
quality. 37% of enterprises use 5+ models in production (IDC 2026).

### Why it is hard for tool-use agents

Model routing works well for request-level routing (different users or different
query types get different models). It works poorly for turn-level routing within
a single agent loop. The problems:

1. **Context coherence.** Each turn builds on the full conversation history.
   Switching models mid-conversation means the new model must re-process all
   prior context. With automatic prefix caching, this cache is per-model and
   per-provider -- switching models invalidates the cache.

2. **Tool-use format mismatch.** Different models handle tool calling syntax
   differently. Qwen3-Coder's tool call format may differ from a faster model's
   format. The harness would need to handle format translation, adding
   complexity.

3. **Classification overhead.** You need to classify each turn as "simple" or
   "complex" before routing, which itself adds latency (either a classifier
   call or heuristic logic).

4. **OpenRouter's sticky routing.** OpenRouter hashes the first system message
   to route to a consistent provider. Switching models mid-conversation may
   lose this benefit.

### When routing IS practical for us

**Between agent invocations, not within them.** If the harness receives a
question, a lightweight classifier could determine whether it needs the full
Qwen3-Coder agent loop or whether a simpler model can answer directly. This
avoids the mid-conversation switching problem entirely.

Example: "What time is it?" does not need 6 tool-calling turns. A fast model
answering directly takes 1-2 seconds vs. 20+ seconds for the full agent loop.

**The practical implementation:** A tiered system where simple factual questions
go to a fast model (Qwen3-Coder-Next with 3B active params, or a Qwen3.5
variant) and complex analytical questions go to the full agent with
Qwen3-Coder.

### Google's speculative cascades

Google Research published "Speculative Cascades" -- a hybrid approach combining
speculative decoding with model cascading. A small model generates candidate
tokens; a larger model verifies them in batches. This achieves 1.8-2.3x
throughput improvement at the inference infrastructure level.

**Relevance to us:** This is an infrastructure-level optimization, not
something we control through OpenRouter. If OpenRouter or the underlying Qwen
provider implements speculative decoding, we benefit automatically. Not
actionable from the harness layer.

**Sources:**
- [LLM Routing in Production (LogRocket)](https://blog.logrocket.com/llm-routing-right-model-for-requests/)
- [Intelligent LLM Routing (Swfte)](https://www.swfte.com/blog/intelligent-llm-routing-multi-model-ai)
- [Speculative Cascades (Google Research)](https://research.google/blog/speculative-cascades-a-hybrid-approach-for-smarter-faster-llm-inference/)
- [Multi-Model Routing Pattern](https://dev.to/askpatrick/the-multi-model-routing-pattern-how-to-cut-ai-agent-costs-by-78-1631)

---

## 5. Inference Infrastructure

### What we can influence from the harness layer

**Prefix caching** is the single most impactful infrastructure optimization
for agentic workloads. Manus reports that the KV-cache hit rate is "the single
most important metric for a production-stage AI agent," with their average
input-to-output token ratio at 100:1. Cached input tokens cost 10x less than
uncached on most providers.

**Our caching situation:**
- OpenRouter routes to Qwen3-Coder providers with automatic prefix caching
- OpenRouter uses sticky routing (hashes first system message) to keep the
  cache warm across turns
- Our tool definitions and system prompt are static across turns (good)
- Our `cache_hit=None` telemetry is unresolved -- we do not know if caching
  is actually working

**What helps caching from the harness:**
1. Keep the system prompt + tool definitions identical across all turns
2. Do not inject timestamps, session IDs, or per-request dynamic content into
   the prefix (the Manus team specifically warns about this)
3. Append messages only -- never modify previous messages
4. Use deterministic serialization (stable JSON key ordering)

### What we cannot influence

**Speculative decoding, KV cache quantization, disaggregated serving** -- these
are provider-side optimizations. QuantSpec achieves 2.5x speedup through
4-bit KV cache quantization. NVFP4 KV cache reduces memory footprint 50% vs.
FP8. KV-cache-aware routing (llm-d) routes requests to GPU workers that
already hold relevant cache entries. These are all running at the Kubernetes
and GPU level -- invisible to API consumers.

**SGLang's RadixAttention** achieves 85-95% cache hit rates and 29% higher
throughput than vLLM for agentic workloads. If the provider serving Qwen3-Coder
uses SGLang (vs. vLLM), we get this benefit automatically. We cannot control
this through OpenRouter.

### OpenRouter-specific considerations

OpenRouter's value for latency is sticky routing -- keeping the same provider
and therefore the same cache for a conversation. The risk is that OpenRouter
adds its own routing overhead (network hop to OpenRouter, then to provider).
For latency-critical workloads, going direct to the provider eliminates this
hop, but loses the routing and fallback benefits.

**Sources:**
- [Manus Context Engineering](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)
- [SGLang vs vLLM KV Cache (RunPod)](https://www.runpod.io/blog/sglang-vs-vllm-kv-cache)
- [QuantSpec (Apple ML Research)](https://machinelearning.apple.com/research/quantspec)
- [KV Cache Aware Routing with llm-d](https://llm-d.ai/blog/kvcache-wins-you-can-see)
- [OpenRouter Prompt Caching](https://openrouter.ai/docs/guides/best-practices/prompt-caching)

---

## 6. What to Watch Out For

### Anti-patterns that seem like they would help but do not

**1. Adding more specialized tools to "help" the model.**
The Vercel case study is the definitive counter-evidence. Their original 17-tool
system was designed to guide the model through a specific workflow (search
schema, validate joins, build query plan, etc.). Every tool was a decision
point and a potential wrong turn. Cutting to 2 tools and trusting the model
to reason freely produced better and faster results.

Anthropic's tool design guidance reinforces this: "If a human can't say which
tool to use, the AI can't either." Tool overlap (our former calculator +
run_python situation) causes the model to waste turns deliberating.

**2. Cramming everything into one giant prompt to avoid turns.**
Multiple sources warn against this. Packing too many distinct tasks into a
single LLM request "often leads to hallucination, missing tasks, or producing
low-quality output as its attention is divided." The goal is fewer, more
productive turns -- not one monolithic turn. Anthropic recommends "the smallest
set of high-signal tokens that maximize the likelihood of desired outcomes."

**3. Optimizing token generation speed when prefill dominates.**
For agentic workloads with high input-to-output ratios (Manus reports 100:1),
output token generation speed barely matters. The bottleneck is prefill --
processing the growing context window. A model that generates tokens 2x faster
but has the same prefill speed will show minimal wall-clock improvement.

The actionable insight: keep context small. Every tool result that enters the
conversation history makes every subsequent prefill slower. This is code-mode's
real win: intermediate results stay in the sandbox and never enter context.

**4. Multi-agent for latency reduction.**
Multi-agent architectures help with *parallelizable* workloads (search 5
sources simultaneously). They hurt for *sequential* workloads (analyze a
document step by step). Manus runs ~50 tool calls per task sequentially because
each step depends on the previous. Multi-agent would add coordination overhead
without parallelism benefit.

Anthropic's multi-agent research system improved quality (90.2% on internal
benchmarks) but the latency benefit only applies when subagents work
independently and concurrently. The cost is 15x more tokens.

For our workload (sequential document analysis), multi-agent adds complexity
and cost without latency benefit.

**5. Dynamic tool availability changes.**
Some frameworks add/remove tools between turns based on the conversation state.
Manus specifically warns against this: changing tool definitions invalidates
the KV cache prefix. Instead, they use logits masking to control which tools
the model can select while keeping the tool definitions stable. For our
single-tool architecture, this is not relevant -- but it is a trap to avoid
if we add tools later.

**6. Benchmarking with warm caches only.**
Production environments include cold starts, variable load, and provider queue
times. Testing only with warm caches gives misleadingly optimistic latency
numbers. Our 20-140 second range likely includes significant variance from
provider-side queuing, especially on the free or low-priority Qwen3-Coder
tiers.

**Sources:**
- [Vercel: We removed 80% of our agent's tools](https://vercel.com/blog/we-removed-80-percent-of-our-agents-tools)
- [Patterns and Anti-Patterns for LLMs (MLOps)](https://medium.com/marvelous-mlops/patterns-and-anti-patterns-for-building-with-llms-42ea9c2ddc90)
- [Why AI Agents Fail: Latency, Planning & Reflection](https://langcopilot.com/posts/2025-10-17-why-ai-agents-fail-latency-planning)
- [Agent Harness 2026 (Philipp Schmid)](https://www.philschmid.de/agent-harness-2026)
- [Manus Context Engineering](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)

---

## 7. Concrete Recommendations for Our Harness

Ordered by expected impact and implementation effort.

### High Impact, Low Effort

**A. Prompt the model to batch operations (immediate).**
Add explicit instructions to the system prompt encouraging multi-step code
blocks. "Combine file searches, reads, and analysis into a single code block
whenever possible. Minimize the number of tool calls." Based on Manus and
Vercel evidence, this alone could reduce turns by 30-50%.

**B. Verify prefix caching is working (immediate).**
The `cache_hit=None` in telemetry remains our biggest unknown. If caching is
not active, every turn reprocesses the full conversation from scratch. Check
OpenRouter's response headers or usage object for cache metrics. If caching
is not reported, test by going direct to a Qwen provider that reports it.

**C. Keep context lean (ongoing).**
Tool results accumulate in the conversation history and slow down every
subsequent prefill. Consider truncating or summarizing large tool outputs
before appending them to messages. If `run_python` returns a 10KB DataFrame
printout but the model only needs a 200-byte summary, the model could
`print()` only the summary -- and the system prompt could encourage this.

### High Impact, Medium Effort

**D. Prompt for planning before execution (prompt iteration).**
Add a planning instruction: "Before writing code, briefly state what you need
to find and how you'll find it." Plan-and-Solve research shows this reduces
missing-step errors and produces more complete solutions per turn. The risk
is adding a "thinking" turn that does not do real work -- the instruction
should be "plan AND execute in the same turn."

**E. Pre-classify question complexity (harness change).**
Simple questions (time, basic math, factual recall) do not need the full agent
loop. A lightweight check before entering `_run_loop` could short-circuit:
if the question is simple enough, call the model once without tools. This
avoids 5+ unnecessary turns for trivial queries.

### Medium Impact, Higher Effort

**F. Context compaction between turns.**
After N turns, summarize the conversation so far and replace older messages
with the summary. This bounds prefill growth. Manus uses the filesystem as
external memory for this purpose (agent writes intermediate findings to files,
then reads them back when needed rather than keeping everything in context).

**G. Parallel tool execution for independent calls.**
Our agent loop processes tool calls sequentially (line 116-143 in agent.py).
If the model emits multiple tool calls in a single response, they could
execute concurrently (asyncio.gather or ThreadPoolExecutor). This only helps
if the model actually emits parallel tool calls, which is more common with
multiple tools than with our single `run_python` tool. Lower priority given
our architecture.

### Watch and Wait

**H. Model routing between invocations.**
Route simple questions to a faster/cheaper model, complex questions to the
full agent. Practical value depends on the distribution of question complexity.
Wait until we have trace data showing how many questions genuinely need 10+
turns vs. could be answered in 1-2 turns.

**I. Direct provider access (bypass OpenRouter).**
Eliminates one network hop. Worth testing when latency data shows that
per-turn overhead (not total turns) is the bottleneck. Currently, reducing
turns is higher leverage than reducing per-turn time.

---

## 8. The Big Picture: Where This Is Going

### The harness is thinning

Philipp Schmid (2026): "Capabilities that required complex, hand-coded
pipelines in 2024 are now handled by a single context-window prompt in 2026."
The trend is toward simpler harnesses with fewer moving parts. Manus
refactored their harness five times in six months to remove rigid assumptions.
The advice: "Build to Delete" -- construct architectures where obsolete logic
can be quickly removed when models improve.

### The competitive moat is the orchestration layer

Can Boluk's experiment (Feb 2026): Changing only the harness improved 15 LLMs
by 5-14 points. One model jumped from 6.7% to 68.3% -- a 10x improvement from
harness changes alone. Anthropic, Martin Fowler, and OpenAI have all published
the same conclusion: the harness matters more than the model.

For our harness, this means the system prompt, tool design, and context
management strategy have more impact on speed and quality than switching models.

### Code mode is the future, hybrid is the present

Every production implementation in 2026 supports both structured tool calls
and code execution simultaneously. Pure code-only struggles with weak models.
Pure tool-only struggles with complex chained operations. The hybrid approach
(simple actions as direct tool calls, complex chains as code) consistently
outperforms both pure approaches by 2-7 percentage points.

Our single-`run_python` architecture is the right direction but is "pure
code-only." If we find cases where the model struggles with code-based file
operations, having a few direct tool calls as fallbacks is the industry pattern.

**Sources:**
- [Agent Harness 2026 (Philipp Schmid)](https://www.philschmid.de/agent-harness-2026)
- [The Harness Problem (Can Boluk)](https://blog.can.ac/2026/02/12/the-harness-problem/)
- [HuggingFace Structured Code Agents](https://huggingface.co/blog/structured-codeagent)
- [Code Mode 2026 Landscape](../../docs/research/code-mode-2026-landscape.md)

---

## Sources Index

### Practitioner Case Studies
- [Vercel: We removed 80% of our agent's tools](https://vercel.com/blog/we-removed-80-percent-of-our-agents-tools)
- [Manus: Context Engineering for AI Agents](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)
- [Anthropic: Advanced Tool Use](https://www.anthropic.com/engineering/advanced-tool-use)
- [The Harness Problem (Can Boluk)](https://blog.can.ac/2026/02/12/the-harness-problem/)

### Architecture & Patterns
- [Agent Harness 2026 (Philipp Schmid)](https://www.philschmid.de/agent-harness-2026)
- [Agents At Work: The 2026 Playbook](https://promptengineering.org/agents-at-work-the-2026-playbook-for-building-reliable-agentic-workflows/)
- [Code as Action Pattern](https://www.ikangai.com/code-as-action-the-pattern-behind-programmatic-tool-calling/)
- [UTCP Code Mode](https://github.com/universal-tool-calling-protocol/code-mode)

### Prompting Techniques
- [Plan-and-Solve Prompting](https://learnprompting.org/docs/advanced/decomposition/plan_and_solve)
- [Pre-Act: Multi-Step Planning](https://arxiv.org/html/2505.09970v2)

### Infrastructure
- [SGLang vs vLLM KV Cache (RunPod)](https://www.runpod.io/blog/sglang-vs-vllm-kv-cache)
- [QuantSpec (Apple ML Research)](https://machinelearning.apple.com/research/quantspec)
- [KV Cache Aware Routing (llm-d)](https://llm-d.ai/blog/kvcache-wins-you-can-see)
- [OpenRouter Prompt Caching](https://openrouter.ai/docs/guides/best-practices/prompt-caching)
- [Speculative Cascades (Google)](https://research.google/blog/speculative-cascades-a-hybrid-approach-for-smarter-faster-llm-inference/)

### Model Routing
- [LLM Routing in Production (LogRocket)](https://blog.logrocket.com/llm-routing-right-model-for-requests/)
- [Multi-Model Routing Pattern](https://dev.to/askpatrick/the-multi-model-routing-pattern-how-to-cut-ai-agent-costs-by-78-1631)
- [Intelligent LLM Routing (Swfte)](https://www.swfte.com/blog/intelligent-llm-routing-multi-model-ai)

### Anti-Patterns & Pitfalls
- [Why AI Agents Fail: Latency](https://langcopilot.com/posts/2025-10-17-why-ai-agents-fail-latency-planning)
- [Patterns and Anti-Patterns for LLMs](https://medium.com/marvelous-mlops/patterns-and-anti-patterns-for-building-with-llms-42ea9c2ddc90)
- [LLM Performance Bottlenecks 2026](https://www.glukhov.org/llm-performance)
