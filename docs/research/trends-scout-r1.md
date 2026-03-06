# Trends Scout — Round 1 Findings
## Emerging Patterns & Futures in LLM Harnesses
**Date:** 2026-02-26
**Research conducted by:** Trends Scout Agent

---

## Summary of Key Claims

This report covers 8 major trend areas. Confidence levels:
- **High confidence** = multiple independent primary sources, production evidence
- **Medium confidence** = consistent reports but limited production proof
- **Speculative** = clearly labeled, single sources or early signals only

---

## Confirmed Trends (Multiple Sources, Real Adoption)

### 1. Context Engineering Replaces Prompt Engineering

**What it is:** "Context engineering" is the discipline of managing the entire information environment an LLM operates in — memory, retrieved data, tool outputs, state — not just the wording of prompts. Gartner formally declared in July 2025: "Context engineering is in, and prompt engineering is out."

**Evidence of real adoption:**
- Anthropic published a dedicated engineering post: ["Effective Context Engineering for AI Agents"](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) (2025)
- Manus AI rebuilt their agent framework **four times** until they settled on context engineering as the core discipline — and now ships improvements in hours vs. weeks
- Spotify's "Honk" project (background coding agents) explicitly credits context engineering as the key to Claude Code being their top-performing production agent for 50+ migrations
- LangChain published a dedicated post: ["Context Engineering for Agents"](https://blog.langchain.com/context-engineering-for-agents/)
- Cognition AI's "Don't Build Multi-Agents" post elevated context engineering to "the #1 job of engineers building AI agents"

**What this means for harness design:**
The harness is *not* just a prompt wrapper. It must manage:
- **Writing context** — saving state externally for later retrieval
- **Selecting context** — pulling only what's relevant per request
- **Compressing context** — summarizing or distilling old state (auto-compact, KV-cache optimization)
- **Isolating context** — keeping token-heavy objects out of the LLM context entirely

**Manus production lessons:**
- KV-cache hit rate is the **single most important metric** for production agents (latency + cost)
- Avoid dynamically adding/removing tools mid-iteration
- Use task recitation (rewrite a todo.md continuously) to fight goal drift
- Leave failed actions in context — they update the model's internal beliefs and reduce repetition
- Use the file system as "unlimited external memory"

**Sources:**
- [Anthropic: Effective Context Engineering for AI Agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [Manus: Context Engineering for AI Agents](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)
- [LangChain: Context Engineering for Agents](https://blog.langchain.com/context-engineering-for-agents/)
- [Promptingguide.ai: Context Engineering Guide](https://www.promptingguide.ai/guides/context-engineering-guide)
- [Spotify Engineering: Context Engineering, Background Coding Agents (Nov 2025)](https://engineering.atspotify.com/2025/11/context-engineering-background-coding-agents-part-2)

---

### 2. Model Context Protocol (MCP) Won — But With Real Security Caveats

**What it is:** An open protocol (launched by Anthropic, Nov 2024) for connecting AI agents to external tools, data sources, and services in a standardized way. Think "USB-C for AI tools."

**Evidence of real adoption:**
- OpenAI adopted MCP in their Agents SDK and Responses API (March 2025)
- Google DeepMind confirmed Gemini support (April 2025)
- HuggingFace, LangChain, Deepset integrated it into their frameworks
- 97 million monthly SDK downloads (Python + TypeScript)
- 5,800+ MCP servers, 300+ MCP clients as of late 2025
- Anthropic donated MCP to the Linux Foundation's "Agentic AI Foundation" in Dec 2025 — with OpenAI, Google, Microsoft, AWS, Cloudflare, Bloomberg as co-founders/supporting members
- Real deployments: Block, Bloomberg, Amazon, hundreds of Fortune 500 companies
- IDEs (Cursor, Windsurf, Replit, Sourcegraph) adopted MCP natively

**Implications for harness design:**
- MCP is now effectively the **standard interface** for tool connectivity — using it is a safer bet than proprietary tool schemas
- It separates concerns: tool definitions live in servers, not hardcoded into agent logic
- Creates a reusable tool ecosystem; your agent can consume published MCP servers

**Critical security caveats (HIGH PRIORITY for production):**
- MCP provides **minimal authentication guidance**; many implementations default to no auth at all
- **Documented attack vectors in 2025:**
  - GitHub MCP prompt injection → leaking private repo data (May 2025)
  - CVE-2025-6514: OS command injection in mcp-remote npm package (437K downloads affected)
  - WhatsApp MCP server: malicious tool poisoning → silent data exfiltration
  - "Tool Poisoning": attacker embeds malicious instructions in tool descriptions
- Simon Willison's "lethal trifecta": **private data + external communication + untrusted content = critical vulnerability**

**Sources:**
- [Pento: A Year of MCP — Review (2025)](https://www.pento.ai/blog/a-year-of-mcp-2025-review)
- [One Year of MCP: Anniversary Post](https://blog.modelcontextprotocol.io/posts/2025-11-25-first-mcp-anniversary/)
- [Practical DevSecOps: MCP Security Vulnerabilities 2026](https://www.practical-devsecops.com/mcp-security-vulnerabilities/)
- [Simon Willison: MCP Prompt Injection](https://simonwillison.net/2025/Apr/9/mcp-prompt-injection/)
- [Palo Alto Unit 42: MCP Attack Vectors](https://unit42.paloaltonetworks.com/model-context-protocol-attack-vectors/)
- [Docker: MCP Horror Stories — GitHub Prompt Injection](https://www.docker.com/blog/mcp-horror-stories-github-prompt-injection/)

---

### 3. Multi-Agent: Real But Expensive, and the Debate Is Active

**What it is:** Multiple LLM agents working together — orchestrators delegating to workers, parallel subagents, specialist agents. **Not hype — but not the default answer either.**

**The strongest empirical case (Anthropic's own system):**
Anthropic published detailed engineering notes on their multi-agent research system (June 2025):
- Orchestrator (Claude Opus 4) + Subagents (Claude Sonnet 4)
- **+90% performance improvement over single-agent Claude Opus 4** on internal evals
- Token usage explains **80% of performance variance** — more tokens = better results
- Parallel tool calling cut research time by **up to 90%** for complex queries
- **But**: Multi-agent systems use **~15× more tokens than chat interactions**
- **Failure modes observed**: spawning 50 subagents for simple queries, endless web searches, agents distracting each other with excessive updates

**The skeptic's case — Cognition AI ("Don't Build Multi-Agents", June 2025):**
Cognition (makers of Devin) argues:
- Multi-agent = fragmented decision-making + lost context
- Sub-agents can't see each other's work → contradictory decisions → compounding errors
- The "Flappy Bird" failure: subagent 1 builds Mario-style background, subagent 2 builds mismatched bird — neither reconciles
- **Recommendation**: For most tasks, use single-threaded agents with continuous context + LLM-based summarization for longer tasks

**The actual consensus emerging:**
The debate is not "multi-agent vs. single-agent" but "when does multi-agent pay off?"
- **Use multi-agent when**: tasks genuinely parallelize, exceed single-context-window limits, have distinct independent subtasks, and value justifies 15x token cost
- **Don't use multi-agent when**: tasks require shared implicit decisions, sequential context matters, or you're optimizing for cost or simplicity
- Cosine AI published a direct counter to Cognition: ["You Should Build Multi-Agents"](https://cosine.sh/blog/why-you-should-build-multi-agent-ai) — arguing the key is better context sharing protocols, not abandoning the architecture

**Token economics are the real constraint:**
- An unconstrained agent can cost $5–$8 per software task
- 3,000 employees using agents ~10x/day = **$126K/month in API fees**
- Quadratic token growth: a 10-cycle reflexion loop can cost 50× a single pass

**Sources:**
- [Anthropic: How We Built Our Multi-Agent Research System](https://www.anthropic.com/engineering/multi-agent-research-system)
- [Cognition: Don't Build Multi-Agents](https://cognition.ai/blog/dont-build-multi-agents)
- [Cosine: You Should Build Multi-Agents](https://cosine.sh/blog/why-you-should-build-multi-agent-ai)
- [Jason Liu: Why Cognition Does Not Use Multi-Agent Systems](https://jxnl.co/writing/2025/09/11/why-cognition-does-not-use-multi-agent-systems/)
- [LangChain: How and When to Build Multi-Agent Systems](https://blog.langchain.com/how-and-when-to-build-multi-agent-systems/)

---

### 4. The "Shrinking Middle" — Model Capability Improvements Are Making Frameworks Thinner

**What is going away:**
- Manual chain construction (LangChain's chains) — models now follow complex instructions natively
- Custom ReAct implementations — native tool use + reasoning is built into frontier APIs
- Complex prompt-based workarounds for multi-step reasoning — extended thinking / o1-style reasoning handles this
- Manual output parsing / coercion — structured outputs are native (OpenAI strict mode, Anthropic JSON mode)
- Custom function routing — function calling / tool use is now a first-class API feature on all major providers

**What model improvements specifically changed:**
- 1M+ token context windows (Gemini 1.5 → Gemini 3.0): Some RAG use cases with fixed corpora can be replaced with direct context stuffing
- Extended thinking / o3-style reasoning: Makes some "chain of thought" framework features obsolete
- Native structured outputs with JSON Schema enforcement: Reduces reliance on frameworks like Instructor/Pydantic-AI
- First-class tool use on all major APIs: OpenAI Agents SDK (March 2025), Anthropic tool use, Google ADK — all provide standard primitives

**Evidence:**
- BuzzFeed abandoned LangChain; direct API calls "immediately outperformed" the LangChain approach in quality and accuracy
- Octomind blog: "Why we no longer use LangChain for building our AI agents" — over-abstraction caused debugging nightmares
- GitHub Discussion on LangChain: "becoming too complex/bloated for simple RAG applications in 2025?"
- The emerging consensus hybrid: "Vanilla Python for logic/prompts + LangGraph if you need stateful orchestration + direct Vector DB SDK for retrieval"

**What remains essential (frameworks still earn their keep):**
- **Stateful workflows**: LangGraph's graph model with checkpointing is hard to replicate cheaply
- **Observability**: LangSmith / Langfuse / Braintrust — "production-grade observability that would take person-months to build"
- **Multi-agent coordination**: Frameworks like LangGraph, CrewAI still provide value for complex agentic topologies
- **Human-in-the-loop patterns**: LangGraph's interrupt + persistence model is genuinely hard to build from scratch

**Sources:**
- [Octomind: Why We No Longer Use LangChain](https://www.octomind.dev/blog/why-we-no-longer-use-langchain-for-building-our-ai-agents)
- [LangChain HN discussion](https://news.ycombinator.com/item?id=40739982)
- [GitHub: Is LangChain too complex/bloated for RAG?](https://github.com/orgs/community/discussions/182015)

---

### 5. Structured Outputs Becoming Native — Framework Abstraction Layers Shrinking

**What it is:** APIs now support guaranteed structured output (JSON with Schema enforcement), making third-party libraries for output parsing less critical.

**State of the art:**
- OpenAI "strict mode" for function calling — **always enable this for production** (official recommendation)
- Anthropic native JSON output mode
- vLLM: constrained decoding for structured outputs at inference time (open-source/self-hosted)
- Libraries like Instructor and Pydantic-AI are still valuable but less critical for basic use cases

**Three distinct tools with different use cases (often confused):**
1. **JSON mode** — hints the model to output JSON, no schema enforcement
2. **Structured outputs** — enforces a JSON Schema, guarantees valid output
3. **Function calling** — model selects a function and provides validated arguments

**Best practices confirmed:**
- Use structured outputs when your application requires machine-readable data
- Combine with enum constraints to make invalid states unrepresentable
- Don't make models fill arguments you already know — offload to code
- Combine sequential tool calls (e.g., always mark_location after query_location → put them in one function)

**Sources:**
- [Agenta: Guide to Structured Outputs and Function Calling](https://agenta.ai/blog/the-guide-to-structured-outputs-and-function-calling-with-llms)
- [OpenAI API: Function Calling](https://platform.openai.com/docs/guides/function-calling)
- [Vellum: Function Calling vs Structured Outputs vs JSON Mode](https://www.vellum.ai/blog/when-should-i-use-function-calling-structured-outputs-or-json-mode)

---

### 6. Memory and State Management — Moving Beyond Simple RAG

**What's happening:**
The field is evolving from stateless RAG → episodic memory → autonomous memory orchestration.

**Memory taxonomy (now industry-standard framing):**
- **Working memory**: current context window
- **Episodic memory**: interaction history (vector stores, databases)
- **Semantic/long-term memory**: factual knowledge base
- **Procedural memory**: learned patterns (in fine-tuning or system prompts)

**Key evolution points:**
- 2023–2024: Vector DB + RAG was the standard pattern
- 2025: "Agentic memory" — LLMs that autonomously manage their own memory (read/write/organize) using tools
- A-Mem (Feb 2025 paper): agentic memory architecture with dynamic memory operations — no static predetermined memory structure
- LangGraph + MongoDB integration for persistent long-term memory in production agents
- **"Memory as a strategic feature for 2026"** — Anthropic's 2026 Coding Trends Report flagged session persistence as a top developer pain point

**RAG vs. long context — nuanced outcome:**
- Long context (1M+ tokens) beats RAG on most benchmarks **when data fits in window**
- But: "Lost in the Middle" effect — stuffing context degrades quality at scale
- Hybrid "Self-Route" approach: model self-assesses whether retrieved context is sufficient before deciding to use long-context vs. RAG
- Enterprise RAG: 72–80% of implementations "significantly underperforming or failing" within first year (per industry reports) — not a RAG problem per se but an implementation quality problem

**Sources:**
- [A-Mem: Agentic Memory for LLM Agents (arxiv, Feb 2025)](https://arxiv.org/html/2502.12110v11)
- [Serokell: Design Patterns for Long-Term Memory in LLM Architectures](https://serokell.io/blog/design-patterns-for-long-term-memory-in-llm-powered-architectures)
- [LangGraph: Long-term Memory Concepts](https://langchain-ai.github.io/langmem/concepts/conceptual_guide/)
- [RAGFlow: From RAG to Context — 2025 Year-End Review](https://ragflow.io/blog/rag-review-2025-from-rag-to-context)

---

### 7. Agentic Coding Tools as a Window Into Production Harness Design

**Why this matters:** Cursor, Windsurf, and Claude Code are the largest-scale production deployments of LLM harnesses. What they've learned maps directly to general harness design.

**Key patterns from Anthropic's 2026 Agentic Coding Trends Report:**
- Engineers now integrate AI into ~60% of work but can "fully delegate" only 0–20% of tasks (rest requires active supervision)
- **"Engineers as orchestrators"** — the shift from writing code to coordinating AI agents is confirmed
- Rakuten engineers pointed Claude Code at a 12.5-million-line codebase — agent worked autonomously for 7 hours, hit 99.9% numerical accuracy
- Four areas flagged for immediate attention: **multi-agent coordination, scaled human oversight, extending beyond engineering, security from day one**

**The 80/15/5 pattern (production usage):**
- 80%: Autocomplete + inline edits (Cursor/Windsurf)
- 15%: Medium agent tasks (Cursor Agent / Windsurf Cascade)
- 5%: Complex multi-file tasks (Claude Code)

**Simon Willison's key observation (Dec 2025):**
"The most important trend in LLMs in 2025 was the explosive growth of coding agents... To master these tools you need to learn how to get them to prove their changes work."
→ **Conformance suites and test harnesses are the #1 practical unlock for reliable agents**

**Sources:**
- [Anthropic: 2026 Agentic Coding Trends Report](https://resources.anthropic.com/2026-agentic-coding-trends-report)
- [Tessl: 8 Trends Shaping Software Engineering in 2026](https://tessl.io/blog/8-trends-shaping-software-engineering-in-2026-according-to-anthropics-agentic-coding-report/)
- [Simon Willison: The Year in LLMs 2025](https://simonwillison.net/2025/Dec/31/the-year-in-llms/)
- [Blockchain News: Anthropic Report — Engineers Now Orchestrate AI Agents](https://blockchain.news/news/anthropic-report-engineers-orchestrate-ai-agents-2026)

---

## Emerging Patterns (Early But Promising)

### 8. Extended Thinking as a Programmable Reasoning Budget

**What it is:** Models like Claude 3.7+ and OpenAI o3 support explicit "extended thinking" — a programmable scratchpad where the model reasons before responding.

**Status:** In production use at Anthropic's own systems. The Anthropic multi-agent research system uses extended thinking as "controllable scratchpad" per their engineering blog.

**Emerging pattern:** Harnesses can programmatically control reasoning depth — allocating more compute (tokens) to harder tasks, less to routine ones. This is "elastic reasoning."

**Risk that it's hype:** The research literature in 2025 includes papers arguing that extended thinking is sometimes counterproductive ("Don't Overthink It: Preferring Shorter Thinking Chains"). Optimal reasoning depth is task-dependent and not yet well understood.

**Sources:**
- [Anthropic: Claude Think Tool](https://www.anthropic.com/engineering/claude-think-tool)
- [Arxiv: Don't Overthink It](https://arxiv.org/html/2505.17813v1)
- [Arxiv: Elastic Reasoning](https://arxiv.org/html/2505.05315v1)

---

### 9. Agentic Context Engineering (ACE) — Self-Improving Context Pipelines

**What it is:** Rather than static system prompts, agents maintain and evolve their own context playbooks through generation, reflection, and curation. The context window becomes a living document the agent improves.

**Evidence:**
- ACE paper (arxiv Oct 2025): +10.6% on agent benchmarks vs. strong baselines; matches top-ranked production agents on AppWorld while using smaller open-source model
- Manus AI production insight: bet on context engineering over training custom models — "harnesses built today will likely be obsolete when the next frontier model arrives"

**Risk:** This is still research-stage for most teams. The ACE approach requires agents to reliably self-evaluate — which is still a reliability concern in production.

**Sources:**
- [Arxiv: Agentic Context Engineering (Oct 2025)](https://arxiv.org/abs/2510.04618)
- [Manus: Context Engineering Lessons](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)

---

### 10. "Bounded Autonomy" as the Production Trust Architecture

**What it is:** Instead of full autonomy or full human oversight, production deployments are converging on **graduated trust** — automatic for low-risk/reversible actions, human-approved for high-stakes/irreversible actions.

**Evidence:**
- Google Cloud 2025 retrospective: "The shift happening in 2026 is from viewing governance as compliance overhead to recognizing it as an enabler"
- Anthropic's 2026 Coding Trends Report: engineers retain active oversight on 80–100% of delegated tasks
- 60%+ of teams cite trust, control, and failure handling as primary production constraints
- Simon Willison's "Agents Rule of Two": anything that can **change state** triggered by untrustworthy inputs is dangerous — not just external communication

**Practical pattern:**
- Define action categories: read-only vs. reversible write vs. irreversible
- Build explicit escalation paths for boundary crossings
- Audit trails of all agent actions (non-negotiable for enterprise)

**Sources:**
- [Google Cloud: Lessons from 2025 on Agents and Trust](https://cloud.google.com/transform/ai-grew-up-and-got-a-job-lessons-from-2025-on-agents-and-trust)
- [Simon Willison: Prompt Injection Design Patterns](https://simonwillison.net/2025/Jun/13/prompt-injection-design-patterns/)
- [Human-in-the-Loop Agentic AI, 2026](https://onereach.ai/blog/human-in-the-loop-agentic-ai-systems/)

---

## Things Becoming Obsolete

| What's Going Away | What's Replacing It | Timeline |
|---|---|---|
| Manual ReAct prompt patterns | Native tool use + reasoning APIs | Already happening |
| LangChain "chains" for simple workflows | Direct API calls + vanilla Python | Already happening for new projects |
| Third-party structured output libraries (basic use) | Native JSON Schema enforcement in APIs | Happening, not complete |
| Stateless RAG as default memory | Hybrid RAG + long-context + agentic memory | 1–2 years |
| Custom function routing logic | MCP standard + native tool use | Happening |
| Per-request prompt engineering as core skill | Context/system design as core skill | Already shifted |
| Framework features for multi-step reasoning workarounds | Extended thinking / o3-style built-in reasoning | Happening for frontier models |

**Important caveat:** LangChain/LangGraph itself is NOT going away — LangGraph for stateful workflows and LangSmith for observability remain valuable. What's dying is the use of LangChain's **chain abstractions** for simple single-call workflows.

---

## Practitioner Convergence Points

Independent teams are arriving at the same conclusions:

1. **Context is the core engineering challenge.** Anthropic, Manus, Spotify, Cognition — all independently name context management as the #1 problem. Nobody is saying "we need better prompts."

2. **Test harnesses unlock agent reliability.** Simon Willison, Anthropic's engineering team, and Cognition all independently point to executable test environments / conformance suites as the key reliability lever.

3. **Observability is non-negotiable and often harder than the agent itself.** LangSmith/Langfuse/Braintrust are being adopted even by teams that rejected LangChain — the evaluation tooling is considered essential.

4. **Start narrow.** Anthropic's agentic coding report, Gartner, and independent practitioners all converge: "general-purpose agents are a research problem, not a product strategy." Define a narrow task first.

5. **Hybrid model routing, not all-opus-all-the-time.** Expensive models for planning/orchestration, cheaper models for execution. Cost reduction of 60–87% reported via cascading.

6. **MCP for tool connectivity.** Even teams with reservations about specific MCP implementations are adopting the protocol for new integrations — it won the standardization race.

---

## Warnings and Pitfalls

### 1. Multi-agent complexity tax is real
Don't build multi-agent just because it's modern. The 15x token cost + coordination overhead requires genuine justification. Cognition's analysis is correct for many use cases.

### 2. MCP security is an active vulnerability surface
Do not deploy MCP-connected agents without:
- Explicit authentication on all MCP servers
- Input sanitization for all tool outputs
- Restricting which tools agents can call from untrusted content
- Regular auditing of MCP server trust chains

### 3. Framework lock-in vs. ecosystem churn
The ecosystem is still moving fast. Frameworks that were leading in early 2024 lost ground by late 2025. Build behind clean interfaces so you can swap the orchestration layer.

### 4. Enterprise RAG failure rate is high
72–80% failure rate is not a RAG architecture problem — it's an implementation quality problem. The fix is better data infrastructure, not framework changes. RAG still works when implemented well.

### 5. Over-investing in context window hacks
Long context windows don't eliminate the "lost in the middle" problem. Teams replacing RAG with naive context stuffing are seeing quality regressions. Hybrid Self-Route is the better default.

### 6. Reasoning model cost traps
Extended thinking models cost significantly more per token. Without task-appropriate routing (use o1/extended thinking only when needed), costs spiral fast.

### 7. Harnesses built for today's models may not port cleanly
Manus's explicit lesson: their harness has been rebuilt 4 times. Don't over-engineer for current model limitations — the next frontier model may make current workarounds obsolete.

---

## Predictions (Clearly Labeled as Speculative)

**High confidence (6–12 months):**
- MCP becomes the baseline assumption for tool connectivity — not using it will require justification
- Memory/session persistence becomes a standard harness feature, not an optional add-on
- "Bounded autonomy" patterns (graduated trust, escalation paths) get formalized into frameworks
- More enterprises adopt LangGraph specifically for its human-in-the-loop / checkpoint model

**Medium confidence (12–24 months):**
- Self-improving context pipelines (ACE-style) graduate from research to production patterns
- Model-routing becomes a standard harness feature — orchestrators automatically pick model tier based on task complexity
- Current framework abstraction layers continue thinning as API capabilities improve
- Early commercial deployments of self-modifying agents (agents that update their own prompts based on experience)

**Low confidence / speculative:**
- General-purpose agents that can reliably "fully delegate" >50% of engineering tasks (currently stuck at 0–20%)
- MCP evolving enough to handle its security problems without major protocol revision
- A dominant harness pattern emerging that resolves the "build vs. buy" question clearly

---

## Open Questions

1. **The multi-agent consensus problem is unresolved.** Anthropic says multi-agent works (90% improvement with their research system). Cognition says avoid it (fragmented context). The answer appears to be task-dependent, but we don't yet have clean heuristics for when to cross the multi-agent threshold.

2. **How much does model improvement make today's harness patterns obsolete?** Manus explicitly warns their harness might be obsolete with the next frontier model. This makes it hard to invest heavily in complex orchestration.

3. **MCP security — will the protocol itself be fixed, or do teams have to build their own security layers on top?** The Linux Foundation governance shift may accelerate auth standards, but timeline is unclear.

4. **Long context vs. RAG — at what corpus size does hybrid Self-Route beat pure long-context?** Research is ongoing; no clean empirical cutoff exists yet.

5. **What does "good context engineering" actually look like at a system design level?** There are many blog posts about principles but surprisingly few detailed technical patterns with benchmarked results.

---

## Sources — Annotated

**Primary / Highest Value:**
- [Anthropic: How We Built Our Multi-Agent Research System](https://www.anthropic.com/engineering/multi-agent-research-system) — Primary engineering source, specific numbers, failure modes
- [Cognition: Don't Build Multi-Agents](https://cognition.ai/blog/dont-build-multi-agents) — Best skeptical argument with specific failure examples
- [Manus: Context Engineering for AI Agents](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus) — Production lessons, very specific
- [Anthropic: 2026 Agentic Coding Trends Report](https://resources.anthropic.com/2026-agentic-coding-trends-report) — Survey data + real case studies
- [Simon Willison: Year in LLMs 2025](https://simonwillison.net/2025/Dec/31/the-year-in-llms/) — Reliable curator, specific claims
- [Simon Willison: Prompt Injection Design Patterns](https://simonwillison.net/2025/Jun/13/prompt-injection-design-patterns/) — Security patterns
- [Spotify: Context Engineering Background Coding Agents](https://engineering.atspotify.com/2025/11/context-engineering-background-coding-agents-part-2) — Real production data

**MCP:**
- [MCP Anniversary Post](https://blog.modelcontextprotocol.io/posts/2025-11-25-first-mcp-anniversary/) — Official adoption stats
- [Palo Alto: MCP Attack Vectors](https://unit42.paloaltonetworks.com/model-context-protocol-attack-vectors/) — Security research
- [Docker: MCP Prompt Injection Horror Stories](https://www.docker.com/blog/mcp-horror-stories-github-prompt-injection/)

**Framework Analysis:**
- [Octomind: Why We No Longer Use LangChain](https://www.octomind.dev/blog/why-we-no-longer-use-langchain-for-building-our-ai-agents) — Specific abandonment case
- [Jason Liu: Why Cognition Does Not Use Multi-Agent Systems](https://jxnl.co/writing/2025/09/11/why-cognition-does-not-use-multi-agent-systems/)
- [LangChain: Context Engineering for Agents](https://blog.langchain.com/context-engineering-for-agents/)

**Memory / State:**
- [A-Mem Paper](https://arxiv.org/html/2502.12110v11) — Research on agentic memory
- [RAGFlow: From RAG to Context, 2025 Review](https://ragflow.io/blog/rag-review-2025-from-rag-to-context)

**Structured Outputs:**
- [Agenta: Guide to Structured Outputs](https://agenta.ai/blog/the-guide-to-structured-outputs-and-function-calling-with-llms)
- [OpenAI: Function Calling](https://platform.openai.com/docs/guides/function-calling)

**Cost / Economics:**
- [Stevens: Hidden Economics of AI Agents](https://online.stevens.edu/blog/hidden-economics-ai-agents-token-costs-latency/)
- [Medium: Token Cost Trap](https://medium.com/@klaushofenbitzer/token-cost-trap-why-your-ai-agents-roi-breaks-at-scale-and-how-to-fix-it-4e4a9f6f5b9a)

**Trust / Production:**
- [Google Cloud: Lessons from 2025 on Agents and Trust](https://cloud.google.com/transform/ai-grew-up-and-got-a-job-lessons-from-2025-on-agents-and-trust)
- [Cleanlab: AI Agents in Production 2025](https://cleanlab.ai/ai-agents-in-production-2025/)

---

*End of Round 1 Findings — Trends Scout*
