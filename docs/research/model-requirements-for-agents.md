# Model Requirements for Reliable Agentic Tool Use

Research date: 2026-03-06

## Context

We have a simple LLM harness with regex search tools over a text corpus. Gemini
2.5 Flash was given detailed system prompt instructions to search with multiple
terms (synonyms, morphological variants). It ignored them -- did a single search
and stopped. This research investigates whether the failure is a model capability
issue, a prompt issue, or both, and what the practical options are.

---

## 1. Benchmarks for Tool Use

### BFCL (Berkeley Function Calling Leaderboard)

BFCL is the de facto standard for evaluating function calling. It has evolved
through four versions:

- **BFCL v1**: AST-based evaluation of single function calls
- **BFCL v2**: Enterprise and OSS-contributed function schemas
- **BFCL v3**: Multi-turn interactions
- **BFCL v4** (current, updated 2025-12-16): Holistic agentic evaluation --
  tests tool use as part of an integrated agentic system, not just discrete calls

**Top BFCL v4 scores (as of late 2025):**

| Model                  | Score  |
|------------------------|--------|
| GLM-4.5 (FC)           | 70.85% |
| Claude Opus 4.1        | 70.36% |
| Claude Sonnet 4        | 70.29% |
| GPT-5                  | 59.22% |

Key finding: **The top score is only ~71%.** Even the best models fail on
roughly 30% of agentic tool-use tasks. This is not a solved problem.

### MCPMark (Multi-Step MCP Benchmark)

MCPMark tests realistic multi-step workflows averaging 16.2 execution turns and
17.4 tool calls per task. This is the closest benchmark to our search scenario.

**MCPMark results (pass@1):**

| Model              | Score  |
|--------------------|--------|
| GPT-5 Medium       | 52.6%  |
| Claude Opus 4.1    | 29.9%  |
| Claude Sonnet 4    | 28.1%  |
| o3                 | 25.4%  |
| Qwen-3-Coder       | 24.8%  |

Critical insight: **Models that dominate BFCL (single/few-step) collapse on
MCPMark (multi-step).** Claude leads BFCL but falls far behind GPT-5 on MCPMark.
This confirms that single-step function calling ability does not predict
multi-step agentic reliability.

### SWE-bench Verified (February 2026)

SWE-bench tests multi-step coding agent capability on real GitHub issues.

| Rank | Model                              | Score  |
|------|------------------------------------|--------|
| 1    | Claude 4.5 Opus (high reasoning)   | 76.8%  |
| 2    | Gemini 3 Flash (high reasoning)    | 75.8%  |
| 3    | MiniMax M2.5 (high reasoning)      | 75.8%  |
| 4    | Claude Opus 4.6                    | 75.6%  |
| 5    | GLM-5 (high reasoning)             | 72.8%  |
| 6    | GPT-5.2 (high reasoning)           | 72.8%  |
| 7    | Claude 4.5 Sonnet (high reasoning) | 72.8%  |
| 8    | Kimi K2.5 (high reasoning)         | 71.4%  |
| 9    | DeepSeek V3.2 (high reasoning)     | 70.8%  |
| 10   | Claude 4.5 Haiku (high reasoning)  | 70.0%  |

Note: SWE-bench Pro (harder, more realistic) shows massive drops -- the best
models score only ~23% on Pro vs ~75% on Verified. Multi-step tool use remains
the hard part.

### Key Takeaway

There is a clear capability hierarchy. Basic tool calling (name validity, schema
compliance) has converged across models at 95%+. The gap emerges in higher-order
reasoning: knowing when NOT to call a tool, managing context across turns,
strategic planning of multi-step sequences, and iterating based on results. This
is exactly the capability our search task requires.

---

## 2. Gemini Flash: Known Problems

### Documented Issues

Gemini 2.5 Flash has well-documented, systemic problems with function calling,
confirmed across multiple developer reports:

**Unreliable invocation**: The model generates plain text responses instead of
invoking functions, despite correct schemas and API configuration. The same query
produces random results -- sometimes triggering function calls, sometimes plain
text. (Google AI Developer Forum, multiple threads)

**Refusing tool calls**: Gemini 2.5 Flash systematically refuses to execute tool
calls that work on other Gemini models, returning `blockReason: "OTHER"` without
invoking functions. Issues worsen with complex requests. (GitHub issues, Google
forums)

**Multi-turn degradation**: After several tool calls, the model starts
outputting markdown code blocks instead of actually calling tools. Multi-turn
validation errors occur because the model returns unexpected signatures in
responses. (LiteLLM GitHub issue #17949)

**Thinking mode conflicts**: Tool calling is more reliable with thinking mode
disabled. When thinking is enabled, the model attempts to end conversations
prematurely or fails to invoke tools. Google acknowledged the bug in June 2025;
developers continued reporting issues through September 2025.

**Quality regression**: The preview model outperforms the production release,
suggesting rushed releases.

### Flash vs Pro

Google's own positioning is clear: "Cases where you need the highest intelligence
and most capabilities are where you will see Pro shine, like coding and agentic
tasks." Flash is optimized for speed and cost (15x cheaper, ~163 tokens/sec),
not for complex agentic reasoning.

Gemini 2.5 Flash improved on SWE-bench Verified from 48.9% to 54% in a
September 2025 update, confirming that agentic tool use was a known weakness
that Google was actively patching.

### Our Specific Failure Mode

Our experience -- Flash ignoring detailed system prompt instructions to perform
multi-step search -- is consistent with these reports. The model:

1. Has documented problems with following complex behavioral instructions
2. Tends toward minimal tool use (single call and stop) rather than iterative
   multi-step sequences
3. Has known issues with multi-turn tool calling reliability
4. Is explicitly positioned by Google as weaker than Pro for agentic tasks

This is primarily a model capability issue, not a prompt issue. No amount of
prompt engineering will reliably produce multi-step search behavior from a model
that struggles with basic tool call reliability.

---

## 3. Free/Cheap Models That Work for Agents

### Free API Tiers

**Gemini (Google AI Studio)**:
- Free tier: 5-15 RPM depending on model, 100-1,000 requests/day
- December 2025 quota reduction of 50-80% made it prototyping-only
- Flash is cheap but unreliable for agents; Pro is better but heavily rate-limited

**Groq**:
- Free tier with no credit card required
- Llama 3.3 70B: ~6,000 tokens/min, 500K tokens/day
- Llama 3.1 8B: ~30,000 tokens/min
- Extremely fast inference but tight daily limits

### Open-Source Models for Agentic Use

The community has converged on several models for agentic workloads:

**Tier 1 -- Production-grade agentic capability:**
- **Qwen3-Coder**: 69.6% on SWE-bench. Best-in-class open model for tool
  calling and agentic workflows. Alibaba explicitly designed it for agent use
  with MCP support.
- **DeepSeek V3.2**: 67.8% on SWE-bench Verified, 70.8% with high reasoning.
  Strong reasoning and tool use. Built with 1,800+ environments and 85,000+
  agent tasks in RL training.
- **Qwen3.5-397B-A17B**: MoE architecture, strong multimodal and agentic
  capabilities. Scores 78.6 on BrowseComp (beats US frontier models on web
  browsing).

**Tier 2 -- Capable with caveats:**
- **GLM-4.6** (Zhipu AI, ~355B params): Explicitly tuned for agent use.
  Plans multi-step solutions and decides when to use tools.
- **Llama 4 Maverick**: 55.8% on SWE-bench. Decent but trails Qwen and
  DeepSeek significantly.

**Tier 3 -- Small models (7-8B), limited but usable:**
- Qwen3-8B, Qwen2.5-7B with tool augmentation can compete with much larger
  models on simple tasks. A 4B model with tools (18.18% on GAIA) beat a 32B
  model without tools (12.73%).
- Reliable tool-use pass rates now exceed 70% for open 7B-32B models on
  standard benchmarks.
- However, these models struggle with multi-step planning and show unstable
  tool orchestration. The 14B-32B range shows meaningfully better stability.

### Practical Recommendation

For our use case (multi-step search requiring iterative tool calls), the minimum
viable open model is likely in the **30B+ parameter range** with explicit agentic
training. Qwen3 models are the strongest open option for tool calling. Below
30B, expect to compensate heavily with architectural scaffolding.

---

## 4. The Bitter Lesson Perspective

### The Case for "Just Wait for Better Models"

Sebastian Raschka's State of LLMs 2025 documents this trend: "Reasoning models
scaled, and the user burden of elaborate prompting shrank dramatically." His
2026 prediction: "Much of LLM benchmark and performance progress will come from
improved tooling and inference-time scaling rather than from training or the
core model itself."

The Bitter Lesson argument is real. Reasoning models like DeepSeek R1 and o3
have shown that scale + RL training naturally produces better tool use without
hand-crafted workarounds. GPT-4.5 was "bad bang for the buck" -- but the
improvements came from better training pipelines, not bigger models.

### The Case for Architecture

However, the consensus in 2025-2026 is **not** "just wait":

**Anthropic's position** (from their context engineering guide): "The quality
of an agent often depends less on the model itself and more on how its context
is structured and managed. Even a weaker LLM can perform well with the right
context, but no state-of-the-art model can compensate for a poor one."

**NeurIPS 2025 consensus**: "The era of magic is over; the era of Reliable
Systems Engineering has begun." A smaller, well-grounded model consistently
outperforms a frontier model that lacks access to the right context.

**Architecture as the primary differentiator**: Producing a complete plan before
taking action leads to higher-quality reasoning and greater task completion
rates. The Plan-then-Execute pattern systematically improves outcomes from the
underlying model.

**Multi-agent approaches**: Research shows that multi-agent collaboration with
small models can match or beat single large models. A modular agentic planner
combined with Llama3-70B displays superior transfer across tasks compared to
monolithic approaches.

### The Synthesis

Both are true, and they operate on different timescales:

- **Short-term** (now): Architecture and context engineering are the primary
  levers. Pick a model that meets a capability threshold, then invest in
  structured workflows, tool design, and context management.
- **Medium-term** (6-12 months): Better models will reduce the need for
  scaffolding. What requires a structured workflow today may work with a simple
  ReAct loop on next-generation models.
- **Long-term**: The Bitter Lesson wins. But you ship products now, not in the
  long term.

---

## 5. Model Size vs. Agentic Capability

### Research Findings

**GAIA benchmark study (Qwen3, 4B-32B)**:
- 4B with tools (18.18%) beat 32B without tools (12.73%)
- 32B with agentic setup: 25.45% (best overall)
- 8B models showed 6% accuracy improvement with explicit reasoning on multi-step
  tasks, but full thinking mode often degraded performance
- Failure modes at small scale: tool omission, search loops without termination,
  output formatting drift

**Size thresholds for different capabilities**:
- **Basic tool calling** (single step, correct schema): 7-8B models achieve 70%+
  pass rates
- **Stable tool orchestration** (consistent multi-step patterns): 14B-32B range
  shows meaningful stability improvement over 7-8B
- **Strategic planning** (choosing when/whether to use tools, iterating on
  results): 30B+ with agentic training, or frontier proprietary models
- **Reliable multi-step agentic behavior**: Currently only frontier models
  (Claude 4+, GPT-5, Gemini Pro) and the largest open models (Qwen3-Coder,
  DeepSeek V3.2) demonstrate this consistently

**Mid-sized models (8B) increase tool diversity under explicit reasoning, while
larger models (14B, 32B) maintain stable ratios.** Higher-capacity models are
better able to integrate explicit reasoning with tool execution; smaller models
struggle to translate internal reasoning into effective external actions.

### The Practical Cutoff for Our Use Case

Our task -- multi-step search with synonym generation, result evaluation, and
iterative refinement -- requires:

1. Following complex behavioral instructions from a system prompt
2. Planning a multi-step search strategy
3. Evaluating intermediate results and deciding whether to continue
4. Generating search term variants (synonyms, morphological forms)

This is squarely in the "strategic planning" tier. The practical floor is
**30B+ parameters with agentic training** for model-autonomous behavior, or a
smaller model with heavy architectural scaffolding (forced multi-step loops,
explicit planning tools).

---

## 6. What Is Actually Working in Practice

### SWE-bench: The Definitive Agent Benchmark

SWE-bench Verified (Feb 2026) top results show only frontier models and the
largest open models reliably solving multi-step coding tasks. The top open-source
result is DeepSeek V3.2 at 70.8% (with high reasoning scaffolding).

On SWE-bench Pro (harder, more realistic), **all models collapse to ~23%**. This
is the most honest measure of current multi-step agent capability, and it shows
that even the best models fail on roughly 77% of realistic tasks.

### Coding Agents in Production

Real-world coding agents (Claude Code, Cursor, Windsurf) all use frontier
proprietary models (Claude Sonnet/Opus, GPT-5) as their backbone. None have
shipped with open-source models for the primary reasoning loop. Claude Code uses
approximately a dozen tools with carefully designed, minimal-overlap interfaces.

### Multi-Step Tool Use: What the Data Shows

MCPMark results are the most relevant to our search scenario. With tasks
averaging 16+ turns and 17+ tool calls, the best model (GPT-5 Medium) achieves
only 52.6%. Models that lead on simpler benchmarks (Claude) drop to ~29%.

The disconnect between BFCL and MCPMark scores is the most important finding
in this research: **single-step tool calling ability does not predict multi-step
agentic reliability.**

### Open Models in Production

Qwen3-Coder is the most viable open model for agentic use, with 69.6% on
SWE-bench and explicit MCP support. DeepSeek V3.2 follows closely. Both require
significant compute to run (they are large MoE models, not 7B models you run
on a laptop).

For truly free/local use, the Qwen3-30B range offers the best trade-off between
capability and resource requirements, but expect to invest in architectural
scaffolding to compensate for the capability gap vs. frontier models.

---

## Recommendations for Our Harness

### Diagnosis

The Gemini 2.5 Flash failure is a **model capability issue**. Flash has
documented, systemic problems with tool calling reliability. Even if those were
fixed, Flash-class models are not designed for the kind of multi-step strategic
planning our search task requires.

### Options, Ranked by Practicality

**Option 1: Upgrade the model (simplest fix)**

Switch to a model with demonstrated multi-step tool use capability:
- Claude Sonnet 4+ or GPT-5: Best reliability, pay per token
- Gemini 2.5 Pro: Better than Flash, available on free tier (5 RPM limit)
- Qwen3-Coder: Best open model for tool calling, needs hosting

**Option 2: Add architectural scaffolding (compensate for weaker model)**

If staying with a cheaper/free model, force the multi-step behavior
architecturally rather than relying on the model to self-direct:
- **Forced iteration loop**: Instead of asking the model to "search with
  multiple terms," run a loop that explicitly calls the model multiple times:
  once to generate search terms, once per search execution, once to evaluate
  results and decide whether to continue
- **Planning tool**: Give the model a dedicated "create_search_plan" tool that
  it must call before any search, forcing it to enumerate terms upfront
- **Result evaluation step**: After each search, explicitly prompt the model
  to evaluate coverage and generate additional terms if needed

This is more work but makes the search strategy model-agnostic. A simple
model that can do one thing well per turn can be orchestrated into a multi-step
workflow.

**Option 3: Hybrid approach (recommended)**

Use a capable model AND add light architectural support:
- Switch to Gemini 2.5 Pro (free tier) or Qwen3 for better baseline capability
- Add a simple forced-iteration loop as a safety net
- Design tools to be self-contained and unambiguous (Anthropic's guidance:
  if a human can't tell which tool to use, neither can the model)

The Anthropic context engineering principle applies: "Smarter models require
less prescriptive engineering, allowing agents to operate with more autonomy."
Start with structure, relax it as model capability improves.

---

## Sources

### Benchmarks and Leaderboards
- [BFCL V4 Leaderboard](https://gorilla.cs.berkeley.edu/leaderboard.html)
- [BFCL v3 Leaderboard](https://llm-stats.com/benchmarks/bfcl-v3)
- [SWE-bench Leaderboards](https://www.swebench.com/)
- [SWE-bench Verified (Epoch AI)](https://epoch.ai/benchmarks/swe-bench-verified)
- [SWE-bench Pro (Scale AI)](https://scale.com/leaderboard/swe_bench_pro_public)
- [SWE-bench February 2026 Update (Simon Willison)](https://simonwillison.net/2026/Feb/19/swe-bench/)
- [Function Calling and Agentic AI in 2025 (Klavis AI)](https://www.klavis.ai/blog/function-calling-and-agentic-ai-in-2025-what-the-latest-benchmarks-tell-us-about-model-performance)
- [MCPMark Benchmark](https://arxiv.org/html/2509.24002v1)
- [MCP-Bench (Accenture)](https://github.com/Accenture/mcp-bench)

### Gemini Flash Issues
- [Very Frustrating Experience with Gemini 2.5 Function Calling (Google Forum)](https://discuss.ai.google.dev/t/very-frustrating-experience-with-gemini-2-5-function-calling-performance/92814)
- [Gemini 2.5 Flash Refusing Tool Calls (Google Forum)](https://discuss.ai.google.dev/t/gemini-2-5-flash-05-20-refusing-to-use-certain-tool-calls/84086)
- [Gemini 2.5 Flash Multi-Turn Function Calling Bug (LiteLLM)](https://github.com/BerriAI/litellm/issues/17949)
- [Improved Gemini 2.5 Flash Release (Google Blog)](https://developers.googleblog.com/en/continuing-to-bring-you-our-latest-models-with-an-improved-gemini-2-5-flash-and-flash-lite-release/)
- [Gemini 2.5 Pro vs Flash Comparison](https://muneebdev.com/gemini-2-5-pro-vs-flash/)

### Model Capability and Architecture
- [Effective Context Engineering for AI Agents (Anthropic)](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [State of LLMs 2025 (Sebastian Raschka)](https://magazine.sebastianraschka.com/p/state-of-llms-2025)
- [Can Small Agent Collaboration Beat a Single Big LLM?](https://arxiv.org/html/2601.11327v1)
- [Agent Design Patterns (LlamaIndex)](https://www.llamaindex.ai/blog/bending-without-breaking-optimal-design-patterns-for-effective-agents)
- [Agent Design Patterns (Lance Martin)](https://rlancemartin.github.io/2026/01/09/agent_design/)

### Open-Source Models
- [Best Open-Source LLM for Agent Workflow 2026 (SiliconFlow)](https://www.siliconflow.com/articles/en/best-open-source-LLM-for-Agent-Workflow)
- [DeepSeek V3 Function Calling Evaluation](https://github.com/deepseek-ai/DeepSeek-V3/issues/1108)
- [Qwen3 Blog](https://qwenlm.github.io/blog/qwen3/)
- [Top Open-Source LLMs 2026 (BentoML)](https://www.bentoml.com/blog/navigating-the-world-of-open-source-large-language-models)

### Free API Tiers
- [Gemini API Rate Limits](https://ai.google.dev/gemini-api/docs/rate-limits)
- [Gemini API Pricing](https://ai.google.dev/gemini-api/docs/pricing)
- [Groq Rate Limits](https://console.groq.com/docs/rate-limits)
