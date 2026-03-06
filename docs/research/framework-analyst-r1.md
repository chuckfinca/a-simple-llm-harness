# Framework Analyst Report — Round 1
*Research conducted: February 26, 2026*
*Scope: LLM agent framework ecosystem analysis for production harness implementation*

---

## Executive Summary

The LLM agent framework landscape consolidated significantly in 2025. The "framework fatigue" era (2022–2024) of dozens of overlapping tools gave way to a clearer picture with a few dominant players for distinct use cases. **The most important finding: most production teams are not using a single framework for everything — they're combining tools** (e.g., LangGraph for orchestration + Instructor for structured output + LangSmith for observability).

**Key takeaways:**
- **LangGraph is the de facto standard for complex stateful multi-step agents** in production (400+ companies, LinkedIn, Uber, Elastic confirmed users)
- **CrewAI won the enterprise non-technical buyer market** (60% Fortune 500 claim, but has real reliability problems in production)
- **Pydantic AI hit v1.0 in Sept 2025** and is gaining ground as the serious Python engineer's choice due to type safety and durability
- **OpenAI Agents SDK** is the fastest path to a working agent, but locks you into OpenAI's ecosystem
- **LangChain (classic) is effectively deprecated** — the LangChain team itself says "use LangGraph"
- **MCP (Model Context Protocol) became the universal standard** for tool/data integration in 2025 — framework-agnostic, now backed by Linux Foundation
- **Microsoft merged AutoGen + Semantic Kernel** into a single "Microsoft Agent Framework" (GA expected Q1 2026)
- **DSPy** is unique and powerful for prompt optimization but doesn't replace orchestration frameworks — it solves a different problem

---

## Framework Comparison Matrix

| Framework | Best For | Worst For | Maturity | Momentum | Model Lock-in |
|-----------|----------|-----------|----------|----------|---------------|
| **LangGraph** | Complex stateful multi-step agents, production | Simple tasks, beginners | High (GA, 70M+ downloads/mo) | Strong | None (agnostic) |
| **CrewAI** | Multi-agent role-playing, rapid MVP, demos | Reliability-critical production | Medium (independent since 2025) | Strong (enterprise sales) | None (agnostic) |
| **Pydantic AI** | Type-safe agents, durable workflows, Python devs | Complex graph orchestration | Medium-High (v1.0 Sept 2025) | Growing | None (agnostic) |
| **OpenAI Agents SDK** | Fast MVP with OpenAI models | Provider-agnostic or air-gapped | High (March 2025 GA) | Strong (within OpenAI ecosystem) | High (OpenAI) |
| **DSPy** | Automated prompt optimization, ML-heavy teams | Simple orchestration | High (Stanford-backed) | Niche but real | None |
| **Microsoft Agent Framework** | .NET/Azure enterprise, regulated industries | Python-first teams, fast iteration | Medium (RC as of late 2025) | Growing (Microsoft-backed) | High (Azure) |
| **Agno** | Performance-critical agents, low-overhead | Complex stateful workflows | Early-Medium | Growing | None |
| **Google ADK** | Gemini/Vertex-integrated apps, streaming | Non-Google infrastructure | Medium (April 2025 GA) | Growing (Google-backed) | High (Google/Gemini) |
| **LlamaIndex** | RAG-heavy agents, document workflows | General orchestration | High | Stable | None |
| **Haystack** | Enterprise RAG, modular pipelines, NLP | Rapid prototyping | High (mature, deepset-backed) | Stable | None |
| **Instructor** | Structured output extraction (single concern) | Full orchestration | High (3M+ monthly downloads) | Strong | None |
| **LangChain (classic)** | Legacy code, prototypes | New production systems | Declining | Declining (team recommends LangGraph) | None |

---

## Detailed Assessments

### LangGraph
**Philosophy:** Graph-based state machine orchestration. Explicit nodes, edges, and conditional routing. Low-level primitives that give you control over exactly how an agent thinks, acts, and reacts.

**Strengths:**
- Genuine production adoption at scale: LinkedIn, Uber, Elastic, Replit confirmed production users
- 70M+ open-source downloads per month across LangChain ecosystem
- ~400 companies using LangGraph Platform since beta launch
- Best-in-class state management and persistence across multi-step workflows
- Native support for cycles, conditionals, parallel execution
- LangSmith observability layer is mature and widely used
- Graph structure makes branching, looping, and human-in-the-loop natural
- AWS Marketplace availability (July 2025) accelerated enterprise adoption
- Lowest latency and token usage in benchmarks across comparable frameworks (recent benchmark data from Langwatch)

**Weaknesses:**
- Steep learning curve — graph + state concepts unfamiliar to many developers
- Over-engineering trap for simple sequential workflows
- Tied to LangChain ecosystem (though increasingly independent)
- LangGraph Platform (managed hosting) adds cost for teams self-hosting everything
- Debugging complex graph state can be opaque without LangSmith

**Who's using it in production:**
- **Uber**: Large-scale code migration agents, unit test generation
- **Elastic**: AI assistant orchestrating threat detection across network of agents
- **LinkedIn**: SQL Bot (NL→SQL internal assistant)
- **Replit**: Agentic IDE with human-in-the-loop

**Trajectory:** Strongest position in the market. Effectively the winner for complex production orchestration.

**Sources:**
- [Is LangGraph Used In Production?](https://blog.langchain.com/is-langgraph-used-in-production/)
- [LangGraph Platform GA](https://blog.langchain.com/langgraph-platform-ga/)
- [LangGraph AWS Marketplace](https://blog.langchain.com/aws-marketplace-july-2025-announce/)

---

### CrewAI
**Philosophy:** Role-based multi-agent coordination. You model "crews" of specialized agents (researcher, writer, editor) that collaborate to accomplish goals. High-level abstraction over agent coordination.

**Strengths:**
- Lowest barrier to entry for multi-agent demos and MVPs
- Strong enterprise sales traction: $18M Series A, 60% Fortune 500 claim, $3.2M revenue by July 2025
- 100,000+ agent executions/day (peak), 450M agents/month (platform claim)
- PwC, IBM, Capgemini, NVIDIA as named enterprise customers
- CrewAI AMP (Agent Management Platform) adds enterprise management layer
- Rapid prototyping speed — intuitive role/task abstraction
- Complete independence from LangChain (fully refactored in 2025)

**Weaknesses (critical for production):**
- **Hierarchical manager-worker architecture does not work as documented** — manager often executes tasks sequentially rather than coordinating agents, per independent analysis (Towards Data Science, Nov 2025)
- **Non-deterministic by design**: relies on LLM for most orchestration decisions, leading to unpredictable behavior
- Context window overflow causes "loops of doom" — agent crashes and crew keeps re-running it
- **Cannot write unit tests** for agent behavior — serious production reliability concern
- Debugging is painful: LLM unreliability + no clear test harness
- Performance scales poorly with complex multi-agent setups
- Python-only; teams with other stacks face barriers

**Who's using it in production:**
- DocuSign (email engagement optimization)
- Fortune 500 companies via AMP platform
- *Note: Many claimed users appear to be using CrewAI AMP (managed platform) rather than the raw framework, which may mask underlying reliability issues*

**Trajectory:** Strong enterprise sales momentum, but real production teams report friction. The managed AMP platform mitigates some issues, but raw framework reliability is a concern for engineering-led teams.

**Critical source:** [Why CrewAI's Manager-Worker Architecture Fails](https://towardsdatascience.com/why-crewais-manager-worker-architecture-fails-and-how-to-fix-it/) (Nov 2025) — specific documented failures, not just general criticism.

**Sources:**
- [CrewAI Practical Lessons Learned](https://ondrej-popelka.medium.com/crewai-practical-lessons-learned-b696baa67242)
- [AI Agents 2025: Why AutoGPT and CrewAI Still Struggle](https://dev.to/dataformathub/ai-agents-2025-why-autogpt-and-crewai-still-struggle-with-autonomy-48l0)
- [CrewAI Series A Coverage](https://pulse2.com/crewai-multi-agent-platform-raises-18-million-series-a/)

---

### Pydantic AI
**Philosophy:** Type-safe, production-grade agent framework built on the Pydantic ecosystem. Treats agents as typed programs, not conversational systems. Emphasis on durability, validation, and observability from day one.

**Strengths:**
- **v1.0 released September 4, 2025** — committed to API stability for 6+ months
- Built on battle-tested Pydantic — familiar to most Python backend engineers
- Strong type safety: guaranteed output validation at runtime
- First-class OpenTelemetry support and Pydantic Logfire integration (real-time traces, cost tracking)
- Durable execution with Temporal: agent survives API failures and application restarts
- Human-in-the-loop tool approval built in
- Amazon uses Pydantic within Bedrock for metadata filtering
- Thoughtworks Technology Radar: on the "adopt" track for teams needing structured outputs

**Weaknesses:**
- Less ergonomic than LangGraph for complex graph-based multi-step orchestration
- Smaller ecosystem than LangChain/LangGraph
- Pydantic Logfire is their observability solution — ties you somewhat to their stack
- Less enterprise-scale production adoption evidence compared to LangGraph

**Trajectory:** Rapidly gaining. The v1.0 stability commitment and durable execution story makes it compelling for engineering teams who want type safety. Strong choice for single-agent or linear-workflow scenarios.

**Sources:**
- [Pydantic AI v1 Announcement](https://pydantic.dev/articles/pydantic-ai-v1)
- [Pydantic AI Thoughtworks Radar](https://www.thoughtworks.com/en-us/radar/languages-and-frameworks/pydantic-ai)
- [Temporal + Pydantic AI](https://temporal.io/blog/build-durable-ai-agents-pydantic-ai-and-temporal)

---

### OpenAI Agents SDK
**Philosophy:** Minimalist, production-ready orchestration for OpenAI models. The production evolution of the experimental "Swarm" framework. Focuses on simplicity and fast time-to-value.

**Strengths:**
- Released March 2025 as production-ready (replacing Swarm)
- Built-in tracing and state persistence
- Clean, minimal abstractions — easy to learn
- Native handoffs between agents well-supported
- Tight integration with OpenAI tooling (assistants, function calling, structured outputs)
- Provider-agnostic via OpenAI-compatible APIs (100+ LLMs)

**Weaknesses:**
- **High vendor lock-in** — optimized for OpenAI; opinionated toward OpenAI's tooling and models
- Lacks built-in parallel execution (compared to LangGraph)
- Less control over graph-level execution flow
- Air-gapped or self-hosted scenarios are harder
- Pricing exposure: organizations locked in single-provider face leverage risk

**Trajectory:** Strong for OpenAI-committed shops. Teams that are already OpenAI-first will find this the easiest path. Teams that want model portability should look elsewhere.

**Sources:**
- [State of AI Agent Frameworks comparison](https://medium.com/@roberto.g.infante/the-state-of-ai-agent-frameworks-comparing-langgraph-openai-agent-sdk-google-adk-and-aws-d3e52a497720)
- [LangGraph vs OpenAI Agents SDK](https://ahmetkuzubasli.medium.com/langgraph-vs-openai-agents-sdk-cdd7be7ec154)

---

### DSPy
**Philosophy:** Programmatic, optimizer-first framework. Instead of writing prompts, you write *signatures* and *modules* — then let DSPy optimize the prompts automatically using your labeled examples. Solves the prompt-engineering problem, not the orchestration problem.

**Strengths:**
- **Solves a different problem than other frameworks**: automated prompt optimization
- Model-agnostic: change the underlying LLM + re-run optimizer, prompts adapt automatically
- Production results: systems matching human quality 80% of time; 50% reduction in agent-building time (reported cases)
- Thread-safe with native async support
- Stanford-backed, active research community
- Strong for ML-heavy teams with labeled datasets

**Weaknesses:**
- **Requires quality training datasets to work** — not useful without labeled examples
- Not a turnkey orchestration solution — needs to be combined with an orchestration layer
- Steep learning curve for teams used to prompt engineering
- Less useful for one-off tasks vs. repeated, optimizable workflows
- Limited production observability story compared to LangGraph

**Trajectory:** Niche but growing. Best for teams doing serious prompt optimization at scale. Not a replacement for orchestration frameworks — a complement.

**Sources:**
- [DSPy Production](https://dspy.ai/production/)
- [DSPy Fundamentals](https://www.statsig.com/perspectives/dspy-fundamentals-llm-optimization)
- [Building with DSPy and Databricks](https://lovelytics.com/building-agentic-workloads-with-dspy-mlflow-and-databricks/)

---

### Microsoft Agent Framework (formerly AutoGen + Semantic Kernel)
**Philosophy:** Enterprise-first, Azure-integrated multi-agent orchestration. Microsoft's strategic consolidation play.

**Key 2025 Development:**
- October 2025: AutoGen and Semantic Kernel entered *maintenance mode* (bug fixes only, no new features)
- Microsoft consolidated around "Microsoft Agent Framework" — convergence of both
- Release Candidate as of late 2025; GA expected Q1 2026
- 10,000+ organizations using Azure AI Foundry Agent Service

**Strengths:**
- .NET and Python support with v1.0 API stability commitment
- Native OpenTelemetry, Azure Monitor, Entra ID (critical for regulated industries)
- KPMG, BMW, Fujitsu production users
- Tight Azure DevOps, GitHub Actions, Azure Marketplace integration
- Enterprise governance features (audit trails, compliance)

**Weaknesses:**
- Heavy Azure coupling — significant vendor lock-in
- In maintenance/transition state — teams who built on AutoGen 0.2 faced breaking changes with 0.4 (sparked AG2 community fork)
- Overkill for non-Azure-native teams
- Slower iteration speed than Python-native frameworks

**AG2 (community fork of AutoGen 0.2):**
- Created by original AutoGen creators who left Microsoft
- Positions as "production-ready" with open governance
- Community-driven continuation maintaining 0.2 API compatibility

**Trajectory:** Strong for Azure enterprise. For non-Azure teams, this stack makes little sense. Watch for GA release — API stability unclear until then.

**Sources:**
- [Microsoft Agent Framework blog](https://devblogs.microsoft.com/autogen/microsofts-agentic-frameworks-autogen-and-semantic-kernel/)
- [AG2 GitHub](https://github.com/ag2ai/ag2)
- [European AI & Cloud Summit analysis](https://cloudsummit.eu/blog/microsoft-agent-framework-production-ready-convergence-autogen-semantic-kernel)

---

### Google ADK (Agent Development Kit)
**Philosophy:** Code-first, Vertex AI-integrated agent framework. Announced at Google Cloud NEXT 2025.

**Strengths:**
- Strong bidirectional audio/video streaming support (unique differentiation)
- Deployment-agnostic: local, container, or serverless (Cloud Run)
- Built-in CLI and visual Web UI for local development and debugging
- Tight Gemini/Vertex AI integration
- Support for latest Gemini 3 Pro/Flash models

**Weaknesses:**
- **Heavy Google/Gemini lock-in** — "optimized for Google AI"
- Relatively new (April 2025) — less production battle-testing than LangGraph
- Python + TypeScript only; no Java SDK yet
- Non-Google infrastructure teams gain little from ADK

**Trajectory:** Natural choice for Google Cloud shops. Limited relevance for AWS/Azure-first or cloud-agnostic architectures.

**Sources:**
- [Google ADK Introduction](https://developers.googleblog.com/en/agent-development-kit-easy-to-build-multi-agent-applications/)
- [ADK Architecture Tour](https://thenewstack.io/what-is-googles-agent-development-kit-an-architectural-tour/)

---

### Agno
**Philosophy:** Minimal, high-performance Python-native agent runtime. Optimized for speed and low memory footprint.

**Performance Claims (from their benchmarks):**
- Agent instantiation: ~2μs — allegedly 10,000× faster than LangGraph
- Memory usage: ~3.75 KiB per agent — ~50× less than LangGraph
- 529× faster instantiation than LangGraph, 57× vs Pydantic AI, 70× vs CrewAI

**Strengths:**
- Genuinely fast instantiation for high-throughput scenarios
- Model-agnostic, self-hostable
- Multi-modal support (text, images, audio, video) natively
- Good for teams who want performance without LangGraph's complexity

**Weaknesses:**
- Performance benchmarks are largely from Agno's own documentation — **treat with skepticism**
- Less ecosystem maturity than LangGraph
- Complex stateful multi-step workflows are better handled by LangGraph
- Smaller community, less production evidence

**Trajectory:** Worth watching for performance-sensitive use cases. Not a LangGraph replacement for complex workflows.

**Sources:**
- [Agno Framework](https://www.agno.com/agent-framework)
- [Agno vs LangGraph](https://www.zenml.io/blog/agno-vs-langgraph)
- [DigitalOcean Agno overview](https://www.digitalocean.com/community/conceptual-articles/agno-fast-scalable-multi-agent-framework)

---

### LlamaIndex
**Philosophy:** Originally RAG-focused, expanded into agentic orchestration. Strongest in document-heavy, knowledge-intensive workflows.

**Strengths:**
- 35% retrieval accuracy improvement in 2025 benchmarks
- Agentic Document Workflows (ADW) for end-to-end document processing
- Strong RAG pipeline maturity — best-in-class for document/knowledge work
- Distributed microservice architecture for large-scale agent systems

**Weaknesses:**
- Not the first choice for general-purpose agent orchestration
- Overkill if you don't have significant document/knowledge retrieval needs
- Agent orchestration is secondary to its RAG strengths

**Trajectory:** Stable, well-positioned for document-intensive enterprise workloads. Not a general LangGraph replacement.

**Sources:**
- [LlamaIndex Review 2025](https://sider.ai/blog/ai-tools/llamaindex-review-2025-is-it-the-best-rag-framework-for-production-ai)

---

### Haystack (deepset)
**Philosophy:** Open-source, pipeline-first AI orchestration for production. Pipeline serialization, cloud-agnostic deployment, modular components.

**Strengths:**
- Airbus, The Economist, NVIDIA, Comcast production users
- Pipeline serialization: Kubernetes-ready, cloud-agnostic
- Haystack Enterprise Platform with visual pipeline editor
- Strong NLP/RAG heritage
- MCP integration added in 2025

**Weaknesses:**
- Less suitable for purely agentic (non-pipeline) workflows
- Smaller community than LangChain ecosystem
- Slower cadence of new agent features vs. LangGraph/CrewAI

**Trajectory:** Stable enterprise choice for pipeline-centric architectures. Strong in NLP/search use cases.

---

### Instructor
**Philosophy:** Single-concern library for structured output extraction. Not an orchestration framework — solves structured JSON extraction from LLMs.

**Strengths:**
- 3M+ monthly downloads, 11k stars
- OpenAI, Google, Microsoft, AWS use it internally
- Lightweight, composable — works alongside any orchestration framework
- 3× more reliable extraction than raw prompting
- Multi-provider support

**Weaknesses:**
- Not an orchestration framework — needs to be combined with one
- OpenAI's native structured outputs may replace it for OpenAI-only users

**Trajectory:** Strong. The de facto standard for structured extraction. Will coexist with full frameworks, not compete.

**Sources:**
- [Instructor Python](https://python.useinstructor.com/)
- [Structured Output Comparison](https://simmering.dev/blog/structured_output/)

---

## LangChain (Classic) — The Cautionary Tale

LangChain was the dominant framework from 2022–2024, but has effectively been deprecated for production use in 2025. Key failure modes:

**Concrete problems reported by engineers:**
- **Over-abstraction**: "chains", "runnables", "agents", "tools", "callbacks" — layers of abstraction obscuring what actually happens
- **Performance**: Abstractions add >1 second of latency per API call in some configurations
- **Debugging opacity**: No clear execution trace; reverse-engineering your own stack to diagnose issues
- **Architectural lock-in**: Heavy dependency graph inflates container size; expensive to migrate away
- **Memory waste**: Default memory setups store far more conversation history than needed — unnecessary token spending
- **Breaking changes**: Frequent, documented in numerous migration post-mortems

**HN "Why we no longer use LangChain" thread (HN #40739982):**
> "The second you need to do something a little original you have to go through 5 layers of abstraction just to change a minute detail."
> Most engineers who left LangChain moved to **native API calls directly** (OpenAI/Anthropic Python SDK), not to a competing framework. The lesson: LangChain replaced problems with bigger problems.

**What LangChain team says:** "Use LangGraph for agents, not LangChain." The team pivoted away from LangChain as the primary product.

**Sources:**
- [Why LangChain technically sucks](https://medium.com/@s.sebastianmanassero/why-langchain-technically-sucks-569b25d3687f)
- [HN: Why we no longer use LangChain](https://news.ycombinator.com/item?id=40739982)
- [LangChain Dilemma engineering perspective](https://medium.com/@neeldevenshah/the-langchain-dilemma-an-ai-engineers-perspective-on-production-readiness-bc21dd61de34)

---

## Framework Anti-Patterns Found

### 1. The LangChain Abstraction Trap
**Pattern:** Using a framework's high-level abstractions for simple tasks → framework fights you when you deviate.
**Evidence:** HN thread, multiple engineering post-mortems. "Go through 5 layers of abstraction to change a minute detail."
**Mitigation:** Start with native API calls. Only introduce framework abstractions for workflows that genuinely need them.

### 2. CrewAI Demo-to-Production Gap
**Pattern:** Multi-agent framework demos beautifully but delivers non-deterministic results in production.
**Evidence:** CrewAI's manager-worker architecture "does not function as documented" (TDS Nov 2025). Context window overflow loops, inability to write unit tests.
**Mitigation:** If using CrewAI, run it through the managed AMP platform rather than raw framework. Or use LangGraph for reliability-critical flows.

### 3. Single-Provider Lock-In
**Pattern:** Choosing OpenAI Agents SDK or Google ADK for speed → expensive migration when provider raises prices or you need model portability.
**Evidence:** Multiple teams in 2025 spent weeks on emergency migrations when OpenAI/Google changed pricing. Provider-agnostic teams adapted in hours.
**Mitigation:** Use model-agnostic frameworks (LangGraph, Pydantic AI, Agno) even if you only use one provider today. Abstract the model call.

### 4. Microsoft Platform Churn
**Pattern:** AutoGen 0.2 → AutoGen 0.4 breaking changes → community fork (AG2) → merger with Semantic Kernel → new Microsoft Agent Framework. Instability cycle.
**Evidence:** AG2 fork was created specifically to escape AutoGen 0.4 breaking changes. Microsoft Agent Framework still in RC as of Feb 2026.
**Mitigation:** If on Azure, use Microsoft Agent Framework only when it reaches GA. AG2 is a viable community alternative for teams wanting AutoGen 0.2 stability.

### 5. Framework for Framework's Sake
**Pattern:** Adopting a heavyweight framework when direct API calls would be simpler, faster, and more maintainable.
**Evidence:** Post-LangChain migration stories; Agno's extreme performance benchmarks vs. heavyweight frameworks.
**Mitigation:** Start with the simplest possible implementation. Introduce framework complexity only when the problem demands it.

---

## MCP as Cross-Framework Infrastructure

**Model Context Protocol (MCP)** became the universal standard in 2025, adopted by effectively every major framework. It's now the right layer for tool/data connectivity regardless of framework choice.

**Key facts:**
- Announced by Anthropic Nov 2024; by Nov 2025, became an industry standard with 97M+ monthly SDK downloads
- Adopted by: Claude, ChatGPT (March 2025), Gemini, VS Code, Cursor, Microsoft Copilot, LangChain, Haystack, Hugging Face
- 10,000+ published MCP servers covering developer tools to Fortune 500 integrations
- Donated to Linux Foundation (Agentic AI Foundation, AAIF) in December 2025 — OpenAI, AWS, Google, Microsoft as co-founders

**Implication for framework choice:** MCP reduces framework lock-in for the tool/integration layer. Regardless of which framework you choose for orchestration, tools built as MCP servers are reusable across any MCP-compatible framework.

**Security caveat:** Security researchers flagged multiple MCP issues in April 2025: prompt injection, tool permission abuse, and lookalike tool attacks. MCP is powerful but needs a security wrapper in production.

**Sources:**
- [MCP Impact 2025 Thoughtworks](https://www.thoughtworks.com/en-us/insights/blog/generative-ai/model-context-protocol-mcp-impact-2025)
- [MCP Anniversary Blog](https://blog.modelcontextprotocol.io/posts/2025-11-25-first-mcp-anniversary/)
- [MCP Enterprise Guide](https://guptadeepak.com/the-complete-guide-to-model-context-protocol-mcp-enterprise-adoption-market-trends-and-implementation-strategies/)

---

## Recommended Framework by Use Case

| Use Case | Recommended | Why | Caveats |
|----------|-------------|-----|---------|
| **Complex stateful multi-step agent** (the common production case) | **LangGraph** | Battle-tested in production (Uber, Elastic, LinkedIn), best state management, explicit control flow | Steep learning curve; add LangSmith for observability |
| **Multi-agent role-based coordination (enterprise)** | **CrewAI AMP** (managed) or **LangGraph** | CrewAI for non-engineering-led teams who want managed platform; LangGraph for engineering control | Raw CrewAI framework has documented reliability issues |
| **Single-agent, Python-first, durability matters** | **Pydantic AI** | v1.0 stability, type safety, Temporal durability, good observability | Smaller ecosystem; graph-style orchestration less natural |
| **OpenAI-committed shop, fast MVP** | **OpenAI Agents SDK** | Minimal abstractions, fast to learn, good tracing | High provider lock-in; no parallel execution |
| **Structured output extraction** | **Instructor** (or Pydantic AI) | 3M+ downloads, composable, multi-provider | Not an orchestration framework — combine with LangGraph |
| **RAG/document-heavy pipeline** | **LlamaIndex** or **Haystack** | Best RAG pipeline support, production-ready | Not general orchestration |
| **Azure/Microsoft enterprise** | **Microsoft Agent Framework** (when GA) | Governance, compliance, Azure-native | Heavy lock-in; wait for GA |
| **Prompt optimization** | **DSPy** + orchestration layer | Automated prompt tuning without manual engineering | Needs labeled examples; not orchestration |
| **High-performance, low-overhead** | **Agno** | Extremely fast instantiation, low memory | Benchmarks self-reported; less production evidence |
| **Google Cloud / Gemini** | **Google ADK** | Native Gemini integration, streaming | Heavy Google lock-in |

---

## What Teams Have Abandoned and Why

1. **LangChain classic → LangGraph/native APIs**: Too many abstractions, debugging opacity, performance issues, breaking changes. Even LangChain team says use LangGraph.

2. **AutoGen 0.2 → AG2 (fork)**: Microsoft's AutoGen 0.4 rewrote the architecture with breaking changes. Community forked AG2 to preserve the 0.2 API.

3. **CrewAI (raw framework) → CrewAI AMP or LangGraph**: Non-deterministic behavior, inability to write tests, context window loop issues.

4. **LangChain → Direct API calls**: For simpler use cases, teams found that a thin wrapper around the OpenAI/Anthropic SDK beats a heavyweight framework every time.

---

## Open Questions for Deeper Investigation

1. **Microsoft Agent Framework GA timing**: Scheduled Q1 2026 — is it actually stable enough for production now? Need engineering assessment.

2. **CrewAI enterprise claims**: "60% of Fortune 500" and "450M agents/month" are vendor claims. Are these using AMP platform (managed) or raw framework? What's the failure rate?

3. **LangGraph vs Pydantic AI at scale**: For a single-agent, linear workflow (not needing graph complexity), is LangGraph overkill? Pydantic AI may be the better choice but lacks production evidence at LangGraph's scale.

4. **Agno's performance benchmarks**: 10,000× faster than LangGraph is a suspicious claim. These are self-reported benchmarks. Independent verification needed.

5. **MCP security**: Multiple vulnerabilities flagged in April 2025. What's the current state of mitigations? Is MCP safe to use in production for sensitive data systems?

6. **DSPy + LangGraph integration**: Several teams are using DSPy for prompt optimization on top of LangGraph for orchestration. Is this the emerging production pattern?

---

## Sources (Annotated)

**Highest value:**
- [Is LangGraph Used In Production?](https://blog.langchain.com/is-langgraph-used-in-production/) — LangChain team's own data, includes Uber/Elastic/LinkedIn case studies
- [Langfuse Open-Source Framework Comparison](https://langfuse.com/blog/2025-03-19-ai-agent-comparison) — Independent comparison with concrete code examples
- [HN: Why we no longer use LangChain](https://news.ycombinator.com/item?id=40739982) — Raw practitioner criticism, unfiltered
- [Why CrewAI's Manager-Worker Architecture Fails](https://towardsdatascience.com/why-crewais-manager-worker-architecture-fails-and-how-to-fix-it/) — Specific documented failure analysis (Nov 2025)
- [Pydantic AI v1 Release](https://pydantic.dev/articles/pydantic-ai-v1) — First-party, v1.0 milestone with stability commitment
- [MCP First Anniversary](https://blog.modelcontextprotocol.io/posts/2025-11-25-first-mcp-anniversary/) — Adoption data, protocol evolution
- [Thoughtworks Technology Radar](https://www.thoughtworks.com/radar) — Independent industry signal on framework maturity

**Good context:**
- [State of AI Agent Frameworks: LangGraph, OpenAI, Google ADK, AWS](https://medium.com/@roberto.g.infante/the-state-of-ai-agent-frameworks-comparing-langgraph-openai-agent-sdk-google-adk-and-aws-d3e52a497720)
- [Microsoft AutoGen + Semantic Kernel consolidation](https://devblogs.microsoft.com/autogen/microsofts-agentic-frameworks-autogen-and-semantic-kernel/)
- [AI Agents in Production 2025: Enterprise Trends](https://cleanlab.ai/ai-agents-in-production-2025/)
- [ZenML: LangGraph Alternatives](https://www.zenml.io/blog/langgraph-alternatives)
- [Developer's Guide: MCP-Native vs Traditional Agent Frameworks](https://dev.to/hani__8725b7a/agentic-ai-frameworks-comparison-2025-mcp-agent-langgraph-ag2-pydanticai-crewai-h40)

**Skepticism flags:**
- Most CrewAI production stats are vendor-reported and likely include managed platform (AMP), not raw framework usage
- Agno's performance benchmarks are self-reported — treat with skepticism until independently verified
- "60% of Fortune 500 use CrewAI" — appears repeatedly in CrewAI's own marketing; not independently verified

---

*Total searches conducted: 15+*
*Sources reviewed: 30+*
*Confidence level: High for LangGraph/CrewAI/Pydantic AI assessments; Medium for Microsoft Agent Framework (in transition); Medium for Agno (limited independent data)*
