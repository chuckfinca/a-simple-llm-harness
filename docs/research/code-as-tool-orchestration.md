# Code Execution as Tool Orchestration: Research Findings

**Date:** 2026-03-06
**Context:** Evaluating the pattern where an LLM writes code that calls tools
programmatically inside a sandbox, instead of making individual tool calls
through the agent loop. Assessing architecture patterns, implementation
approaches, security implications, and practical applicability to our harness.

---

## 1. The Pattern Explained

In the traditional agent loop, each tool call requires a full round-trip:
the LLM generates a tool_use request, the harness executes it, the result
goes back into the context window, and the LLM generates the next request.
For N sequential tool calls, this means N inference passes, with every
intermediate result accumulating in the context.

The code-as-orchestration pattern inverts this. The LLM writes a program
that calls tools as functions within an execution environment. The program
runs to completion (or until it needs a result from the host), and only the
final output enters the context window. Intermediate data stays inside the
execution environment.

**Why it matters quantitatively:** Research on real agent trajectories shows
the average trajectory to solve a single GitHub issue contains 48.4K tokens
across 40 steps, of which 30.4K tokens (63%) are tool result messages that
accumulate in context. Daily Claude Sonnet usage on OpenRouter reaches 100B
tokens, with 99% being accumulated input tokens and only 1% being
LLM-generated output. Code-as-orchestration attacks this 99% directly.

Sources:
- [Trajectory Reduction for LLM Agent Systems](https://arxiv.org/pdf/2509.23586)
- [Anthropic: Advanced Tool Use](https://www.anthropic.com/engineering/advanced-tool-use)

---

## 2. Who Implements This Pattern

### 2.1 Anthropic Programmatic Tool Calling (Production API)

This is the most mature implementation. Anthropic has shipped this as a
first-party API feature, now generally available (not beta) as of early 2026.

**How it works:**

1. You include a `code_execution_20260120` tool alongside your regular tools.
2. Regular tools declare `"allowed_callers": ["code_execution_20260120"]` to
   indicate they can be called from within code execution.
3. Claude writes Python code that calls your tools as async functions
   (`result = await query_database("SELECT ...")`).
4. The code runs in Anthropic's sandboxed container. When a tool function is
   called, execution *pauses* and the API returns a `tool_use` block to you.
5. You execute the tool on your side, return the result, and code execution
   resumes inside the container.
6. Only the final stdout/print output enters Claude's context window.

**The hybrid mechanism is built in.** Each tool can declare:
- `["direct"]` -- only callable as traditional tool calls (default)
- `["code_execution_20260120"]` -- only callable from within code
- `["direct", "code_execution_20260120"]` -- callable both ways

Anthropic recommends choosing one or the other per tool, not both, because
it gives Claude clearer guidance on how to use each tool.

**Measured results:**
- Token consumption reduced from 43,588 to 27,297 tokens (37%) on complex
  research tasks
- On agentic search benchmarks (BrowseComp, DeepSearchQA), programmatic
  tool calling was "the key factor that fully unlocked agent performance"
- Knowledge retrieval improved from 25.6% to 28.5%; benchmark performance
  from 46.5% to 51.2%

**Critical detail for our harness:** LiteLLM supports this. It automatically
detects tools with the `allowed_callers` field and adds the required beta
header. This means our harness could use programmatic tool calling without
leaving litellm's abstraction layer.

Sources:
- [Anthropic: Programmatic Tool Calling docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/programmatic-tool-calling)
- [LiteLLM: Anthropic Programmatic Tool Calling](https://docs.litellm.ai/docs/providers/anthropic_programmatic_tool_calling)
- [Anthropic: Advanced Tool Use](https://www.anthropic.com/engineering/advanced-tool-use)

### 2.2 Cloudflare Code Mode

Cloudflare built a production implementation for their massive API (1,600+
endpoints). The architecture:

1. MCP tool schemas are converted to TypeScript type definitions.
2. The LLM gets a single "write code" tool instead of 1,600 individual tools.
3. Generated JavaScript runs in a V8 isolate (Cloudflare Worker) with no
   filesystem, no environment variables, and external fetch disabled by default.
4. Inside the sandbox, code calls tools via `codemode.toolName(args)`,
   which are bridged back to the actual MCP servers through the host process.

**Token savings:** From 1.17 million tokens (all tool definitions) to ~1,000
tokens -- a 99.9% reduction. For 63 tools specifically: from 36.6K tokens
to 4.4K tokens (88% reduction).

**Security model:** The V8 isolate is genuinely locked down. `globalOutbound:
null` blocks all network access at the runtime level. Code can only interact
with the host through the codemode tool call bridge.

Source:
- [Cloudflare Blog: Code Mode](https://blog.cloudflare.com/code-mode-mcp/)
- [Cloudflare Agents docs: Codemode](https://developers.cloudflare.com/agents/api-reference/codemode/)

### 2.3 smolagents CodeAgent (HuggingFace)

smolagents is the clearest open-source implementation of code-as-orchestration,
and it is the *default* agent type in the library.

**How tools are exposed:** Tools decorated with `@tool` become Python
functions that the LLM can call directly in generated code:

```python
@tool
def get_travel_duration(start: str, dest: str) -> str:
    """Gets travel time between two places."""
    ...

agent = CodeAgent(tools=[get_travel_duration], model=model)
```

The LLM generates code like:
```python
result1 = get_travel_duration("Eiffel Tower", "Notre-Dame")
result2 = get_travel_duration("Notre-Dame", "Montmartre")
total = parse_duration(result1) + parse_duration(result2)
print(f"Total travel time: {total} minutes")
```

**Key insight:** Tools are injected as callable names in the execution
scope. No import mechanism, no filesystem discovery. The tools are simply
*there* when the code runs, like built-in functions. This is the simplest
possible exposure mechanism.

**Benchmark evidence:** The paper "Executable Code Actions Elicit Better
LLM Agents" (2024) shows code agents use 30% fewer steps than JSON
tool-calling agents and achieve up to 20 percentage points higher success
rates on complex tasks.

**Security:** Five sandbox backends (LocalPythonExecutor, E2B, Modal,
Docker, WASM). The local executor has been broken (CVE-2025-5120).
Production use requires one of the container/cloud backends.

Sources:
- [smolagents blog](https://huggingface.co/blog/smolagents)
- [HuggingFace Agents Course: Code Agents](https://huggingface.co/learn/agents-course/unit2/smolagents/code_agents)
- [Executable Code Actions Elicit Better LLM Agents](https://huggingface.co/papers/2402.01030)

### 2.4 The olaservo/code-execution-with-mcp Reference Implementation

This is the reference implementation of Anthropic's original engineering
blog post. It takes a different approach from Anthropic's API-level solution.

**Architecture:** Generates RPC wrapper files (TypeScript) for each MCP
tool. These wrappers are placed on the filesystem in a `servers/` directory
structure. The agent discovers them via the Claude Agent SDK's Skills system,
reads the wrapper files, and writes TypeScript code that imports and calls
them.

**Key difference from smolagents:** Discovery is explicit (filesystem
exploration) rather than implicit (tools injected into scope). This adds
complexity but enables lazy loading -- the agent only reads tool definitions
it actually needs.

Source:
- [olaservo/code-execution-with-mcp on GitHub](https://github.com/olaservo/code-execution-with-mcp)

### 2.5 Meta-MCP "Code Mode" Pattern

A community pattern that wraps N child MCP servers behind a meta-server
exposing exactly two tools:

- `search_docs` -- search API definitions of child MCP servers
- `execute_code` -- run TypeScript that calls MCP bindings

Execution happens in a Deno worker sandbox with 30-second timeout, no
network, no filesystem access. Child server calls relay through the parent.

**Token savings:** 63 tools compressed from 36.6K to 4.4K tokens (88%).

Source:
- [Meta-MCP Architecture for Claude Code](https://dev.to/tgfjt/a-practical-meta-mcp-architecture-for-claude-code-compressing-60-tools-into-just-two-oje)

### 2.6 LLM-in-Sandbox (Microsoft Research)

A research project demonstrating that LLMs placed in a code sandbox
spontaneously generalize to non-code tasks without additional training. The
LLM explores a virtual computer -- reading files, executing scripts,
accessing external resources -- to solve problems across math, physics,
chemistry, biomedicine, and long-context understanding.

**Key contribution:** Context is placed as text files inside the sandbox
rather than in the prompt. Models explore, read files, and interact with
the sandbox to solve tasks.

Open-sourced as a Python package: `pip install llm-in-sandbox`.

Source:
- [LLM-in-Sandbox paper](https://huggingface.co/papers/2601.16206)

### 2.7 OpenAI Codex

Codex operates entirely within isolated cloud containers. The agent has
full filesystem access within the container but no network access during
task execution (this was later relaxed). Tools like web search and MCP
are available.

Context window management is explicitly called out as "one of the agent's
many responsibilities," and agents can make hundreds of tool calls in a
single turn.

Source:
- [OpenAI: Introducing Codex](https://openai.com/index/introducing-codex/)

---

## 3. Architecture Patterns for Exposing Tools Inside the Sandbox

Based on all implementations surveyed, there are four distinct approaches:

### Pattern A: Tools as Injected Callable Functions (smolagents)

Tools are registered with the agent and automatically available as named
functions in the execution scope. No imports, no discovery.

**Pros:** Simplest possible mechanism. Zero overhead for the LLM.
**Cons:** All tools must be loaded upfront. No lazy loading. Scales
poorly past ~20 tools because tool definitions still consume prompt tokens.
**Best for:** Small tool sets (under 20 tools).

### Pattern B: Tools as Importable Modules on a Filesystem (Anthropic blog)

Tools are written as source files in a directory structure. The LLM
explores the filesystem (`ls servers/`, `cat servers/salesforce/updateRecord.ts`)
to discover and understand tools, then writes code that imports them.

**Pros:** Lazy loading -- only reads definitions it needs. Scales to
hundreds of tools. Feels natural for LLMs trained on codebases.
**Cons:** Requires filesystem exploration round-trips. More complex
setup (generating wrapper files). The LLM might misunderstand tool
interfaces if it skips reading the definition.
**Best for:** Large tool sets (50+ tools) where upfront loading is
prohibitively expensive.

### Pattern C: Tools as Async Functions with Host Bridging (Anthropic API)

Tools appear as `await`-able functions inside a server-side container.
When called, execution pauses and the API returns the tool call to the
client for fulfillment. The client provides the result and execution resumes.

**Pros:** Tools run on the client side (your infrastructure), not in the
sandbox. This means tools can access databases, APIs, and secrets without
exposing them to the sandbox. The sandbox only sees the tool's result.
**Cons:** Requires server-side container infrastructure (Anthropic provides
this). Each tool call still requires a round-trip to the client, though
the LLM is not in the loop for intermediate results.
**Best for:** Production systems where tools access sensitive resources.

### Pattern D: Tools as HTTP/RPC Endpoints (REST API pattern)

The sandbox makes HTTP calls to a tool server running alongside it. The
tool server exposes a REST API that mirrors the tool definitions.

**Pros:** Clean separation of concerns. Tools can be implemented in any
language. Easy to add authentication/authorization.
**Cons:** Requires the sandbox to have network access to the tool server,
which conflicts with `--network=none`. Requires running an additional
service. Adds latency from HTTP overhead.
**Best for:** Complex enterprise deployments with existing API infrastructure.

### What This Means for Our Harness

With 3 tools, **Pattern A is the clear winner.** The complexity of
filesystem-based discovery (Pattern B) or host bridging (Pattern C) is
not justified. Our tools should be injected as importable Python functions
that the LLM can call directly in generated code.

---

## 4. Implementation Approaches: Getting Tools Into Docker

### Option 1: Bind-Mount a Tools Library (Recommended for us)

Create a Python module (e.g., `sandbox_tools/`) containing tool wrappers.
Bind-mount it into the container at runtime:

```
docker run ... -v ./sandbox_tools:/home/sandbox/tools:ro ...
```

The LLM writes code that imports from `tools`:
```python
from tools import calculator, get_current_time
result = calculator("sqrt(144)")
current = get_current_time()
```

**Pros:** Tools are always in sync with the host. No image rebuilds. Simple.
**Cons:** Must be careful about what the tools module can *do* inside the
container (network restrictions still apply).

### Option 2: Bake Into the Docker Image

Include the tools module in the Dockerfile:
```dockerfile
COPY sandbox_tools/ /home/sandbox/tools/
```

**Pros:** Self-contained image. No bind-mount needed.
**Cons:** Requires image rebuild when tools change. Stale tools if image
is not rebuilt.

### Option 3: Inject Code at Runtime

Prepend the tool definitions to the LLM-generated code before execution.
The tool functions are literally concatenated at the top of the script.

**Pros:** No filesystem or image changes needed. Works with existing
sandbox.py unchanged.
**Cons:** Increases the size of every script. Messy. Hard to maintain.

### Recommendation

**Bind-mount** is the right approach for our harness. It requires a one-line
change to the `docker run` command in `sandbox.py`, and the tools stay in
sync automatically. It works with our existing `--read-only` flag because
the mount is `:ro`.

---

## 5. The Hybrid Approach: Should We Keep Both Patterns?

### What the Evidence Says

Every major implementation that has shipped to production supports both
patterns simultaneously:

- **Anthropic API:** `allowed_callers` can be `["direct"]`,
  `["code_execution_20260120"]`, or both. You configure per tool.
- **smolagents:** Offers both `CodeAgent` (code-as-orchestration) and
  `ToolCallingAgent` (traditional JSON tool calls) as separate agent types.
  Does not mix them within a single agent.
- **Cloudflare:** Code Mode is an alternative to traditional MCP tool
  calling, not a replacement. Traditional tool calling still exists.

### When Each Pattern Wins

**Direct tool calls are better when:**
- The task requires a single tool call with a simple response
- Observability is critical (each tool call is individually logged/traced)
- The LLM needs to reason about the tool result before deciding next steps
- Security policy requires per-call approval (HITL)

**Code-as-orchestration is better when:**
- Multiple tool calls need to be chained (loops, conditionals)
- Intermediate results are large but only a summary matters
- The task involves data processing (filter 10K rows to 5)
- Latency matters (eliminates N-1 inference round-trips)
- Token cost matters (intermediate data stays out of context)

### Recommendation for Our Harness

**Start with the status quo (direct tool calls) and add code-as-orchestration
as a *second mode*, not a replacement.** The LLM does not choose between
them -- we configure per tool which mode is appropriate.

For our current 3 tools:
- `calculator` -- direct tool call (single-step, result is small)
- `get_current_time` -- direct tool call (single-step, trivial result)
- `run_python` -- already IS code execution (this is the sandbox itself)

The interesting transition happens when we add tools that benefit from
chaining: database queries, document retrieval, API calls. At that point,
those new tools should be exposed inside the sandbox, and the LLM writes
Python that calls them as part of a `run_python` invocation.

---

## 6. Tool Discovery: Is Lazy Loading Worth It?

### The Token Math

Anthropic's data: With 7 MCP servers active, tool definitions consume
67,300 tokens (33.7% of 200K context). With many more tools: 150K tokens.

Our harness: 3 tools consume roughly 500 tokens total. This is 0.25% of
a 200K context window.

### When Lazy Loading Becomes Relevant

The literature is consistent: lazy loading matters when tool definitions
exceed ~5% of the context window. Below that, the upfront cost is negligible.

- **10 tools:** ~1,500-2,000 tokens. Not worth lazy loading.
- **30 tools:** ~5,000-8,000 tokens. Starting to matter.
- **100+ tools:** ~30,000+ tokens. Lazy loading is essential.

### The Simplest Discovery Mechanism

If/when we need discovery, the simplest approach (far simpler than
filesystem exploration) is a **tool search tool**, which is exactly what
Anthropic shipped:

1. Mark tools with `defer_loading: true` so their definitions are not sent
   to the LLM upfront.
2. Provide a tool_search tool (~500 tokens) that the LLM can call to find
   relevant tools by keyword.
3. When the LLM searches and finds a tool, its definition is loaded on
   demand.

This is simpler than filesystem-based exploration because it requires no
generated wrapper files, no directory structure, and no filesystem
operations. It is a single tool call.

### Recommendation

**Do not implement lazy loading.** With 3 tools (or even 10), the token
cost is trivial. Revisit when tool definitions exceed 5% of context. When
that happens, use Anthropic's `defer_loading` mechanism rather than
building filesystem-based discovery.

---

## 7. State and Data Flow

### How Results Should Flow Back to the LLM

All implementations surveyed use the same basic approach:

**stdout is the primary channel.** The LLM writes `print()` statements
(or `console.log()` in TypeScript) for data it wants to surface. Everything
not explicitly printed stays inside the sandbox.

This is the mechanism that produces the token savings. In traditional
tool calling, ALL intermediate results enter the context. With code
execution, only what the code explicitly outputs enters the context.

### The Anthropic API Approach (Most Sophisticated)

1. Claude writes code that calls tools as async functions.
2. Tool results go to variables inside the container.
3. Claude's code processes/filters the results.
4. Only `print()` output enters Claude's context.
5. The container persists (~4.5 min inactivity timeout), allowing
   multi-turn state.

### What Our Harness Already Does (and Could Do)

Our current `run_python` tool already captures stdout and returns it to the
LLM. The architecture is already correct for code-as-orchestration. The
missing piece is only: tools are not available inside the sandbox.

If we bind-mount a tools library, the LLM can write code like:
```python
from tools import calculator
results = [calculator(f"sqrt({x})") for x in range(100)]
print(f"Computed {len(results)} square roots, max is {max(results)}")
```

Instead of 100 separate `calculator` tool calls through the agent loop,
this is a single `run_python` call. Only the summary enters the context.

### Structured Output

Some implementations support structured output beyond stdout:

- **File artifacts:** smolagents and llm-sandbox support extracting files
  (plots, CSVs) from the container as base64-encoded artifacts.
- **JSON on stdout:** The LLM can `print(json.dumps(...))` for machine-
  parseable results.
- **Exit code:** All implementations return the exit code alongside output.

**Recommendation:** Stick with stdout + stderr + exit_code (our existing
format). It is simple and sufficient. If we later need file artifacts
(plots, generated files), add a shared volume mount for an output directory.

---

## 8. Security Implications

### How the Threat Model Changes

Our current sandbox (`sandbox.py`) is restrictive:
- `--cap-drop=ALL`
- `--network=none`
- `--read-only`
- `--memory=512m`
- `--pids-limit=100`
- `--tmpfs=/tmp:size=64m`
- Script bind-mounted read-only

**If tools are exposed inside the sandbox, the threat model depends entirely
on what those tools can do.** This is the fundamental security consideration.

### Scenario Analysis

**Safe: Pure computation tools (calculator, math, data processing)**

If tools inside the sandbox only do computation (our `calculator` and
`get_current_time`), the threat model is unchanged. These tools do not
access the filesystem, network, or any external resources.

The tool code runs *inside* the container, subject to all existing
restrictions. `--network=none` still prevents data exfiltration. `--read-only`
still prevents filesystem writes. This is the same security posture as
letting the LLM write arbitrary Python, which we already allow.

**Dangerous: Tools that access external resources**

If a tool inside the sandbox needs to call an external API, query a database,
or read files from the host, the security model changes fundamentally:

- Network access required: Must relax `--network=none`, opening the door
  to data exfiltration.
- Credentials required: API keys or database credentials must be available
  inside the container, creating a secrets management problem.
- Host access required: File-reading tools need bind-mounts to host
  directories, expanding the blast radius.

**Anthropic's solution (Pattern C) avoids this problem entirely.** Tools
are called via a bridge: the sandbox pauses, the host executes the tool,
and the result is passed back. The sandbox never has network access,
credentials, or host filesystem access. This is the right architecture
for tools that access external resources, but it requires the more
complex host-bridging infrastructure.

### The OWASP Agentic Top 10 (2026) Perspective

The OWASP Top 10 for Agentic Applications (2026) identifies several
relevant threats:

1. **Tool Call Parameter Validation:** The LLM can craft arbitrary
   arguments to tools. If tools inside the sandbox have destructive
   capabilities, adversarial inputs can trigger them.
2. **Indirect Prompt Injection:** If tool results contain adversarial
   content (e.g., a retrieved document with injection payloads), the
   LLM's generated code might propagate the attack.
3. **Privilege Escalation:** Agent A tricks Agent B into performing
   actions, bypassing sandboxing.

### Defense-in-Depth Recommendations

1. **Keep `--network=none`** for as long as possible. Only relax it when a
   tool genuinely requires network access, and then only grant access to
   specific hosts via a network proxy.
2. **Tools inside the sandbox should be pure functions** -- compute only,
   no side effects. If a tool needs external access, use host bridging.
3. **Validate tool inputs** even inside the sandbox. Don't assume the LLM
   will call tools correctly.
4. **Treat tool output as untrusted** when it comes from external sources
   (APIs, retrieved documents).
5. **Use scoped, short-lived credentials** if credentials must enter the
   sandbox. Rotate them after each execution.

Sources:
- [OWASP Top 10 for Agentic Applications 2026](https://www.practical-devsecops.com/owasp-top-10-agentic-applications/)
- [Anthropic: Claude Code Sandboxing](https://www.anthropic.com/engineering/claude-code-sandboxing)

---

## 9. Practical Recommendation for Our Harness

### Current State Assessment

Our harness has:
- 3 tools (`run_python`, `calculator`, `get_current_time`)
- A Docker sandbox with strong isolation
- An agent loop that dispatches tool calls one at a time
- ~500 tokens of tool definitions (negligible)

### Is Code-as-Orchestration Worth It at Our Scale?

**Not yet, with an important caveat.**

The token savings from code-as-orchestration are proportional to (a) the
number of chained tool calls per task and (b) the size of intermediate
results. With 3 tools, one of which (`run_python`) already IS code
execution, the savings are minimal.

**The caveat:** We already have the hardest part -- a working Docker
sandbox. The incremental cost to expose tools inside it is small (a bind-
mount and a small Python module). The question is whether the cognitive
overhead of two tool-calling patterns is worth the marginal benefit.

### What to Do Now

**Step 0: Use Anthropic's Programmatic Tool Calling for free (no code change).**

If our harness is using Claude models via litellm, we can add
`"allowed_callers": ["code_execution_20260120"]` to tool definitions and
include the `code_execution_20260120` tool. LiteLLM handles the rest.
Anthropic runs the sandbox. We get code-as-orchestration with zero
infrastructure changes.

This is the highest-leverage change. It requires modifying only `tools.py`
to add the `allowed_callers` field and including the code execution tool
type. No sandbox changes needed.

**Limitations:**
- Anthropic-only (not model-agnostic via litellm for other providers)
- Not eligible for Zero Data Retention
- Code runs on Anthropic's servers, not locally
- Container expires after ~4.5 min inactivity

**Step 1: When we add tools that benefit from chaining, expose them
inside the Docker sandbox.**

The implementation is straightforward:

1. Create a `sandbox_tools/` directory containing thin Python wrappers
   for tools that should be available inside the sandbox.
2. Add a bind-mount to `sandbox.py`: `-v sandbox_tools:/home/sandbox/tools:ro`
3. The LLM's generated code (via existing `run_python`) can import and
   call these tools.
4. Keep `calculator` and `get_current_time` as direct tool calls AND
   available inside the sandbox. No harm in both.

**The trigger for Step 1:** When we have a tool whose results are large
(database queries returning many rows) or a task that requires calling
the same tool many times (batch processing). At that point, the token
savings become meaningful.

**Step 2: If tool count grows past ~20, implement tool search.**

Use Anthropic's `defer_loading` / tool search mechanism. Do not build
filesystem-based discovery -- it is unnecessary complexity for our use case.

### What NOT to Do

1. **Do not build a REST API for tool access inside the sandbox.** This
   requires network access, which breaks our security model.
2. **Do not implement filesystem-based lazy loading.** With 3 tools,
   this is pure overhead. Even with 20 tools, `defer_loading` is simpler.
3. **Do not replace direct tool calls with code-as-orchestration.** Keep
   both. Some tools are better as direct calls (simple, single-step,
   needs HITL approval). Some are better inside code (chaining, batch,
   large intermediate results).
4. **Do not relax `--network=none`** unless a specific tool requires
   external access. When that happens, use host bridging (Pattern C)
   rather than opening network access to the sandbox.

---

## 10. Summary Comparison: All Approaches

| Approach | Token Savings | Complexity | Security | Our Applicability |
|---|---|---|---|---|
| Anthropic Programmatic Tool Calling | 37-98% | Low (API flag) | Anthropic-managed | High -- use today |
| Cloudflare Code Mode | 88-99.9% | Medium | V8 isolate | Low -- JS/TS only |
| smolagents CodeAgent | ~30% fewer steps | Low-Medium | Varies by backend | Medium -- OSS reference |
| Bind-mount tools into our Docker | Proportional to chaining | Low | Same as current | High -- when needed |
| Filesystem lazy loading | 98.7% (150K -> 2K) | High | Depends | Low -- overkill for 3 tools |
| Meta-MCP two-tool pattern | 88% | Medium-High | Deno sandbox | Low -- overkill |

---

## 11. Open Questions

1. **LiteLLM + Programmatic Tool Calling compatibility.** LiteLLM documents
   support for `allowed_callers`, but the code execution container is an
   Anthropic-specific feature. Does the full flow (pausing, tool result
   return, resumption) work through litellm's generic interface, or does
   it require Anthropic-specific API calls? This needs testing.

2. **Stateful vs. stateless sandbox for tool chaining.** Our sandbox is
   stateless (fresh container per call). If the LLM writes code that calls
   a tool, processes the result, then calls another tool based on the first
   result, does this work in a single `run_python` invocation? With our
   current architecture, the tools would need to execute entirely within
   the container. Anthropic's approach (pause-and-resume) handles this
   but requires server-side infrastructure we don't have.

3. **When does our `run_python` tool overlap with code-as-orchestration?**
   Our `run_python` tool already lets the LLM write arbitrary Python.
   If we expose `calculator` and `get_current_time` inside the sandbox,
   the LLM can use `run_python` to call them. This is effectively
   code-as-orchestration using our existing infrastructure. The question
   is whether the LLM will discover and use this pattern without explicit
   prompting.

4. **Tool interface stability.** If tools are exposed as Python functions
   inside the sandbox, their signatures become an API contract. Changing a
   tool's interface requires updating both `tools.py` (for direct calls)
   and `sandbox_tools/` (for in-sandbox calls). How do we keep these in
   sync?

---

## 12. Sources

Architecture and patterns:
- [Anthropic: Code Execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp)
- [Anthropic: Advanced Tool Use](https://www.anthropic.com/engineering/advanced-tool-use)
- [Anthropic: Programmatic Tool Calling docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/programmatic-tool-calling)
- [Cloudflare Blog: Code Mode](https://blog.cloudflare.com/code-mode-mcp/)
- [Meta-MCP Architecture](https://dev.to/tgfjt/a-practical-meta-mcp-architecture-for-claude-code-compressing-60-tools-into-just-two-oje)

Implementations:
- [smolagents blog](https://huggingface.co/blog/smolagents)
- [HuggingFace Agents Course: Code Agents](https://huggingface.co/learn/agents-course/unit2/smolagents/code_agents)
- [olaservo/code-execution-with-mcp](https://github.com/olaservo/code-execution-with-mcp)
- [LLM-in-Sandbox paper](https://huggingface.co/papers/2601.16206)
- [Cloudflare Agents: Codemode](https://developers.cloudflare.com/agents/api-reference/codemode/)
- [OpenAI Codex](https://openai.com/index/introducing-codex/)

Research:
- [Executable Code Actions Elicit Better LLM Agents](https://huggingface.co/papers/2402.01030)
- [Trajectory Reduction for LLM Agent Systems](https://arxiv.org/pdf/2509.23586)

Security:
- [OWASP Top 10 for Agentic Applications 2026](https://www.practical-devsecops.com/owasp-top-10-agentic-applications/)
- [Anthropic: Claude Code Sandboxing](https://www.anthropic.com/engineering/claude-code-sandboxing)

Integration:
- [LiteLLM: Anthropic Programmatic Tool Calling](https://docs.litellm.ai/docs/providers/anthropic_programmatic_tool_calling)
- [Code Sandbox MCP](https://www.philschmid.de/code-sandbox-mcp)
- [OpenAI Cookbook: Code Interpreter Tool](https://developers.openai.com/cookbook/examples/object_oriented_agentic_approach/secure_code_interpreter_tool_for_llm_agents/)

Sandbox approaches (detailed in sandboxed-code-execution.md):
- [Claude Code sandboxing docs](https://code.claude.com/docs/en/sandboxing)
- [dida.do: Secure Python Sandbox](https://dida.do/blog/setting-up-a-secure-python-sandbox-for-llm-agents)
- [smolagents secure code execution](https://huggingface.co/docs/smolagents/en/tutorials/secure_code_execution)
