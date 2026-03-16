# Token Caching: Where Tool Instructions Live Matters

**Date:** 2026-03-14
**Context:** We send model, messages (with system prompt), tools (array of tool
definitions), and completion_kwargs via litellm. We are evaluating whether to move
tool-specific instructions from the system prompt into tool descriptions, and how
this interacts with prompt caching across providers.

---

## 1. How Providers Build the Cache Prefix

Every provider that supports prompt caching constructs a cache key from a
serialized prefix of the request. The critical question is: what goes into that
prefix, and in what order?

### Anthropic

Anthropic documents the most explicit caching model of any provider.

**Processing order:** `tools` -> `system` -> `messages`

This is a hierarchy. The tools array is serialized first, the system prompt
second, and messages third. Cache prefixes are built in this order, so a cache
breakpoint on the system prompt implicitly includes all tools above it.

**Cache invalidation cascades downward.** If you change a tool definition (name,
description, or parameters), it invalidates the tools cache *and* the system and
messages caches below it. If you change the system prompt, it invalidates the
system and messages caches but the tools cache survives. If you only add new
messages, the tools and system caches survive.

| What changes             | Tools cache | System cache | Messages cache |
|--------------------------|:-----------:|:------------:|:--------------:|
| Tool definitions         | invalidated | invalidated  | invalidated    |
| tool_choice parameter    | survives    | survives     | invalidated    |
| System prompt            | survives    | invalidated  | invalidated    |
| New messages appended    | survives    | survives     | partial hit    |

**Cache control placement:** You place `cache_control: {"type": "ephemeral"}`
on the *last* tool definition to cache all tools as a single prefix. You can
place a second cache breakpoint on the system prompt. Maximum 4 breakpoints
per request.

**Minimum cacheable prefix:** 1,024 tokens for Sonnet/Opus models, 2,048 for
Haiku models.

**Pricing:** Cache writes cost 1.25x base input price (5-minute TTL) or 2x
(1-hour TTL). Cache reads cost 0.1x base input price -- a 90% discount.

Source: [Anthropic Prompt Caching docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)

### OpenAI

OpenAI's caching is automatic and less configurable.

**Processing order:** `tools` -> `developer/system message` -> `messages`

OpenAI's documentation confirms: "Tools, schemas, and their ordering contribute
to the cached prefix -- they get injected before developer instructions." This
matches Anthropic's ordering.

**Exact prefix matching required.** Cache hits require byte-for-byte identical
prefixes. Changing tool definitions, changing tool ordering, changing the system
prompt -- any of these break the cache. There is no explicit cache breakpoint
mechanism (no `cache_control`).

**`allowed_tools` preserves the cache.** OpenAI's recommended pattern: list all
tools in the `tools` array (keeping it stable), then use the `allowed_tools`
parameter on `tool_choice` to control which tools are available per request
without breaking the cache prefix.

**Minimum cacheable prefix:** 1,024 tokens. Cache hits occur in 128-token
increments.

**Pricing:** Cache writes are free. Cache reads cost 0.25x-0.50x of base input
price (model-dependent). This is a significantly different economic model from
Anthropic -- no write penalty, but smaller read discount.

Sources:
- [OpenAI Prompt Caching docs](https://developers.openai.com/api/docs/guides/prompt-caching/)
- [OpenAI Prompt Caching 201](https://developers.openai.com/cookbook/examples/prompt_caching_201/)

### DeepSeek

DeepSeek's caching is automatic and prefix-based, similar to OpenAI.

**Processing order:** Not explicitly documented for tool definitions. The
documentation describes caching in terms of message prefixes only. The examples
show system messages and user content but never mention tools.

**How it works:** The system caches prefixes on a distributed disk array. If a
subsequent request shares an identical prefix with a previous request (starting
from the 0th token), the overlapping portion is a cache hit. The cache uses
64-token storage units; content shorter than 64 tokens is not cached.

**Tool definitions: undocumented.** DeepSeek's caching documentation does not
mention tool definitions at all. Since DeepSeek uses an OpenAI-compatible API
format, tools are almost certainly serialized into the prefix before messages
(matching OpenAI's behavior), but this is inference, not documented fact.

**Pricing:** Cache hits cost $0.014/M tokens (roughly 90% cheaper than base
input). Cache writes are billed at the standard input rate (no premium).

Source: [DeepSeek Context Caching docs](https://api-docs.deepseek.com/guides/kv_cache)

### Qwen (Alibaba Cloud / DashScope)

Qwen models support context caching through Alibaba Cloud's Model Studio API.

**Cache control:** Uses a `cache_control` marker similar to Anthropic's
approach. You place a `cache_control` marker to create a cache block containing
content from the beginning of the messages array.

**Minimum cacheable prefix:** 1,024 tokens.

**Tool definitions:** Not explicitly documented in the caching context. The
Qwen3-Coder documentation describes tool support and context caching as
separate features without discussing their interaction.

Source: [Alibaba Cloud Model Studio - Context Cache](https://www.alibabacloud.com/help/en/model-studio/context-cache)

### OpenRouter (Our Provider)

OpenRouter is a routing layer, not a model provider. Its caching behavior
depends on which downstream provider serves the request.

**Sticky routing:** OpenRouter hashes the first system message and first
non-system message to create a conversation fingerprint. Subsequent requests
with the same fingerprint are routed to the same downstream provider, keeping
that provider's cache warm. This is automatic.

**Pass-through caching:** For providers with explicit caching (Anthropic),
OpenRouter passes `cache_control` parameters through. For providers with
automatic caching (OpenAI, DeepSeek, Gemini), no configuration is needed.

**Critical limitation for us:** When using litellm through OpenRouter, there
is a known issue where litellm may inject `cache_control` parameters that
OpenRouter does not support for certain providers, causing 404 errors. The
workaround is to avoid `cache_control` annotations when targeting non-Anthropic
models through OpenRouter.

**DeepSeek via OpenRouter:** Caching is automatic. No configuration needed.
OpenRouter's sticky routing ensures requests hit the same DeepSeek endpoint.

**Qwen via OpenRouter:** OpenRouter lists Qwen3-Coder with automatic caching
(90% savings claimed on the model page), but the documentation does not
specifically address how Qwen caching works through OpenRouter.

Sources:
- [OpenRouter Prompt Caching docs](https://openrouter.ai/docs/guides/best-practices/prompt-caching)
- [OpenRouter Tool Caching announcement](https://openrouter.ai/announcements/gif-prompts-omni-search-tool-caching-and-byok-flags)

---

## 2. The Core Question: System Prompt vs. Tool Descriptions

### What We Send Today

Our current request structure (simplified):

```
tools: [
  { name: "run_python",    description: "Execute Python code..." (short) },
  { name: "list_files",    description: "List files in workspace..." (medium) },
  { name: "search_files",  description: "Search file contents..." (medium) },
  { name: "read_file",     description: "Read a file..." (medium) },
  { name: "calculator",    description: "Evaluate a math expression..." (short) },
  { name: "get_current_time", description: "Returns the current UTC time." (short) },
]
system: [
  role + capabilities description,
  workspace context (dynamic: path, file listing),
  tool workflow guidance ("search before reading"),
]
messages: [ ... conversation ... ]
```

The system prompt contains ~200-400 tokens. Tool definitions contain ~500
tokens. Together the static prefix is ~700-900 tokens.

### Scenario A: Move Instructions from System Prompt into Tool Descriptions

Example: Move "search before reading" guidance from the system prompt into the
`search_files` and `read_file` tool descriptions.

**Effect on caching:**

For Anthropic: Tools are cached first. Making tool descriptions longer does not
hurt caching -- it moves tokens from the system level to the tools level, but
both are part of the same cached prefix. The total cached prefix size is
unchanged. No impact.

For OpenAI/DeepSeek: Tools are serialized first in the prefix. Same logic
applies -- moving tokens between tools and system prompt does not change the
total prefix or its stability. No impact.

**Effect on cache invalidation:**

This is where it matters. If tool descriptions contain instructions that you
might want to iterate on (and you will), every edit to a tool description
invalidates the *entire* cache hierarchy on Anthropic (tools + system +
messages). If those same instructions lived in the system prompt, editing them
would only invalidate the system and message caches -- the tools cache would
survive.

**Verdict:** Moving volatile instructions into tool descriptions *hurts* caching
on Anthropic because tool changes cascade more destructively than system prompt
changes. For OpenAI/DeepSeek (prefix-matching), there is no difference -- any
change to either tools or system prompt breaks the prefix match equally.

### Scenario B: Move Instructions from Tool Descriptions into System Prompt

The reverse: make tool descriptions minimal (just the API contract) and put all
usage guidance in the system prompt.

**Effect on caching (Anthropic):**

This is strictly better for cache invalidation. Tool definitions become stable
(they change only when the tool API changes). The system prompt absorbs the
volatile instructions. When you iterate on instructions, only the system and
message caches invalidate. The tools cache survives.

**Effect on model behavior:**

This is the tradeoff. Our existing research (system-prompt-for-tool-agents.md)
found that models need guidance in *both* places: the system prompt for
workflow-level guidance ("when" and "why"), and tool descriptions for
tool-specific guidance ("what" and "how"). Stripping tool descriptions to bare
API contracts may reduce tool-use quality, especially with weaker models.

**Verdict:** Better for caching on Anthropic, potentially worse for model
behavior. For OpenAI/DeepSeek prefix-matching, no caching difference.

### Scenario C: Status Quo (Instructions in Both Places)

Keep workflow guidance in the system prompt, keep tool-specific hints in tool
descriptions.

**Effect on caching:** Both tools and system prompt are stable between requests
in a conversation (they do not change turn-to-turn). Both get cached. The
question of "where instructions live" only matters for cache invalidation during
*development* (when you are iterating on prompts), not during *production use*
(when prompts are fixed).

**Verdict:** This is the right answer for production. During development, any
prompt change invalidates caches regardless of where the change is.

---

## 3. Code-as-Tool-Use and Caching

In the code-as-tool-use pattern (e.g., Cloudflare Code Mode, smolagents), the
model gets a single `run_code` tool instead of N individual tools. The tool
definitions shrink dramatically, and the system prompt describes available
functions as documentation.

### How This Changes the Caching Picture

**Tool definitions shrink:** From ~500 tokens (6 tools) to ~100 tokens (1 tool:
`run_code`). This makes the tools portion of the cache trivially small.

**System prompt grows:** The system prompt must now describe the available
functions (their signatures, behavior, when to use each). This could add
300-1,000 tokens to the system prompt depending on how many functions exist
and how detailed the documentation is.

**Net effect on cacheable prefix size:** Roughly the same total tokens, just
redistributed from tools to system prompt.

**Effect on caching stability:**

On Anthropic, this is a clear win for cache management. The tools array (now
just `run_code`) is extremely stable -- it basically never changes. All the
volatile content (function documentation, usage guidance) lives in the system
prompt. When you iterate on function docs, only the system and message caches
invalidate; the tools cache survives.

On OpenAI/DeepSeek, the prefix-matching is unchanged. Any change to any part
of the prefix breaks the cache.

**Effect on token consumption per turn:**

This is separate from caching but important. Code-as-tool-use reduces total
tokens because intermediate tool results stay inside the sandbox and never
enter the context window. Our code-as-tool-orchestration.md research showed
37-99% token reductions depending on the pattern. These savings compound with
caching -- fewer input tokens means smaller cached prefixes and cheaper cache
reads.

### The Tradeoff

Code-as-tool-use does not primarily help with *caching*. It helps with *total
token consumption*. The caching benefits are minor (slightly more stable tools
array on Anthropic). The token consumption benefits are major (intermediate
results stay out of context).

---

## 4. What Actually Matters for Our Harness

### Our Situation

- **Provider:** OpenRouter -> DeepSeek V3.2 or Qwen3-Coder
- **Caching type:** Automatic prefix caching (no `cache_control` needed)
- **Static prefix size:** ~700-900 tokens (tools + system prompt)
- **Minimum cache threshold:** 1,024 tokens (both DeepSeek and Qwen)

### Problem: Our Static Prefix May Be Below the Cache Threshold

At ~700-900 tokens, our combined tools + system prompt may fall below the
1,024-token minimum required for caching. This means the static prefix might
not be cached at all.

**Implications:**

1. Moving instructions between tools and system prompt is irrelevant if the
   total prefix is below the cache threshold.
2. Adding more content to the system prompt (longer workspace description, more
   guidance) could *help* by pushing the prefix above 1,024 tokens.
3. For DeepSeek specifically, the 64-token storage granularity means even
   partial matches provide some benefit, but only for content above the
   threshold.

### What Would Actually Help Caching

1. **Ensure the static prefix exceeds 1,024 tokens.** If the system prompt +
   tools are under this threshold, caching provides zero benefit regardless
   of where instructions live. With conversation growth (messages accumulating),
   the total input will exceed 1,024 tokens quickly, and the prefix (tools +
   system) will be the cacheable portion. So this may not be a real concern
   in practice -- it only affects the first 1-2 turns.

2. **Keep tool definitions stable across requests.** Do not dynamically add or
   remove tools between turns in a conversation. Our harness already does this
   correctly -- `TOOL_DEFINITIONS` is a static list.

3. **Keep tool ordering stable.** OpenAI and DeepSeek require byte-identical
   prefixes. Even reordering tools breaks the cache. Our harness already does
   this correctly -- the list is defined in source code with a fixed order.

4. **Do not inject dynamic content into the tools array.** Timestamps, session
   IDs, or per-request variations in tool descriptions would break caching.
   Our harness does not do this.

5. **Verify caching is actually working.** The MEMORY.md notes that
   `cache_hit=None` in our telemetry. This needs investigation -- it may mean
   OpenRouter is not reporting cache metrics, or that caching is not happening.

### What Would NOT Help Caching

1. **Moving instructions between tools and system prompt.** For automatic
   prefix caching (DeepSeek, Qwen via OpenRouter), this is a no-op. Both
   tools and system prompt are part of the same prefix. Moving tokens between
   them does not change the prefix hash.

2. **Switching to code-as-tool-use for caching reasons.** The caching benefits
   are minimal. Code-as-tool-use helps with *total token consumption* (keeping
   intermediate results out of context), not with *cache hit rates*.

3. **Adding `cache_control` annotations.** Our providers (DeepSeek, Qwen via
   OpenRouter) use automatic caching. Adding `cache_control` annotations would
   either be ignored or cause errors.

---

## 5. Provider Comparison Summary

| Aspect                    | Anthropic              | OpenAI                 | DeepSeek               | Qwen (via OpenRouter)  |
|---------------------------|------------------------|------------------------|------------------------|------------------------|
| Caching type              | Explicit (breakpoints) | Automatic (prefix)     | Automatic (prefix)     | Automatic (prefix)     |
| Tools in cache prefix?    | Yes (first)            | Yes (first)            | Undocumented (likely)  | Undocumented           |
| Processing order          | tools->system->msgs    | tools->system->msgs    | Not documented         | Not documented         |
| Min cacheable tokens      | 1,024 (Sonnet/Opus)    | 1,024                  | 64 (storage unit)      | 1,024                  |
| Cache write cost          | 1.25x base             | Free                   | 1x base (standard)     | Unknown via OpenRouter |
| Cache read discount       | 90% (0.1x)             | 50-75% (0.25-0.5x)    | ~90%                   | ~90% (claimed)         |
| Tool change invalidation  | Cascades to all levels | Breaks prefix match    | Breaks prefix match    | Breaks prefix match    |
| System change invalidation| Tools cache survives   | Breaks prefix match    | Breaks prefix match    | Breaks prefix match    |
| Max cache breakpoints     | 4                      | N/A (automatic)        | N/A (automatic)        | N/A (automatic)        |

---

## 6. Practical Recommendations

### For Our Current Setup (DeepSeek/Qwen via OpenRouter)

1. **Do not reorganize tool instructions for caching reasons.** With automatic
   prefix caching, where instructions live within the prefix does not affect
   cache hit rates. Keep instructions where they serve the model best: workflow
   guidance in the system prompt, tool-specific hints in tool descriptions.

2. **Investigate the `cache_hit=None` telemetry.** This is the most important
   action item. We cannot optimize what we cannot measure. Check if OpenRouter
   reports cache metrics in the response `usage` object, or if litellm is
   stripping them.

3. **Keep the tools array stable and ordered.** Already done, but worth
   protecting as a design principle.

4. **If we switch to Anthropic models,** the picture changes. Anthropic's
   hierarchical caching means the *placement* of instructions matters: volatile
   content should live in the system prompt (not tool descriptions) to preserve
   the tools cache across prompt iterations.

### For a Future Anthropic Migration

If we ever use Claude models directly (not via OpenRouter):

1. Add `cache_control: {"type": "ephemeral"}` to the last tool definition.
2. Add a second `cache_control` breakpoint on the system prompt.
3. Keep tool descriptions stable (API contracts only, no volatile guidance).
4. Put all iterable guidance in the system prompt.
5. Use `allowed_tools` / `tool_choice` rather than modifying the tools array
   to control tool availability.

### For Code-as-Tool-Use

The caching argument is not relevant to the code-as-tool-use decision. The real
benefits of code-as-tool-use are:
- Token savings from keeping intermediate results out of context (37-99%)
- Fewer inference round-trips (latency improvement)
- Better model performance on multi-step tasks

The caching side effect (more stable tools array) is a minor bonus, not a
decision driver.

---

## 7. Open Questions

1. **Is caching actually working for us?** The `cache_hit=None` in telemetry
   is the most pressing question. Until we confirm caching is active, all of
   this analysis is theoretical for our deployment.

2. **How does DeepSeek serialize tool definitions?** DeepSeek's caching docs
   only discuss message prefixes. Whether tools are serialized before messages
   (like OpenAI) or handled differently is not documented. Given the
   OpenAI-compatible API, the OpenAI behavior is the most likely, but this is
   unconfirmed.

3. **What is Qwen3-Coder's caching behavior via OpenRouter?** OpenRouter
   claims 90% savings for Qwen3-Coder, but the mechanism (prefix caching?
   provider-side KV cache?) is not documented. We do not know if tools are
   part of the cached prefix.

4. **Does litellm interfere with caching?** The known issue where litellm
   injects `cache_control` for non-Anthropic providers via OpenRouter could
   cause silent failures. Worth checking whether our litellm version has this
   bug and whether it affects our cache hit rates.

---

## Sources

### Provider Documentation
- [Anthropic Prompt Caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- [OpenAI Prompt Caching](https://developers.openai.com/api/docs/guides/prompt-caching/)
- [OpenAI Prompt Caching 201 (Cookbook)](https://developers.openai.com/cookbook/examples/prompt_caching_201/)
- [DeepSeek Context Caching](https://api-docs.deepseek.com/guides/kv_cache)
- [Alibaba Cloud Model Studio - Context Cache](https://www.alibabacloud.com/help/en/model-studio/context-cache)
- [OpenRouter Prompt Caching](https://openrouter.ai/docs/guides/best-practices/prompt-caching)

### OpenRouter Announcements
- [OpenRouter Tool Caching](https://openrouter.ai/announcements/gif-prompts-omni-search-tool-caching-and-byok-flags)

### LiteLLM
- [LiteLLM Prompt Caching](https://docs.litellm.ai/docs/completion/prompt_caching)
- [LiteLLM cache_control filtering issue #12787](https://github.com/BerriAI/litellm/issues/12787)

### Background
- [OpenAI Community: Prompt caching with tools](https://community.openai.com/t/prompt-caching-with-tools/1357440)
- [Prompt Caching Guide 2025](https://promptbuilder.cc/blog/prompt-caching-token-economics-2025)
- [How prompt caching works (Paged Attention)](https://sankalp.bearblog.dev/how-prompt-caching-works/)
