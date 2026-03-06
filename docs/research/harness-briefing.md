# LLM Harness Best Practices Briefing
## Actionable Research for Implementation Engagement
**Date:** February 26, 2026
**Research Team:** 4 specialist agents (scratch-builder, framework-analyst, trends-scout, production-engineer) across 2 research rounds, 80+ web sources reviewed

---

## 1. Executive Summary

1. **The harness is the product, not the model.** A February 2026 experiment changed only the tool schema across 16 models — one went from 6.7% to 68.3% success. No model change, no framework change. Context engineering and tool design are where competitive advantage lives.

2. **Start custom, graduate to frameworks at specific trip wires.** Build the agent loop with direct SDK calls (Anthropic SDK + Pydantic). Adopt LangGraph only when you need: durable execution across failures, human-in-the-loop with real wait semantics, or multi-agent shared state. This is what Anthropic themselves do with Claude Code.

3. **LangGraph is the production leader for complex workflows; Pydantic AI for simple ones.** LangGraph has 400+ production companies (Uber, LinkedIn, Elastic). Pydantic AI (v1.0 Sept 2025) wins for single-agent, type-safe, linear workflows. CrewAI has documented reliability problems — avoid for anything critical.

4. **For a client building on Anthropic models: use the Claude Agent SDK.** Released Sept 2025, it's Anthropic's own production runtime (powers Claude Code). Built-in tools, hooks for governance, MCP integration, and multi-cloud support (Bedrock, Vertex, Azure). Combine with LangGraph if graph orchestration is needed.

5. **Prompt caching is the highest-ROI optimization — architect for it from day zero.** 90% cost reduction on cached tokens. Static content (system prompt, tools) at top; dynamic content at bottom. Never put timestamps in system prompts. This is an architectural decision that's expensive to retrofit.

6. **Multi-agent is powerful but expensive and fragile.** 15x token cost vs. chat. Use only for genuinely parallelizable, read-dominant tasks where single-agent success rate is below ~45%. Centralized topology always; never "bag of agents" (17x error amplification).

7. **Security must be infrastructure-level, not prompt-level.** Prompt injection is still unsolved. MCP expands the attack surface significantly. Use an MCP gateway (Portkey, Kong, Cloudflare) with OAuth 2.1. Move all authorization to the API layer where the model cannot circumvent it.

---

## 2. What Are LLM Harnesses?

An LLM harness (also called agent framework, orchestration layer, or agentic scaffolding) is the software layer between your application and the LLM API. It manages:

- **Context engineering** — what information goes into the LLM's context window (and what stays out)
- **Tool orchestration** — which tools the LLM can call, how results flow back, error handling
- **State management** — persisting agent progress across turns, sessions, and failures
- **Control flow** — deciding when to loop, branch, escalate, or stop
- **Observability** — tracing, logging, and evaluating agent behavior
- **Safety** — budget limits, permission boundaries, human approval gates

**The taxonomy:**
- **Harness** = the full system around the model (your code + whatever libraries/frameworks you use)
- **Framework** = an opinionated library providing pre-built harness components (LangGraph, Pydantic AI, CrewAI)
- **Runtime** = the execution environment for long-running agents (Temporal, Inngest)
- **Gateway** = infrastructure layer between your code and model APIs (Portkey, LiteLLM)

The most important insight from the research: **context engineering — not prompt engineering — is the core discipline.** Anthropic, Manus, Spotify, and Cognition independently converge on this. The harness must actively manage what goes into context (write, select, compress, isolate), not just format prompts.

---

## 3. Build vs. Buy

### The Evidence-Based Answer

Neither pure custom nor full framework adoption. The evidence points to a **hybrid approach**: own your core logic, buy your infrastructure.

### Start Custom When:
- Single agent, narrow domain, bounded task horizon
- Fewer than 5 tools with stable schemas
- No multi-agent coordination required
- No human approval loops with wait semantics
- Tasks complete within one session
- Team needs full debuggability

**What "custom" means in 2025-2026:**
- Direct SDK calls (`anthropic`, `openai`) for the agent loop
- `pydantic` for tool schema validation
- `instructor` or native structured outputs for validated responses
- An eval/observability tool (Langfuse) — always bought, never built
- Circuit breakers and budget limits — always custom

### Graduate to a Framework When You Hit These Trip Wires:

| Trip Wire | What It Is | Custom Build Cost | Framework Solution |
|-----------|-----------|-------------------|-------------------|
| **Durable execution** | Agent must resume after process crash/restart | ~500-1,000 lines of checkpointing code | LangGraph checkpointer (~5 lines) or Temporal |
| **Human-in-the-loop** | Pause agent, wait hours for human approval, resume | Task queue + webhook + state store + re-entry | LangGraph `interrupt()` + persistence |
| **Multi-agent shared state** | Two+ agents read/write common state with inspection | Message queues, shared stores, cycle detection | LangGraph typed state + graph routing |

**Key evidence:** Claude Code — Anthropic's own production agent — is fully custom-built without using an external framework. Its core agentic loop is a single-threaded while-loop, but it does support session resumption, human-in-the-loop permissions, and multi-agent coordination (agent teams with peer-to-peer messaging and shared task lists). Anthropic built purpose-fit versions of these capabilities rather than adopting LangGraph — but backed by a dedicated engineering team maintaining non-trivial custom infrastructure (context compressor, async dual-buffer queue, planning system with goal-drift prevention, full hooks/lifecycle layer).

**The survivorship bias caveat:** Teams that blog about custom builds are the ones that shipped. At scale (Uber, LinkedIn, 400+ LangGraph companies), even custom-first teams end up building on top of frameworks — often writing opinionated wrappers. Pure custom at enterprise scale is rare.

### Complexity Profiles — Match Architecture to Use Case

Claude Code proves that single-threaded custom architecture can be extraordinarily capable. But Claude Code also benefits from a dedicated team at Anthropic maintaining purpose-built infrastructure and intimate knowledge of their own model's behavior. The right architecture depends on what you're building.

**Profile A: Narrow, Bounded Agent**
*Examples: document Q&A, structured data extraction, form processing, workflow automation with fixed steps*

- Sessions are short (minutes, not hours)
- Tool set is small and stable (< 5 tools)
- No human approval loops needed mid-task
- Single user, single task, stateless between sessions

**Recommended architecture:** Custom while-loop + Anthropic SDK + Pydantic + Langfuse. No framework needed. This is simpler than Claude Code — you need *less*, not more. Budget: 50-200 lines of orchestration code.

**Profile B: Capable Single Agent, Moderate Complexity**
*Examples: coding assistant, research agent, customer service with tool access, multi-step analysis*

- Sessions may be long (30+ minutes of agent work)
- Tool set is moderate (5-15 tools)
- Human is present but agent works semi-autonomously
- Needs context management as conversations grow
- May need session resume

**Recommended architecture:** Claude Agent SDK or Pydantic AI. The SDK handles the agent loop, tool execution, and context management. You focus on tool design and context engineering. This is roughly Claude Code's complexity profile — single-threaded works well here. Budget: the SDK + your custom tools + eval infrastructure.

**Hidden complexity to plan for:** Context management is the hard part. You'll need to handle context compression (what happens at 50k+ tokens?), tool output summarization (tool results can be huge), and goal drift on long tasks. Claude Code solves these with custom infrastructure — you'll need to solve them too, either custom or via framework primitives.

**Profile C: Multi-Step Workflow with Human Gates**
*Examples: loan processing with approval stages, compliance review pipelines, multi-day research with checkpoints*

- Tasks span hours or days
- Human approval required at specific gates (not just "user is watching")
- Must survive process restarts without losing progress
- Audit trail of every decision required

**Recommended architecture:** LangGraph or Temporal. You've hit the trip wires. Building durable execution + async human approval + audit logging custom is ~1,000+ lines of careful infrastructure code that LangGraph provides out of the box. The single-threaded while-loop breaks down when the process needs to pause for 3 hours waiting for a human, serialize state, then resume in a new process.

**Important note:** Adopting LangGraph does not mean adopting multi-agent or parallel execution. LangGraph's graph is a logical control flow structure, not a threading model. It executes synchronously by default — one node at a time. You can use LangGraph purely for its checkpointing, `interrupt()`, and state management while keeping execution single-threaded and sequential. This is likely the sweet spot for Profile C: you get durable workflows and human gates without the complexity and failure modes of multi-agent coordination.

**Profile D: Multi-Agent System**
*Examples: complex research across multiple domains, parallel document processing pipelines, orchestrator + specialist workers*

- Multiple agents with genuinely independent subtasks
- Need coordination, shared state, or result merging
- Task value justifies 15x token cost
- Read-dominant, parallelizable work

**Recommended architecture:** LangGraph for the coordination graph + Claude Agent SDK for individual agent execution. Use centralized topology (orchestrator + workers), never peer-to-peer. Budget the 15x token cost and validate the economics before committing.

**The danger zone: Profile B creeping into Profile C.** The most common architectural mistake is starting with a simple while-loop (Profile A/B) and gradually adding custom persistence, custom approval flows, and custom multi-agent coordination until you've built a worse version of LangGraph without realizing it. If you see yourself writing a state serializer, a webhook handler for approvals, or a message queue between agents — stop and adopt a framework instead.

### The Bitter Lesson Applied to Harnesses

Sutton's [Bitter Lesson](http://www.incompleteideas.net/IncsightfulTidbit/SuttonBitterLesson.html): every time AI researchers hand-crafted knowledge into systems, general methods that scaled compute eventually overtook them. This is already playing out in harness design. Complex chain abstractions, custom ReAct loops, elaborate multi-agent topologies — these are all "encoding human knowledge" that model improvements are steadily absorbing. Manus rebuilt their harness 4 times and warns: "the harness built today will likely be obsolete when the next frontier model arrives."

The practical implication: **invest heavily in things models won't absorb — eval infrastructure, observability, security, domain-specific tool design, data pipelines.** Keep the orchestration layer thin and replaceable, because that's what the next model generation will make obsolete. The can.ac experiment (6.7% → 68.3% from tool schema alone) proves harness design matters enormously with today's models — but the *kind* of harness work that matters is context engineering and tool design, not elaborate orchestration logic.

This is the deeper reason the recommendation is "custom + minimal framework" rather than betting big on any one orchestration layer.

### The 12-Factor Agent Synthesis

The [12-Factor Agents](https://github.com/humanlayer/12-factor-agents) framework operationalizes this: **own your prompts, context window, control flow, and error handling** (these are differentiating craft that models won't replace). **Delegate durable execution, human-in-the-loop primitives, and monitoring** to tools that have already solved them (these are infrastructure, not differentiation).

### MCP's Impact on Build-vs-Buy

MCP (97M+ monthly SDK downloads, now universal standard) eliminates the need to build tool schema adapters, provider-specific tool calling code, and custom tool discovery. It reduces the custom-build surface area by ~20-30%.

MCP does NOT eliminate the need for: agent state management, conditional routing, durable execution, human-in-the-loop, cross-agent observability, or auth/governance. These are where frameworks provide remaining value.

---

## 4. Framework Landscape

### The Decision Tree

```
Is the agent simple (single-agent, linear steps, structured output)?
├── YES → Pydantic AI (type safe, testable, durable with Temporal)
│         If building on Anthropic → also evaluate Claude Agent SDK
└── NO (multi-agent, cycles, branching, complex state)
    └── LangGraph (purpose-built, production-proven)

Observability: Langfuse (self-hosted, MIT, framework-agnostic)
Structured outputs: Instructor or Pydantic AI
Tool connectivity: MCP standard
```

### Framework Comparison

| Framework | Best For | Production Evidence | Lock-in Risk | Our Recommendation |
|-----------|----------|--------------------|--------------|--------------------|
| **LangGraph** | Complex stateful multi-step agents | Uber, LinkedIn, Elastic, 400+ companies | Medium (LangChain ecosystem) | Use for complex workflows |
| **Pydantic AI** | Type-safe single agents, linear workflows | v1.0 Sept 2025, growing adoption | Low | Use for simple agents |
| **Claude Agent SDK** | Anthropic-native single/hierarchical agents | Powers Claude Code | Low (multi-cloud) | Primary choice for Anthropic builds |
| **OpenAI Agents SDK** | Fast MVP with OpenAI models | March 2025 GA | High (OpenAI) | Only if OpenAI-committed |
| **CrewAI** | Demos, non-critical high-volume | Enterprise sales traction | Low | Avoid for reliability-critical work |
| **DSPy** | Automated prompt optimization | Stanford-backed, niche | Low | Complement, not replacement |
| **Microsoft Agent Framework** | Azure enterprise, regulated industries | KPMG, BMW (RC, GA Q1 2026) | High (Azure) | Only if Azure-committed |
| **Instructor** | Structured output extraction | 3M+ downloads, widely used | None | Use alongside any framework |

### LangGraph vs. Pydantic AI — When to Use Which

| Factor | Pydantic AI Wins | LangGraph Wins |
|--------|-----------------|----------------|
| Single agent, linear steps | Yes | Overkill |
| Type safety, validation | Native Pydantic | Flexible |
| Multi-agent orchestration | Limited | Purpose-built |
| Complex branching/cycles | No | Yes |
| Human-in-the-loop | Supported | Native, stronger |
| Durable execution | Temporal integration | Checkpointer |
| Learning curve | Gentler | Steep |
| Testing/debugging | Easier (pure Python) | Harder (graph state) |
| Production evidence | Growing | Strong (Uber, Elastic, LinkedIn) |

**Rule of thumb:** Start with Pydantic AI. Introduce LangGraph only when the workflow demands graph primitives.

### Claude Agent SDK — For Anthropic-Model Clients

The Claude Agent SDK (released Sept 29, 2025) is Anthropic's own production runtime — the same infrastructure powering Claude Code, now programmable. Key facts:

- **Not a graph orchestration framework** — it's a single-agent autonomous execution runtime
- Built-in tools: Read, Write, Edit, Bash, Glob, Grep, WebSearch, WebFetch
- Hooks system (`PreToolUse`, `PostToolUse`, etc.) for audit logging, approval flows, governance
- Hierarchical subagents (not graph-based)
- First-class MCP integration
- Multi-cloud: Bedrock, Vertex, Azure — not locked to Anthropic API
- **Claude models only.** Multi-cloud but not multi-model — no official support for OpenAI, Gemini, or open-source models. If the client may need to swap models in the future, Pydantic AI or LangGraph (both model-agnostic) are safer bets.

**For this engagement:** Claude Agent SDK is the natural choice for the agent execution layer. If complex graph orchestration is needed, combine with LangGraph (LangGraph for the graph, Claude SDK for individual agent execution).

### LangChain (Classic) — Avoid

LangChain classic is effectively deprecated. Even the LangChain team says "use LangGraph." Key problems: 2.7x token overhead, >1 second added latency per call, debugging opacity, frequent breaking changes. Teams that left moved to direct API calls, not competing frameworks.

---

## 5. Emerging Patterns

### Context Engineering (Confirmed — High Priority)

**The #1 skill for harness builders.** Not prompt engineering — context engineering: managing the entire information environment the LLM operates in.

**The production context pipeline:**

```
Request/Turn
    │
    ▼
[1. LOAD DURABLE STATE]
    System prompt, agent identity, task goals
    Retrieved memories, prior session summaries
    External: file system scratchpad, todo.md
    │
    ▼
[2. SELECT WORKING CONTEXT]
    Current turn input
    Relevant tool outputs (references, not full objects)
    Recent conversation history (last N turns)
    RAG results (filtered by relevance)
    │
    ▼
[3. ISOLATE HEAVY OBJECTS]
    Images, audio, large docs stay in execution environment
    Return values only passed to LLM
    Token-heavy tool results summarized before entering context
    │
    ▼
[4. LLM CALL]
    Context = durable state + selected context
    │
    ▼
[5. POST-TURN OPERATIONS]
    Write new notes to scratchpad
    Update task state
    Store key decisions to memory
    COMPRESS if context > threshold
```

**The core design principle:** Separate durable state from working context. The conversation history should NOT be the primary state store. Externalize state and reconstruct working context at each turn.

**Manus's production lessons:**
- KV-cache hit rate is the single most important metric
- Avoid dynamically adding/removing tools mid-iteration
- Use todo.md task recitation to fight goal drift
- Leave failed actions in context (updates model's beliefs, reduces repetition)
- Use the file system as unlimited external memory

### Model Context Protocol (MCP) — Standard, But Secure It

MCP won the tool connectivity standardization race. 97M+ monthly SDK downloads. Adopted by OpenAI, Google, Microsoft, AWS. Donated to Linux Foundation (Dec 2025). Use it for all new tool integrations.

**But the security surface is real:**
- Tool poisoning: malicious instructions in tool descriptions
- Rug-pull attacks: tools mutate definitions after approval
- Cross-server manipulation: malicious server intercepts calls to trusted servers
- CVE-2025-6514: critical OS command injection in mcp-remote

**Mandatory for production:** Use an MCP gateway (see Security section).

### Multi-Agent Architecture — Use Sparingly, With Heuristics

The Google/MIT study (Dec 2025, 180 configurations) provides the definitive guidance:

**When multi-agent helps:**
- Parallelizable tasks: +80.9% vs. single agent (centralized topology)
- Read-dominant tasks (research, analysis): good fit
- Tasks exceeding single context window: justified for isolation

**When multi-agent hurts:**
- Sequential tasks: -39% to -70% vs. single agent
- Write-dominant tasks (code editing, document modification): always single-agent
- Single-agent success rate above ~45%: diminishing returns

**Decision heuristics:**
1. Can subtasks be described without referencing each other's outputs? If yes → parallelizable → multi-agent may help
2. Read-dominant or write-dominant? Write → always single-agent
3. Single-agent baseline above ~45% success? → Stay single-agent
4. Does task exceed single context window? → Multi-agent for isolation
5. Does value justify 15x token cost? If not → single-agent

**Topology matters more than agent count.** "Bag of agents" (no coordination): 17x error amplification. Centralized (orchestrator + workers): 4.4x. Always use centralized topology.

### The "Shrinking Middle" — Frameworks Are Thinning

Native API capabilities are absorbing what frameworks used to provide:
- Native tool use replaces custom ReAct implementations
- Structured outputs (JSON Schema enforcement) replace output parsers
- Extended thinking replaces chain-of-thought framework features
- 1M+ token context windows reduce some RAG use cases

**What frameworks still earn their keep on:**
- Stateful workflows with checkpointing (LangGraph)
- Human-in-the-loop patterns (LangGraph `interrupt()`)
- Multi-agent coordination (LangGraph graph primitives)
- Observability (Langfuse, LangSmith)

### Structured Outputs — Now Native

All major APIs support guaranteed structured output (JSON Schema enforcement). Use it for any machine-readable output. Combine with enum constraints to make invalid states unrepresentable. Libraries like Instructor remain valuable for complex extraction but less critical for basic use cases.

---

## 6. Production Readiness

### 6.1 Evaluation & Observability

**The eval gap is the #1 risk for production agents.** Hamel Husain (trained 2,000+ engineers at OpenAI, Anthropic, Google): "Unsuccessful AI products share a common root cause: failing to create robust evaluation systems."

**Eval framework (adopt this):**
1. **Level 1: Unit Tests** — scoped assertions by feature/scenario, run on every code change
2. **Level 2: Human + LLM-as-judge** — log traces obsessively, validate judge alignment with human ground truth
3. **Level 3: A/B Testing** — only after Levels 1 and 2 are solid

**Agent evaluation must be trajectory-level**, not just final-answer:
- Tool selection accuracy — did it pick the right tool?
- Trajectory coherence — did the reasoning chain make sense?
- Error recovery — did it handle failures?
- Goal completion — was the outcome correct?

**LLM-as-judge works but has known biases:**
- Verbosity bias (longer = higher scores)
- Self-enhancement bias (favors own style)
- Non-determinism (same response, different scores)
- Mitigation: validate against human ground truth, use pairwise comparison, never use alone in high-stakes domains

**Observability tool recommendation: Langfuse**

| Dimension | Langfuse (Recommended) | LangSmith | Braintrust |
|-----------|----------------------|-----------|------------|
| Open source | Yes (MIT) | No | No |
| Self-hosting | First-class, full parity | Enterprise-only | No |
| Framework lock-in | None | LangChain ecosystem | None |
| LangGraph integration | Official, mature | Native | Via OTel |
| Agent graph visualization | GA Nov 2025 | Comprehensive | Nested spans |
| Pricing | Usage-based / free self-hosted | $39/user/mo + traces | SaaS |
| OTel support | Native | Limited | Partial |

Langfuse wins for any client where independence, data sovereignty, or cost predictability matters. The LangGraph integration via CallbackHandler is mature and officially documented.

### 6.2 Cost & Latency

**Cost by architecture type (Anthropic's own data):**

| Architecture | Token Multiplier | Monthly Cost (1K users/day) |
|-------------|-----------------|---------------------------|
| Chat (baseline) | 1x | — |
| Simple RAG | ~2-3x | $600–$6,000 |
| Tool-calling agent | ~4x | $1,500–$30,000 |
| Multi-agent | ~15x | $5,000–$30,000+ |

**The critical insight:** Agents have ~100:1 input-to-output token ratio. You're paying mostly for context, not generation. This is why prompt caching is disproportionately valuable.

**Cost horror stories (calibration points):**
- $500/month → $847,000/month (1,694x) from runaway agent loop
- $50/month PoC → $2.5 million/month in production (50,000x)
- $127/week → $47,000/4-weeks from infinite loop

**Non-negotiable guardrails (implement before first user traffic):**
1. Hard turn limits per session (circuit breaker)
2. Cost caps per conversation with human escalation
3. Loop detection (terminate on repetitive outputs)
4. Context pruning (summarize old turns, don't grow unbounded)
5. Execution timeout

**Prompt caching — highest ROI optimization:**
- 90% cost reduction on cached tokens, 85% latency reduction
- Cache-friendly prompt structure: static content (system prompt, tools) at top; dynamic content (user messages) at bottom
- Five rules from Manus's production playbook:
  1. Never put timestamps in system prompts (invalidates entire prefix)
  2. Make conversation history append-only (never truncate from middle)
  3. Use deterministic serialization (`sort_keys=True` on JSON)
  4. Manage tools via masking, not removal (keep full tool list always)
  5. Place explicit cache breakpoints at end of each static section

**Expected cache performance:**

| Use Case | Achievable Hit Rate | Cost Reduction |
|----------|-------------------|----------------|
| FAQ/support agent | 80–95% | 72–86% |
| Research agent | 40–70% | 36–63% |
| Coding agent | 20–50% | 18–45% |
| Multi-turn conversation | 60–85% | 54–77% |

**Model routing** pays off at scale (>10,000 requests/day): route simple tasks to cheap models, complex tasks to expensive ones. RouteLLM shows ~60-85% cost reduction while maintaining 95% quality. Tier structure: Gemini Flash Lite (high-volume, low-value) → Claude Haiku (medium) → Claude Sonnet (standard) → Claude Opus (critical reasoning, low volume).

### 6.3 Security & Trust Boundaries

**Core principle: move security to infrastructure, not prompts.** Every new model brings new prompt injection exploits within hours. Prompt-based defenses are insufficient.

**Prompt injection is still unsolved.** Researchers bypassed all 8 tested defenses with adaptive attacks in 2025. 82.4% of LLMs execute malicious tool calls from "peer agents" in multi-agent systems (vs 41.2% for direct injection).

**Production-hardened defenses that work:**
1. **Session tainting** (Oso pattern): Once a session touches untrusted data, it loses access to sensitive tools for its duration. Purely structural — no model behavior involved.
2. **API-layer authorization** (Komodo Health pattern): LLM has zero knowledge of auth. All access control at the API layer.
3. **Dual-layer permissions** (Wakam pattern): Users can only invoke agents if they hold permissions for the agent's data sources.

**MCP Security — mandatory for production:**

Use an MCP gateway (Portkey, Kong, or Cloudflare) with:
- OAuth 2.1 with PKCE (mandatory per June 2025 spec)
- Resource Indicators (RFC 8707) to scope tokens per server
- Per-client consent registry
- Short-lived tokens, credentials in secrets manager
- SSRF mitigation: egress proxy blocking private IP ranges
- Input/output validation for all tool calls
- State-changing operations gated on human approval for untrusted content

**The gap that remains unsolved:** Prompt injection from tool outputs has no clean protocol-level solution. The only defense is architectural — restrict what tools are callable when processing untrusted content.

**OWASP Agentic Top 10 (Dec 2025):** ASI01 (Agent Goal Hijack), ASI02 (Tool Misuse), ASI03 (Identity & Privilege Abuse), ASI04 (Supply Chain), ASI05 (Unexpected Code Execution), ASI06 (Memory & Context Poisoning), ASI07 (Insecure Inter-Agent Communication), ASI08 (Cascading Failures), ASI09 (Human–Agent Trust Exploitation), ASI10 (Rogue Agents). Use as a security review checklist.

**Sandboxing:** Non-negotiable for any agent that executes code. Docker containers as minimum baseline. Defense-in-depth: OS primitives + hardware virtualization + network segmentation. Performance cost (~200-500ms) is negligible vs. LLM roundtrip latency.

**Human-in-the-loop design:** Approval flows must not destroy throughput. Design for async approval with timeout handling. If human doesn't respond within N minutes, fail safe (decline the action, not proceed). LangGraph's `interrupt()` + checkpointer is the standard pattern.

---

## 7. Success Stories & Cautionary Tales

### Success Stories

**Manus AI — Context Engineering Pioneer**
Rebuilt their agent framework 4 times. Settled on context engineering as the core discipline. Ships improvements in hours vs. weeks by betting on in-context learning over fine-tuning. KV-cache hit rate is their #1 production metric. Warning: "the harness built today will likely be obsolete when the next frontier model arrives."

**blog.can.ac — Harness-Only Model Improvement (Feb 2026)**
Changed only the tool schema (hash-based line addressing) across 16 models. Grok Code Fast 1: 6.7% → 68.3% success (10x improvement). No model change. Strongest evidence that harness design is where competitive advantage lives.

**Slack — Temporal-Backed Multi-Agent Escalation**
Custom multi-agent workflow on Temporal handling 5,000+ monthly agentic requests. Mid-task resumption across failures. Used Temporal as runtime rather than a framework's state machine.

**11x — LangGraph Hierarchical SDR**
AI Sales Development Representative achieving human-level 2% reply rates. Iterated through ReAct → workflow-based → hierarchical multi-agent on LangGraph. Evidence that LangGraph adds genuine value for complex role-based workflows.

**Uber — LangGraph + Custom Wrapper**
5,000 developers, hundreds of millions of LOC. Built "Lang Effect" as an opinionated wrapper on top of LangGraph. Evidence that even sophisticated teams choose frameworks at scale — then customize.

**Spotify — Context Engineering with Claude Code**
"Honk" project (background coding agents). Claude Code was the top-performing agent for 50+ migrations. Credits context engineering as the key enabler.

**Care Access — Prompt Caching ROI**
86% cost reduction + 3x speed improvement from architectural redesign separating static vs. dynamic context. The clearest cost optimization case study.

### Cautionary Tales

**GetOnStack — Runaway Agent Loop**
$127/week → $47,000/4-weeks from an undetected infinite agent loop. No circuit breakers, no cost caps. Non-negotiable: every production agent needs hard limits.

**LangChain Migrations — Over-Abstraction Tax**
BuzzFeed, Octomind, and others abandoned LangChain. Direct API calls "immediately outperformed" in quality and accuracy. 2.7x token overhead, >1 second added latency. A fintech team saved ~$200k/year by rewriting from LangChain to custom.

**CrewAI — Demo-to-Production Gap**
Manager-worker architecture "does not function as documented" per independent analysis. Non-deterministic behavior, context window overflow loops, inability to write unit tests. Enterprise metrics (60% Fortune 500) reflect managed platform adoption, not raw framework reliability.

**The Compounding Math**
95% per-step reliability × 20 steps = 36% end-to-end success rate. A "step" is each LLM call that results in a decision or action — each loop iteration where the model calls a tool or makes a routing choice. This compounds fast: even high per-step reliability collapses over long chains. The practical implication is twofold: (1) design agents to be short — one well-designed tool call beats five mediocre ones chained together, and (2) evaluate trajectory, not just final output. Since you can't pre-define the path a non-deterministic agent will take, you evaluate whether each step's tool selection and reasoning were sensible given what the agent knew at that point. Hamel Husain's [eval framework](https://hamel.dev/blog/posts/evals/) is the field consensus on how to do this — start by logging everything and reviewing traces manually before automating with LLM-as-judge.

**Context Rot**
Agents with 100+ turns degrade between 50k-150k tokens regardless of model context window. The theoretical window size is not the practical limit.

---

## 8. What's Coming

**High confidence (6-12 months):**
- MCP becomes the baseline assumption for tool connectivity
- Memory/session persistence becomes a standard harness feature
- "Bounded autonomy" patterns (graduated trust, escalation paths) get formalized
- Model routing becomes standard (expensive model for planning, cheap for execution)

**Medium confidence (12-24 months):**
- Self-improving context pipelines (ACE-style) graduate from research to production
- Current framework abstraction layers continue thinning as API capabilities improve
- MCP gateway products mature into standard infrastructure
- Durable execution (Temporal-style) becomes a default harness component

**What to watch:**
- Whether MCP's security problems get solved at the protocol level or require permanent gateway infrastructure
- How much next-generation model improvements make current harness patterns obsolete (Manus explicitly warns about this)
- Whether the multi-agent debate resolves into clearer heuristics or remains task-dependent

---

## 9. Implementation Recommendations

### Recommended Architecture: Hybrid (Custom Logic + Targeted Framework Use)

Based on the full weight of evidence across all four research domains:

**Agent execution layer: Claude Agent SDK**
- Anthropic's own production runtime, powers Claude Code
- Built-in tools, hooks for governance, MCP integration
- Multi-cloud (Bedrock, Vertex, Azure) — not locked to Anthropic API
- For simple agents: this is sufficient on its own

**If graph orchestration is needed: add LangGraph**
- Only when you hit the trip wires (durable execution, human-in-the-loop, multi-agent state)
- LangGraph for the graph layer; Claude Agent SDK for individual agent execution
- Do not adopt LangGraph preemptively — add it when complexity demands it

**Structured outputs: Pydantic AI or Instructor**
- Type-safe, validated responses
- Composable with any execution layer

**Tool connectivity: MCP standard**
- Build all new tools as MCP servers
- Use MCP gateway (Portkey or Kong) for auth, monitoring, security

**Observability: Langfuse (self-hosted)**
- Framework-agnostic, MIT license, full self-hosting
- Instrument from day zero — before writing production code
- LangGraph integration is mature via CallbackHandler

### Eval Strategy — From Day One

1. **Week 1:** Instrument with Langfuse. Capture every trace from first prototype.
2. **Week 2:** Establish cost-per-query baseline. Set hard limits (turn count, cost cap, execution timeout).
3. **Week 3:** Build Level 1 evals — unit tests with scoped assertions per feature/scenario.
4. **Week 4+:** Add Level 2 evals — LLM-as-judge validated against human ground truth.
5. **Ongoing:** Trajectory evaluation (not just final output). Red team as continuous practice, not one-time.

### Cost Management Approach

1. **Architect for prompt caching from day zero.** Static-first prompt structure. Never put timestamps in system prompts. Deterministic serialization.
2. **Set hard budget limits before first user traffic.** Max turns, max cost per conversation, execution timeout. These are circuit breakers against runaway costs.
3. **Start with a single model tier.** Only add model routing when costs exceed ~$10,000/month and you have enough data to calibrate routing thresholds.
4. **Track KV-cache hit rate as a primary metric.** Target 60%+ for multi-turn agents, 80%+ for FAQ/support agents. Langfuse surfaces `cached_tokens` per trace.
5. **Budget for eval costs.** LLM-as-judge runs at $0.01-$0.10 per sample. Factor this into infrastructure planning.

### Security Baseline

1. **MCP gateway** (Portkey or Kong) with OAuth 2.1, resource indicators, per-client consent
2. **Session tainting** — once untrusted data enters, restrict available tools for the session
3. **API-layer authorization** — LLM has zero knowledge of auth; access control at the API layer
4. **Sandboxing** for any code execution (Docker containers minimum, defense-in-depth preferred)
5. **Human-in-the-loop** for: financial transactions, production writes, external communications, permission changes, any irreversible action
6. **Audit trail** of all agent actions (non-negotiable for enterprise)
7. **PII handling** — pre-processing redaction, API-layer filtering, audit log protection

### Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Runaway cost from agent loops | High (without guardrails) | Critical | Hard limits on turns, cost, time. Implement before first user. |
| Context rot in long conversations | High | Medium | Structured context management. Compress at 50k tokens. |
| Prompt injection via tool outputs | High | High | Infrastructure-level auth. Session tainting. Don't trust model for security. |
| MCP tool poisoning | Medium | High | MCP gateway with audit. Review tool descriptions. Definition mutation alerts. |
| Framework ecosystem churn | Medium | Medium | Build behind clean interfaces. Own your prompts and context logic. |
| Model API breaking changes | Medium | Medium | Gateway layer (Portkey/LiteLLM) abstracts provider. |
| Multi-agent coordination failures | High (if attempted) | High | Default to single-agent. Use multi-agent only with heuristics above. Centralized topology always. |
| Eval debt | High (if delayed) | Critical | Build eval from day one. Not after the first production incident. |

---

## 10. Open Questions & Disagreements

### Where Experts Disagree

1. **Multi-agent as default architecture.** Anthropic demonstrates 90% improvement; Cognition says "don't build multi-agents." Our synthesis: task-dependent, with specific heuristics (parallelizable + read-dominant + low baseline + high value = multi-agent). But clean, universal thresholds don't exist yet.

2. **How much framework to adopt.** Scratch-builder advocates argue most agents need only 50-100 lines of Python. Framework advocates cite Uber and LinkedIn on LangGraph. Our synthesis: start custom, graduate at trip wires. But the trip wires come faster than custom advocates expect.

3. **LangGraph + Claude Agent SDK integration.** Both are natural choices for an Anthropic-model client, but the combination isn't widely documented in production. This is an area of execution risk.

### Where Evidence Is Thin

4. **Harness design transferability across domains.** The strongest harness evidence (can.ac, Manus) is for coding agents. Whether the same patterns transfer to customer service, document processing, or financial agents is less well-documented.

5. **MCP gateway maturity.** Portkey, Kong, and Cloudflare all have MCP gateway products, but they're all late-2025 releases. Real production battle-testing data is limited.

6. **The 70-80% quality ceiling.** 12-Factor Agents claims frameworks cap out at 70-80% quality before reverse-engineering is needed. Whether this applies to LangGraph specifically (vs. LangChain) is unclear.

7. **Fine-tuning thresholds.** When does fine-tuning a smaller model beat frontier model prompting? The Robinhood case study (8B model matching frontier quality) suggests high-volume narrow domains, but we lack clean decision criteria.

---

## 11. Sources

### Highest-Value Sources (Start Here)

| Source | Key Contribution |
|--------|-----------------|
| [blog.can.ac — "The Harness Problem" (Feb 2026)](https://blog.can.ac/2026/02/12/the-harness-problem/) | Quantitative proof: harness design = model upgrade. 10x improvement, one afternoon. |
| [Anthropic — "Building Effective Agents"](https://www.anthropic.com/research/building-effective-agents) | Official guidance: start simple, five patterns, direct API preferred |
| [Anthropic — Multi-Agent Research System](https://www.anthropic.com/engineering/multi-agent-research-system) | Primary engineering source. 90% improvement, failure modes, token economics. |
| [Manus — Context Engineering for AI Agents](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus) | Most detailed production context engineering post. KV-cache playbook. |
| [ZenML — 1,200 Production Deployments](https://www.zenml.io/blog/what-1200-production-deployments-reveal-about-llmops-in-2025) | Best empirical dataset. Slack, Manus, DoorDash, Cox Automotive case studies. |
| [Google Research — Scaling Agent Systems (Dec 2025)](https://research.google/blog/towards-a-science-of-scaling-agent-systems-when-and-why-agent-systems-work/) | Definitive multi-agent study. 180 configurations, quantitative heuristics. |
| [Cognition — "Don't Build Multi-Agents"](https://cognition.ai/blog/dont-build-multi-agents) | Best skeptical argument with specific failure examples. |
| [12-Factor Agents](https://github.com/humanlayer/12-factor-agents) | Best synthesis of what to own vs. delegate. |
| [Hamel Husain — "Your AI Product Needs Evals"](https://hamel.dev/blog/posts/evals/) | Field-tested eval framework. |
| [OWASP Agentic Top 10 (Dec 2025)](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/) | 100+ researcher consensus on agentic security risks. |
| [Braintrust — Canonical Agent Architecture](https://www.braintrust.dev/blog/agent-while-loop) | Why a while-loop + tools is the standard pattern. |

### Framework-Specific

| Source | Key Contribution |
|--------|-----------------|
| [Claude Agent SDK Official Docs](https://platform.claude.com/docs/en/agent-sdk/overview) | Anthropic's production agent runtime. |
| [Pydantic AI v1.0 Release](https://pydantic.dev/articles/pydantic-ai-v1) | Type-safe agent framework, stability commitment. |
| [LangGraph Platform GA](https://blog.langchain.com/langgraph-platform-ga/) | 400+ companies, production evidence. |
| [Langfuse for Agents (Nov 2025)](https://langfuse.com/changelog/2025-11-05-langfuse-for-agents) | Agent graph visualization, trajectory eval. |
| [Langfuse LangGraph Integration](https://langfuse.com/guides/cookbook/integration_langgraph) | Official integration cookbook. |
| [ZenML — Pydantic AI vs LangGraph](https://www.zenml.io/blog/pydantic-ai-vs-langgraph) | Head-to-head comparison. |

### Security

| Source | Key Contribution |
|--------|-----------------|
| [Simon Willison — Prompt Injection Design Patterns](https://simonwillison.net/2025/Jun/13/prompt-injection-design-patterns/) | Security patterns, "lethal trifecta." |
| [MCP Official Security Spec](https://modelcontextprotocol.io/specification/draft/basic/security_best_practices) | Four attack vectors, mandatory mitigations. |
| [Palo Alto Unit 42 — MCP Attack Vectors](https://unit42.paloaltonetworks.com/model-context-protocol-attack-vectors/) | Security research on MCP risks. |
| [Microsoft MSRC — Defending Against Indirect Prompt Injection](https://www.microsoft.com/en-us/msrc/blog/2025/07/how-microsoft-defends-against-indirect-prompt-injection-attacks) | Production-scale defense patterns. |
| [OWASP Top 10 for LLM Applications 2025](https://genai.owasp.org/resource/owasp-top-10-for-llm-applications-2025/) | Industry-standard security reference. |

### Cost & Production

| Source | Key Contribution |
|--------|-----------------|
| [Anthropic — Prompt Caching](https://www.anthropic.com/news/prompt-caching) | 90% cost reduction, official numbers. |
| [LMSYS — RouteLLM](https://lmsys.org/blog/2024-07-01-routellm/) | Research-backed model routing benchmarks. |
| [Portkey — Retries, Fallbacks, Circuit Breakers](https://portkey.ai/blog/retries-fallbacks-and-circuit-breakers-in-llm-apps/) | Proven patterns from 10B+ requests/month. |
| [Spotify — Context Engineering (Nov 2025)](https://engineering.atspotify.com/2025/11/context-engineering-background-coding-agents-part-2) | Real production context engineering data. |

### Trends & Patterns

| Source | Key Contribution |
|--------|-----------------|
| [Anthropic — 2026 Agentic Coding Trends](https://resources.anthropic.com/2026-agentic-coding-trends-report) | Survey data, case studies, industry direction. |
| [Simon Willison — Year in LLMs 2025](https://simonwillison.net/2025/Dec/31/the-year-in-llms/) | Reliable curator, specific claims. |
| [Karpathy — 2025 LLM Year in Review](https://karpathy.bearblog.dev/year-in-review-2025/) | Paradigm-level framing. |
| [MCP Anniversary (Nov 2025)](https://blog.modelcontextprotocol.io/posts/2025-11-25-first-mcp-anniversary/) | Adoption stats, protocol evolution. |

---

*This briefing was produced by a 4-agent research team across 2 rounds of investigation (80+ sources reviewed). All claims are linked to primary sources. Where experts disagree, both positions are presented with evidence. Recommendations are opinionated but justified — the engagement team should treat them as strong defaults, not mandates.*
