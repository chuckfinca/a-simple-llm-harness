# Scratch-Builder Round 2: Survivorship Bias, Complexity Threshold, and MCP
**Targeted Deep Dive | February 2026**

---

## Executive Summary

Three key conclusions from this round:

1. **The survivorship bias is real and quantifiable.** The teams that blog about custom builds are the ones that shipped. Independent evidence (Uber, LinkedIn, 400+ LangGraph production users) shows that at serious scale, even advocates of custom-first approaches build *on top of* LangGraph rather than fully custom. The 12-Factor Agents methodology offers the best synthesis: own control flow and context engineering, but don't reinvent durable execution.

2. **The complexity threshold is three specific capabilities, not "scale."** Graduating from a while-loop harness to a framework is triggered by one or more of: (a) durable execution / mid-task resumption after failure, (b) human-in-the-loop with actual wait semantics, or (c) multi-agent coordination with truly shared, inspectable state. Claude Code — Anthropic's own agent — stays custom precisely because it avoids these three requirements.

3. **MCP solves tool connectivity, not orchestration.** After MCP, you still need to build state management, agent routing, governance, and observability. These are where frameworks provide the most remaining value. MCP reduces the *surface area* of the build-vs-buy decision but doesn't eliminate it.

---

## 1. Survivorship Bias: Steelmanning the Framework Argument

### The Octomind Case: Both Directions of Pain

Octomind (AI testing startup) is the most-cited "we left LangChain for custom" story. After 12+ months in production, they abandoned LangChain because it was "a source of friction, not productivity." Their custom replacement uses direct LLM calls, custom function-calling, and minimal external packages.

**But the story doesn't end there.** Their decision was specifically a reaction to LangChain's *abstraction overload* — they needed to:
- Spawn sub-agents that interact with parent agents
- Dynamically change tool availability based on business logic
- Externally observe agent state

These are real, hard requirements. Their custom solution handles them — but their case is about LangChain specifically, not about frameworks in general. LangGraph would have been a more apt comparison, and they don't address it.

**Source**: [Octomind — "Why we no longer use LangChain for building our AI agents"](https://www.octomind.dev/blog/why-we-no-longer-use-langchain-for-building-our-ai-agents)

---

### The Counter-Evidence: What Teams at Scale Actually Did

**Uber (5,000 developers, hundreds of millions of LOC)**: Built an AI developer tooling platform on LangGraph — then built "Lang Effect," their own opinionated wrapper *on top of* LangGraph. They needed multi-agent orchestration, composable components, real-time streaming, and parallel execution. **Key insight: a sophisticated team building at scale chose a framework AND wrote a framework wrapper.** They were not rolling pure custom.

**LinkedIn**: Used LangGraph for their AI Hiring Assistant — a supervisor multi-agent design with specialized agent communication and memory infrastructure built on top.

**LangGraph production base**: 400+ companies in production as of LangGraph Platform GA in June 2025. 12M downloads/month. If custom always won, these numbers wouldn't exist.

**Sources**:
- [ZenML — Uber case study](https://www.zenml.io/llmops-database/building-ai-developer-tools-using-langgraph-for-large-scale-software-development)
- [LangGraph Platform GA blog](https://blog.langchain.com/langgraph-platform-ga/)

---

### The Underpublished Failure Mode

Direct evidence for "we tried custom and failed" is sparse — confirming the survivorship concern. But practitioners describe the failure pattern:

> "Those who choose the DIY approach want full control but their lives become hell — they write everything from scratch and solve the same problems over and over."

> "That last 20% becomes a debugging nightmare, with developers seven layers deep in a call stack, trying to reverse-engineer how prompts get built and why agents keep calling the wrong API in infinite loops."

The 12-Factor Agents research (Dex Horthy, HumanLayer) provides the sharpest quantification: **frameworks get teams to 70-80% quality quickly, but the remaining 20% often requires reverse-engineering the framework itself.** This is the double-edge — frameworks accelerate early progress and slow down late optimization.

**Confidence**: MEDIUM — failure stories exist but aren't as documented as successes. The pattern is credible given the mechanism.

**Source**: [12-Factor Agents — GitHub](https://github.com/humanlayer/12-factor-agents), [Vellum Blog](https://www.vellum.ai/blog/the-ultimate-llm-agent-build-guide)

---

### The Revised Assessment

**The "custom wins" argument was overfit to single-agent, short-horizon use cases.** The weight of evidence suggests:

- For **simple agents** (< 5 tools, no multi-agent coordination, stateless sessions): custom is clearly better — faster, cheaper, more debuggable.
- For **complex agents** (resumable workflows, multi-agent, human-in-the-loop): sophisticated teams consistently use a framework — sometimes building an opinionated layer on top.
- **Nobody is choosing pure custom at Uber/LinkedIn scale.** The advocates of custom in the R1 research are mostly small-to-medium teams building focused, narrow agents.

---

## 2. The Complexity Threshold: Three Specific Trip Wires

### Trip Wire 1: Durable Execution (State Across Failures)

A naive while loop is stateless between Python process restarts. If a long-running agent task fails mid-way (network error, process crash, model timeout), a pure custom solution restarts from scratch or requires you to build your own checkpointing.

**What you must build custom to avoid LangGraph checkpointing:**
- Serializable state objects for every agent turn
- A persistent store (Redis, Postgres, etc.) with a write-on-every-step pattern
- A replay mechanism that reloads state and continues from the last checkpoint
- Timeout and retry semantics with exponential backoff at the orchestration level

This is ~500-1,000 lines of careful, testable infrastructure code. LangGraph's checkpointer does this in ~5 lines. **Slack uses Temporal rather than LangGraph for this** — another valid path, but still not "pure custom."

**When this triggers**: Any agent task running >5 minutes, any workflow with human approval steps, any system needing fault tolerance.

**Source**: [LangGraph Checkpointing guide](https://sparkco.ai/blog/mastering-langgraph-checkpointing-best-practices-for-2025), [ZenML/Slack Temporal case study](https://www.zenml.io/llmops-database/scaling-ai-assisted-developer-tools-and-agentic-workflows-at-scale)

---

### Trip Wire 2: Human-in-the-Loop with Real Wait Semantics

A while loop can trivially print "waiting for approval" and call `input()`. Production HITL is different:
- The agent must **pause**, serialize state, and exit the process
- A human approves via email/Slack/UI (potentially hours later)
- The agent must **resume** in a new process from saved state with the human's input injected

This is durable execution again plus an interrupt/resume primitive. Building it custom requires:
- A task queue (Celery, BullMQ, etc.) to hold pending approvals
- A webhook endpoint to receive human decisions
- State storage and a re-entry mechanism
- Timeout handling for approvals that never come

LangGraph's `interrupt()` + checkpointer solves this. 12-Factor Agents principle #6 ("Launch/Pause/Resume APIs") names it explicitly as something you must own — but owning the *interface* to this pattern is distinct from implementing it from scratch.

**Source**: [LangGraph Human-in-the-Loop medium post](https://medium.com/data-science-collective/architecting-human-in-the-loop-agents-interrupts-persistence-and-state-management-in-langgraph-fa36c9663d6f)

---

### Trip Wire 3: Multi-Agent Coordination with Shared State

Two or more agents need to:
- Share a common state object that one can write and another can read
- Coordinate without polling (event-driven handoffs)
- Have their interaction be inspectable and debuggable after the fact

Custom implementation requires message queues, shared state stores, and explicit event routing. The failure mode without this (GetOnStack's $127→$47k incident) happens when Agent A asks Agent B for help, Agent B asks Agent A, and nobody detects the cycle.

**What LangGraph provides**: Typed state schemas, graph-based routing, conditional edges, and shared state that both framework and developer can inspect.

**Claude Code's deliberate choice**: Anthropic built Claude Code custom with a **single-threaded master loop and strict limits on sub-agent depth** specifically to *avoid* needing multi-agent shared state infrastructure. They pay the cost of sequential execution to avoid the complexity of concurrent agent coordination. This is a valid architectural choice — but it only works because Claude Code's use case permits sequential execution.

**Source**: [ZenML — Claude Code architecture](https://www.zenml.io/llmops-database/claude-code-agent-architecture-single-threaded-master-loop-for-autonomous-coding)

---

### The Claude Code "Custom at Scale" Case Study

Claude Code is the strongest evidence that custom beats frameworks even at production scale:

- Single-threaded master loop (codenamed "nO"): continues while tool calls exist, exits on plain text
- Custom context compressor triggering at ~92% utilization (no vector DB, Markdown-based project memory)
- Custom async dual-buffer queue ("h2A") for mid-task course corrections
- Custom planning system (TodoWrite + reminder injection to prevent objective drift)
- 4 capability primitives (Read, Write, Execute, Connect) + Bash as universal adapter

**Why it works**: Claude Code's task horizon is bounded (single coding session, single user), it doesn't need human approval loops, and it doesn't coordinate with other agents in a shared state graph. These three non-requirements are exactly the three trip wires above. Remove the trip wires and custom wins.

**Key quote from Anthropic's own analysis**: "Sophisticated autonomous behavior can emerge from well-designed constraints and disciplined tool integration rather than complex coordination mechanisms."

**Source**: [ZenML — Claude Code agent architecture](https://www.zenml.io/llmops-database/claude-code-agent-architecture-single-threaded-master-loop-for-autonomous-coding), [How Claude Code Is Built — Pragmatic Engineer](https://newsletter.pragmaticengineer.com/p/how-claude-code-is-built)

---

### Decision Matrix: Custom vs. Framework

| Requirement | Custom (while loop) | Framework (LangGraph/Temporal) |
|-------------|---------------------|-------------------------------|
| Single agent, stateless session | ✅ Preferred | ❌ Overkill |
| < 5 tools, narrow domain | ✅ Preferred | ❌ Overkill |
| Task horizon < ~5 min | ✅ Fine | ❌ Overkill |
| Sequential execution acceptable | ✅ Fine | — |
| Durable execution / fault recovery | ❌ Must build | ✅ Provided |
| Human-in-the-loop with wait semantics | ❌ Must build | ✅ Provided |
| Multi-agent shared state | ❌ Must build | ✅ Provided |
| Production observability + replay | ❌ Must build | ✅ Provided (LangSmith) |
| 5+ concurrent agent types | ❌ Gets messy | ✅ Graph primitives help |

---

## 3. MCP's Impact on Build-vs-Buy

### What MCP Actually Solves

MCP (97M+ monthly SDK downloads, backed by Anthropic/OpenAI/Google/Microsoft as of end-2025) standardizes:
- **Tool discovery**: Agents can find available tools without hard-coded schemas
- **Tool invocation protocol**: Standardized request/response format
- **Tool portability**: One MCP server works across Claude, GPT-4o, Gemini without adapter code

Before MCP, each framework had its own tool definition format. A LangChain tool required LangChain-specific decorators. An OpenAI function required OpenAI-specific schema. MCP's unification is real and significant.

**Direct impact on build-vs-buy**: The framework value proposition for tool abstraction **is meaningfully reduced** by MCP. If your tools are MCP servers, you don't need LangChain's tool abstraction layer. You can call them directly via the Anthropic or OpenAI SDK with first-class MCP support (Anthropic's MCP connector is native as of October 2025).

**Sources**:
- [Anthropic — New Agent Capabilities API (Oct 2025)](https://www.anthropic.com/news/agent-capabilities-api)
- [Thoughtworks — MCP's Impact on 2025](https://www.thoughtworks.com/en-us/insights/blog/generative-ai/model-context-protocol-mcp-impact-2025)
- [One Year of MCP — MCP Blog](https://blog.modelcontextprotocol.io/posts/2025-11-25-first-mcp-anniversary/)

---

### What MCP Does NOT Solve

This is the critical question. MCP standardizes the tool *interface* but leaves the orchestration *logic* entirely to you.

**Still hard to build custom after MCP:**

1. **State management across tool calls**: MCP says nothing about how to persist agent state between sessions, across failures, or across multiple concurrent agents. You need your own state store, schema, and write-ahead log.

2. **Agent routing and conditional logic**: Which MCP server gets called when? Under what conditions? MCP provides tool discovery but not decision routing. A LangGraph conditional edge or a custom router function handles this — MCP doesn't.

3. **Observability at the agent level**: MCP logs individual tool invocations but "when an AI agent makes 50 tool calls across 10 different services, understanding where things went wrong requires comprehensive tracing" of the *agent's reasoning*, not just tool calls. MCP gateways emerged in 2026 specifically to fill this gap — but they're a separate product layer on top of MCP.

4. **Multi-MCP-server coordination**: Managing 10+ MCP servers in production means "each MCP server needs its own deployment, monitoring, versioning, and maintenance." Without a gateway or framework, operational overhead multiplies with server count.

5. **Auth, governance, and audit trails**: MCP gateways (Portkey, TrueFoundry, Composio) add centralized auth, role-based tool access, and audit trails. The raw MCP protocol provides none of this. In regulated environments this is non-negotiable — and you must either buy a gateway or build this layer yourself.

**Sources**:
- [Advanced MCP: Agent Orchestration, Chaining, and Handoffs](https://www.getknit.dev/blog/advanced-mcp-agent-orchestration-chaining-and-handoffs)
- [MCP Gateway comparison 2026](https://composio.dev/blog/best-mcp-gateway-for-developers)
- [InformationWeek — MCP: Build or Buy](https://www.informationweek.com/machine-learning-ai/model-context-protocol-servers-build-or-buy-)

---

### The Revised Build-vs-Buy Surface Area After MCP

**MCP eliminates the need to build:**
- Tool schema adapters (no more per-framework tool definitions)
- Provider-specific tool calling code (works across all major models)
- Custom tool discovery registries

**MCP does NOT eliminate the need to build (or buy):**
- Agent state management
- Conditional routing between agents and tools
- Durable execution / checkpointing
- Human-in-the-loop interrupt/resume
- Cross-agent observability and tracing
- Auth, governance, rate limiting (requires MCP gateway)

**Net assessment**: MCP reduces the custom-build surface area by perhaps 20-30% (tool integration work). It does not touch the 70-80% that is genuinely hard: orchestration, state, observability. The framework argument for those components remains intact.

---

## Synthesis: The Updated Build-vs-Buy Heuristic

Based on Round 1 + Round 2 evidence, here is the clearest heuristic we can offer:

### Start Custom When:
- Single agent, narrow domain, bounded task horizon
- < 5 tools with clear, stable schemas
- No multi-agent coordination required
- No human approval loops with wait semantics
- Tasks complete within one session (no mid-task failures requiring resume)
- Team needs full debuggability (custom wins on inspection/transparency)

### Graduate to Framework When You Hit:
- **Trip Wire 1**: "I need this agent to resume after process restart"
- **Trip Wire 2**: "I need to pause and wait for human approval, then continue"
- **Trip Wire 3**: "Two agents need to share and inspect state"

### The Middle Ground (Most Teams):
- Use Anthropic/OpenAI SDK directly for the agent loop (not LangChain)
- Use Instructor/PydanticAI for structured outputs
- Use MCP for tool connectivity standardization
- Add LangGraph specifically when hitting trip wires — not before
- Buy eval/observability (Braintrust, Langfuse) rather than build it
- For long-running workflows: consider Temporal as the runtime layer rather than LangGraph

### The 12-Factor Agent Synthesis
The 12-Factor Agents framework (Dex Horthy, HumanLayer — [GitHub](https://github.com/humanlayer/12-factor-agents)) provides the most actionable synthesis: always own your prompts, context window, control flow, and error handling. These are the differentiating craft. Delegate durable execution, human-in-the-loop primitives, and monitoring infrastructure to tools that have already solved them.

---

## Residual Open Questions

1. **LangGraph vs. Temporal for durable execution**: Both solve trip wire 1. LangGraph is Python-native and LLM-aware; Temporal is language-agnostic and battle-tested at massive scale. For an LLM client: which is the right call and why? (Framework-analyst teammate should address this directly.)

2. **The 70-80% quality ceiling**: 12-Factor Agents claims frameworks cap out at 70-80% quality before reverse-engineering is needed. Is this specific to LangChain, or does it apply to LangGraph and PydanticAI as well? Need practitioner testimonials at that threshold specifically.

3. **MCP gateway maturity**: Portkey, TrueFoundry, Composio, Mintlify — all launched MCP gateway products in late 2025. Which is production-ready vs. early-stage? Production-engineer teammate should assess these.

---

## Sources (Annotated)

| Source | Date | Confidence | Key Contribution |
|--------|------|------------|-----------------|
| [Octomind — Left LangChain](https://www.octomind.dev/blog/why-we-no-longer-use-langchain-for-building-our-ai-agents) | 2024 | HIGH | Best documented custom-wins story; specific about failure modes of LangChain abstractions |
| [ZenML — Uber/LangGraph case study](https://www.zenml.io/llmops-database/building-ai-developer-tools-using-langgraph-for-large-scale-software-development) | 2025 | HIGH | Shows even custom-savvy team built LangGraph wrapper at scale |
| [ZenML — Claude Code architecture](https://www.zenml.io/llmops-database/claude-code-agent-architecture-single-threaded-master-loop-for-autonomous-coding) | 2025 | HIGH | Best documented "stayed custom at scale" case; Anthropic's own agent |
| [12-Factor Agents — GitHub](https://github.com/humanlayer/12-factor-agents) | 2025 | HIGH | Best synthesis of what you must own vs. delegate; frameworks to 70-80% then you're stuck |
| [LangGraph Platform GA blog](https://blog.langchain.com/langgraph-platform-ga/) | Jun 2025 | MEDIUM | 400+ companies evidence; note it's self-reported by LangChain |
| [Building LangGraph from first principles](https://blog.langchain.com/building-langgraph/) | 2025 | HIGH | Why LangGraph was built: Uber/LinkedIn/Klarna pain points — durable execution, retries, non-determinism |
| [MCP — One Year Anniversary](https://blog.modelcontextprotocol.io/posts/2025-11-25-first-mcp-anniversary/) | Nov 2025 | HIGH | Scope of MCP adoption; what it standardizes |
| [ClickHouse — 12 framework MCP comparison](https://clickhouse.com/blog/how-to-build-ai-agents-mcp-12-frameworks) | 2025 | MEDIUM | What MCP doesn't solve; protocol implementation still required without frameworks |
| [InformationWeek — MCP Build or Buy](https://www.informationweek.com/machine-learning-ai/model-context-protocol-servers-build-or-buy-) | 2025 | MEDIUM | MCP build/buy tension; ongoing protocol evolution risk |
| [Advanced MCP: Agent Orchestration gaps](https://www.getknit.dev/blog/advanced-mcp-agent-orchestration-chaining-and-handoffs) | 2025 | MEDIUM | What MCP leaves unsolved: state, routing, observability |
| [Pragmatic Engineer — How Claude Code is built](https://newsletter.pragmaticengineer.com/p/how-claude-code-is-built) | 2025 | HIGH | External architectural analysis of Claude Code's custom build |
| [Vellum — DIY nightmare quote](https://www.vellum.ai/blog/the-ultimate-llm-agent-build-guide) | 2025 | MEDIUM | "Seven layers deep in a call stack" — failure pattern for pure custom |
