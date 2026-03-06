# Scratch-Builder Research: Building LLM Harnesses From Scratch
**Round 1 Findings | February 2026**

---

## Executive Summary

The dominant consensus in 2025-2026 is: **build thin, import selectively, and resist over-orchestration.** Teams that shipped reliable production agents overwhelmingly started with simple while loops, purpose-built tools, and direct API calls—then added complexity only when it earned its keep. The most important variable in production is not which framework you use, but how carefully you design the harness layer (tool schemas, context management, circuit breakers). This is a craft skill frameworks cannot abstract away.

---

## Key Claims

### Claim 1: "A while loop + tools + system prompt is all most agents need"

**Evidence**: Braintrust's canonical post "The canonical agent architecture: A while loop with tools" documents that "many of the most popular and successful agents, including Claude Code and the OpenAI Agents SDK, share a common, straightforward architecture: a while loop that makes tool calls."

**Source**: [Braintrust Blog — "The canonical agent architecture"](https://www.braintrust.dev/blog/agent-while-loop) | 2025

**Confidence**: HIGH

**Caveats**: Accurate for single-agent use cases; multi-agent coordination (e.g., handoffs, escalation routing) benefits from runtime support like Temporal or LangGraph.

---

### Claim 2: "The harness matters as much as the model"

**Evidence**: A February 2026 experiment changed only the tool schema (introducing hash-based line addressing) across 16 models on 180 coding tasks:
- Grok Code Fast 1: **6.7% → 68.3% success** (10x improvement)
- Output tokens: ~20% reduction across all models
- Format choice alone swings results ±33 percentage points

**Source**: [blog.can.ac — "I Improved 15 LLMs at Coding in One Afternoon. Only the Harness Changed"](https://blog.can.ac/2026/02/12/the-harness-problem/) | Feb 2026
**HN Discussion**: [Hacker News thread](https://news.ycombinator.com/item?id=46988596) — practitioners confirm 70% of engineering time goes to recovery paths and guardrails, not inference optimization.

**Confidence**: HIGH

**Caveats**: This is for code-editing agents. Domain specificity of harness design is the whole point—it proves no generic framework can substitute for domain-appropriate tool design.

---

### Claim 3: "LangChain adds significant overhead and breaks things in production"

**Evidence**:
- LangChain's default RAG pipeline uses **2.7x more tokens** ($0.0146 manual vs $0.0388 LangChain for equivalent task)
- Memory and agent executor abstractions add **>1 second of latency per call**
- "LangChain is where good AI projects go to die" — Kieran Klaassen, co-founder of Every Inc (reported in multiple sources)
- Fintech case study: migrated from LangChain to custom orchestrator, cut latency 40%, saved ~$200k/year in GPU costs
- Frequent breaking API changes (e.g., `__call__` deprecated, migration to `invoke`)

**Sources**:
- [The Langchain Dilemma — Medium](https://medium.com/@neeldevenshah/the-langchain-dilemma-an-ai-engineers-perspective-on-production-readiness-bc21dd61de34) | 2025
- [Is LangChain becoming too complex? — GitHub Community Discussion](https://github.com/orgs/community/discussions/182015) | 2025
- [Why I'm avoiding LangChain in 2025 — Latenode Community](https://community.latenode.com/t/why-im-avoiding-langchain-in-2025/39046) | 2025

**Confidence**: HIGH for simple use cases. MEDIUM for complex workflows (LangGraph is a different product with genuine value for multi-agent graphs).

**Caveats**: LangChain's RAG abstraction for multiple vector stores (ChromaDB, Pinecone switching) is still valued by practitioners. Not all criticism applies equally.

---

### Claim 4: "Anthropic explicitly recommends starting with direct API calls"

**Evidence**: Anthropic's research post "Building Effective Agents" states: "many patterns can be implemented in a few lines of code" and warns that frameworks "create extra layers of abstraction that can obscure the underlying prompts and responses, making them harder to debug."

**Source**: [Anthropic — "Building Effective Agents"](https://www.anthropic.com/research/building-effective-agents) | 2024/2025 (foundational)

**Confidence**: HIGH — this is Anthropic's official guidance.

**Caveats**: Anthropic also ships frameworks (Claude SDK with MCP support). "Direct API first" doesn't mean "never use anything."

---

### Claim 5: "Context engineering is the most critical skill, not prompt engineering"

**Evidence**: LangChain's 2025 State of Agent Engineering report: 57% of organizations now have AI agents in production, yet 32% cite quality as top barrier—most failures traced to **poor context management, not LLM capability**. ZenML analysis of 1,200+ production deployments confirms context engineering separates production-ready teams from demo-quality teams.

**Sources**:
- [Neo4j — "Why AI Teams Are Moving From Prompt Engineering to Context Engineering"](https://neo4j.com/blog/agentic-ai/context-engineering-vs-prompt-engineering/) | 2025
- [ZenML — "What 1,200 Production Deployments Reveal About LLMOps in 2025"](https://www.zenml.io/blog/what-1200-production-deployments-reveal-about-llmops-in-2025) | 2025

**Confidence**: HIGH

---

### Claim 6: "Custom build maintenance burden is underestimated"

**Evidence**: Salesforce's analysis: "building a solution from scratch is not just an engineering project—it's a commitment to building and maintaining a complex internal platform for years to come." Day 2 operations include recursive retrieval loops, GDPR vector deletion, HNSW graph maintenance, and evolving model API changes.

**Source**: [Salesforce — "DIY-ing Your Own AI Agent? Consider the Maintenance Burden"](https://www.salesforce.com/blog/ai-agent-maintenance/) | 2025

**Confidence**: HIGH (though note Salesforce has an obvious product incentive to promote managed solutions)

**Caveats**: This is a vendor post. Independent practitioners suggest maintenance is manageable with discipline. Real risk is novel infrastructure vs. applying proven distributed systems patterns.

---

## Architecture Patterns Found

### Pattern 1: The Canonical While Loop

**Description**: System prompt + tools + transcript window + while loop. Each iteration: pass current context to LLM → receive tool call or text response → execute tool → append result to transcript → repeat until done or exit condition.

**Minimal implementation**:
```python
messages = [{"role": "user", "content": task}]
while True:
    response = client.messages.create(system=system_prompt, messages=messages, tools=tools)
    if response.stop_reason == "end_turn":
        break
    # execute tool calls, append results
    messages.extend(handle_tool_calls(response))
```

**When it works**: Single-domain agents with well-defined tools. Most production coding agents, customer service bots, data extraction pipelines.

**Source**: [Braintrust](https://www.braintrust.dev/blog/agent-while-loop), [Anthropic Cookbook](https://github.com/anthropics/anthropic-cookbook/tree/main/patterns/agents) | 2025

---

### Pattern 2: Orchestrator-Workers

**Description**: A central "thinker" LLM breaks work into subtasks and assigns to specialized worker LLMs or functions. Workers are narrow and don't need full context. Used by LinkedIn's Hiring Assistant, 11x's Alice SDR.

**When it works**: Complex tasks with distinct subtask types (e.g., web research + code writing + QA review). Enables parallelization and specialization.

**When it fails**: Over-engineering for single-domain problems. Hard to debug handoffs.

**Source**: [Anthropic — Building Effective Agents](https://www.anthropic.com/research/building-effective-agents), [ZenML database](https://www.zenml.io/blog/what-1200-production-deployments-reveal-about-llmops-in-2025) | 2025

---

### Pattern 3: Circuit Breakers + Budget Enforcement

**Description**: Every agent loop includes hard stops: max turns (e.g., 20), max cost (P95 threshold), max time. Triggered stops hand off gracefully to humans or fallback behavior.

**When it works**: Any production system. Non-negotiable.

**Evidence**: Cox Automotive uses P95 cost thresholds + 20-turn limits. DoorDash "budgets the loop" with strict step/time limits. GetOnStack learned this the hard way: $127 → $47,000/week due to missing circuit breakers.

**Source**: [ZenML LLMOps Database](https://www.zenml.io/blog/what-1200-production-deployments-reveal-about-llmops-in-2025) | 2025

---

### Pattern 4: Durable Execution for Long-Running Agents

**Description**: Use Temporal (or similar workflow engines) as the runtime layer for agents that span multiple sessions, require retry semantics, or involve human approval steps. Separates orchestration logic from business logic.

**When it works**: Long-running agentic workflows (multi-hour, multi-day tasks). Slack uses Temporal for 5,000+ monthly agentic requests with mid-task resumption on failure.

**When it overkill**: Short-lived, stateless agents that complete in a single API call session.

**Source**: [Temporal + OpenAI Agents SDK integration post](https://temporal.io/blog/announcing-openai-agents-sdk-integration), [ZenML/Slack case study](https://www.zenml.io/blog/what-1200-production-deployments-reveal-about-llmops-in-2025) | 2025

---

### Pattern 5: Layered Context Management (Anti-Context-Rot)

**Description**: Instead of an unbounded conversation transcript, maintain structured context: working memory (current task), episodic memory (what just happened), long-term knowledge (external DB/RAG), and regularly compress or summarize.

**Evidence**: Manus refactored 5 times to build layered action spaces. Context rot begins at 50k-150k tokens regardless of context window size.

**Source**: [ZenML/Manus case study](https://www.zenml.io/blog/what-1200-production-deployments-reveal-about-llmops-in-2025), [Letta Memory Blocks](https://www.letta.com/blog/memory-blocks) | 2025

---

## Success Stories

### Slack — Temporal-Backed Multi-Agent Escalation
- **What they built**: Custom multi-agent workflow on Temporal handling 5,000+ monthly agentic requests
- **What worked**: Mid-task resumption (agents survive failures without restarting), explicit escalation routing
- **Key decision**: Used Temporal as the runtime layer rather than a framework's state machine
- **Source**: [ZenML LLMOps Database — Slack case study](https://www.zenml.io/llmops-database/scaling-ai-assisted-developer-tools-and-agentic-workflows-at-scale)

### Manus — Iterative Context Architecture
- **What they built**: Refactored architecture 5 times to build layered action spaces with atomic tools and sandbox utilities
- **What worked**: Keeping function-calling spaces minimal (fewer, cleaner tools = better decisions)
- **What failed**: Early versions with too many tools caused "analysis paralysis" (the model spent time choosing, not acting)
- **Source**: [ZenML LLMOps Database — Manus case study](https://www.zenml.io/llmops-database/context-engineering-for-production-ai-agents-at-scale)

### 11x — Hierarchical Multi-Agent SDR (LangGraph)
- **What they built**: Alice, an AI Sales Development Representative, using LangGraph's hierarchical multi-agent architecture
- **What worked**: Iterated through ReAct → workflow-based → hierarchical multi-agent to achieve human-level 2% reply rates
- **Note**: This is a framework success story — evidence that LangGraph (not LangChain) adds genuine value for complex multi-step, role-based workflows
- **Source**: [ZenML LLMOps production case study](https://www.zenml.io/blog/llmops-in-production-287-more-case-studies-of-what-actually-works) | 2025

### blog.can.ac — Harness-Only Model Improvement
- **What they built**: A custom harness with hash-based line addressing for code editing agents
- **Outcome**: 10x improvement for Grok Code Fast 1 (6.7% → 68.3%), comparable to a major model upgrade — with no model change
- **Lesson**: The harness and model form a cybernetic system. Harness quality is a first-class engineering concern.
- **Source**: [blog.can.ac](https://blog.can.ac/2026/02/12/the-harness-problem/) | Feb 2026

---

## Arguments FOR Building From Scratch

1. **Control over every token**: Frameworks add overhead. Manual RAG is 2.7x cheaper in tokens than LangChain equivalent. Critical when costs scale.

2. **Debuggability**: When abstractions hide prompts and responses, bugs become opaque. Direct API calls make every interaction inspectable.

3. **Latency**: LangChain's agent executor adds >1 second per call. For latency-sensitive applications this is a hard blocker.

4. **The harness is differentiating IP**: The can.ac experiment proves harness design is where competitive advantage lives. Outsourcing this to a framework risks capping your quality ceiling.

5. **APIs have improved dramatically**: Anthropic and OpenAI native SDKs now provide tool calling, structured outputs, streaming, MCP support, built-in retry logic. The gap between "raw API" and "framework" has narrowed significantly in 2025.

6. **Most agents are simple**: If your problem has < 5 tools, no multi-agent coordination, and a short task horizon, you need 50-100 lines of Python, not a framework.

7. **Karpathy's "Bitter Lesson" for agents**: The agents that work consistently converge on similar, simple architectures. Complexity at the orchestration layer is often symptoms of unclear tool design or bad context management.

---

## Arguments AGAINST Building From Scratch

1. **Undifferentiated infrastructure**: Retry logic, exponential backoff, streaming, token budget management, structured output validation—you will build all of this. It's not hard, but it's time.

2. **Eval and observability are non-trivial**: "Getting from 80% to 95% quality takes the majority of development time." (ZenML) Building eval harnesses from scratch is a project in itself.

3. **Day 2 maintenance**: Model API changes (Anthropic and OpenAI both made breaking changes in 2025), new SDK versions, context window updates—custom wrappers need to chase all of these. Frameworks absorb some of this churn.

4. **Multi-agent state is genuinely hard**: If you need durable workflows, human-in-the-loop approval, or agent handoffs with shared memory, you'll reinvent LangGraph or Temporal. Better to use them.

5. **Framework ecosystems provide batteries**: LangGraph integrates with LangSmith (tracing). OpenAI Agents SDK has built-in tracing, handoffs, guardrails. Braintrust integrates with most major frameworks. Rolling your own means building these integrations from scratch.

6. **Team onboarding**: Custom harnesses are hard to onboard new engineers into. Frameworks enforce conventions that transfer across projects.

---

## What "From Scratch" Actually Means in Practice

"From scratch" in 2025 does NOT mean raw HTTP calls to the API. It means:

**Typically built custom:**
- System prompt design and context engineering
- Tool schemas (the core differentiating work)
- Domain-specific business logic and routing
- Circuit breakers and budget enforcement
- State/memory management strategy
- Error messages and recovery paths (the 70%)

**Typically imported even in "custom" solutions:**
- SDK (`anthropic`, `openai`) — handles auth, retries, streaming
- `instructor` or native structured outputs — for validated JSON from LLMs
- `tenacity` — exponential backoff for API rate limits
- `pydantic` — tool schema validation
- An eval/observability tool (Braintrust, Langfuse, or Helicone)
- For long-running workflows: `temporal` as execution runtime

**The "thin wrapper" middle ground (gaining adoption):**
- **OpenAI Agents SDK**: 4 primitives (Agents, Handoffs, Guardrails, Tracing). Minimal abstraction, opinionated enough to reduce boilerplate, but doesn't hide your prompts.
- **Instructor**: Pydantic-based structured output layer. Stays close to the SDK interface. "Zero-cost abstraction."
- **PydanticAI**: Framework built on Pydantic v2, strongly typed, dependency injection for tools. Gaining traction in 2025/2026.
- **SmolAgents**: Hugging Face's minimal-abstraction agent library.

---

## Common Pitfalls

1. **Infinite loops / recursive agent calls**: GetOnStack case — $127 to $47,000/week in one incident. Agent A asks Agent B, which asks Agent A. **Fix**: Always implement circuit breakers (max turns, max cost, timeout).

2. **Context rot**: Manus found context degrades between 50k-150k tokens regardless of window size. Unbounded transcript appending is a production bug. **Fix**: Structured context management with compression/summarization.

3. **Tool proliferation**: Dropbox's agents suffered "analysis paralysis" with too many retrieval tools. **Fix**: Fewer, better-defined tools. The harness can.ac post proves this directly.

4. **LLM self-assessment unreliability**: Agents declare "done" when they subjectively think so, not when objectively complete. **Fix**: Verifiable exit conditions, external evaluators, test suites.

5. **Skipping eval infrastructure**: Teams ship to production without baselines. When the model or prompts change, they have no way to detect regressions. **Fix**: Build eval from day one (not after the first production incident).

6. **Building the wrong thing at the wrong layer**: Using multi-agent orchestration for problems that a single agent + better tools would solve. **Fix**: Default to the simplest architecture, validate need for complexity empirically.

7. **Framework lock-in through accidental dependency**: Using LangChain for RAG abstraction, then discovering LangGraph's state management is tied to LangChain primitives. **Fix**: Choose your dependencies deliberately, prefer composable over monolithic.

---

## Open Questions & Areas for Deeper Investigation

1. **What's the actual production trajectory of PydanticAI vs. OpenAI Agents SDK?** Both launched in late 2024 / early 2025. Need framework-analyst teammate's view on adoption signals and maturity.

2. **How much of the "build from scratch" advocacy is survivorship bias?** The teams that blog about their custom harnesses are the ones that shipped. Teams that tried and failed to maintain custom orchestration don't publish post-mortems.

3. **Does the harness advantage hold for non-coding agents?** The can.ac result is for code editing. How much does harness design matter for, say, customer service or document extraction? Need empirical evidence.

4. **MCP's impact on the custom vs. framework question**: Anthropic's MCP is now integrated into the SDK. Does this shift the calculus? If tool definitions are standardized via MCP, does a framework's tool abstraction become less valuable?

5. **Cost of eval from scratch**: The ZenML data shows eval is where teams spend most time. What's a realistic scope for building vs. buying eval infrastructure? The production-engineer teammate should have a view here.

---

## Sources (Annotated)

| Source | Type | Date | Quality | Key Contribution |
|--------|------|------|---------|-----------------|
| [Braintrust — Canonical Agent Architecture](https://www.braintrust.dev/blog/agent-while-loop) | Engineering blog | 2025 | HIGH | Definitive case for while-loop simplicity; cites Claude Code + OAI Agents SDK as evidence |
| [blog.can.ac — Harness Problem](https://blog.can.ac/2026/02/12/the-harness-problem/) | Practitioner experiment | Feb 2026 | HIGH | Quantitative proof that harness design = model upgrade; 10x improvement in one afternoon |
| [HN Discussion of above](https://news.ycombinator.com/item?id=46988596) | Community commentary | Feb 2026 | MEDIUM | Practitioner reinforcement; note on 70% of time spent on recovery paths |
| [Anthropic — Building Effective Agents](https://www.anthropic.com/research/building-effective-agents) | Official docs | 2024/2025 | HIGH | Anthropic's official position: start simple, five patterns, direct API preferred |
| [Anthropic — Effective Harnesses for Long-Running Agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) | Engineering post | 2025 | HIGH | Specific guidance on multi-session agents: initializer pattern, progress files, feature lists |
| [ZenML — 1200 Production Deployments](https://www.zenml.io/blog/what-1200-production-deployments-reveal-about-llmops-in-2025) | Industry analysis | 2025 | HIGH | Best empirical dataset; Slack/Manus/DoorDash/Cox Automotive case studies |
| [Karpathy — 2025 LLM Year in Review](https://karpathy.bearblog.dev/year-in-review-2025/) | Expert commentary | Dec 2025 | HIGH | Paradigm-level framing; context engineering + DAG orchestration as the app layer |
| [Simon Willison — Designing Agentic Loops](https://simonwillison.net/2025/Sep/30/designing-agentic-loops/) | Practitioner post | Sep 2025 | HIGH | Shell commands as tools; sandboxing; lightweight approach advocacy |
| [Langchain Dilemma — Medium](https://medium.com/@neeldevenshah/the-langchain-dilemma-an-ai-engineers-perspective-on-production-readiness-bc21dd61de34) | Engineering perspective | 2025 | MEDIUM | Specific latency and cost measurements against LangChain |
| [OpenAI Community — Replacing LangChain](https://community.openai.com/t/thoughts-on-replacing-langchain-with-native-orchestration-and-doubling-down-openai-apis-directly/1360207) | Community discussion | 2025 | MEDIUM | Nuanced view: keep LangChain for RAG abstraction, replace for orchestration |
| [Salesforce — AI Agent Maintenance Burden](https://www.salesforce.com/blog/ai-agent-maintenance/) | Vendor blog | 2025 | LOW-MEDIUM | Real maintenance challenges; heavily biased toward managed solutions |
| [Analytics Vidhya — Frameworks vs Runtimes vs Harnesses](https://www.analyticsvidhya.com/blog/2025/12/agent-frameworks-vs-runtimes-vs-harnesses/) | Analysis | Dec 2025 | MEDIUM | Useful taxonomy of the three layers |
| [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/) | Official docs | Mar 2025 | HIGH | The "thin wrapper" reference implementation; 4 primitives approach |
| [Instructor](https://python.useinstructor.com/blog/2024/03/05/zero-cost-abstractions/) | Library docs | 2024 | MEDIUM | "Zero-cost abstractions" philosophy for structured outputs |
| [ZenML — Agent Deployment Gap](https://www.zenml.io/blog/the-agent-deployment-gap-why-your-llm-loop-isnt-production-ready-and-what-to-do-about-it) | Engineering blog | 2025 | HIGH | Specific anti-patterns for the naive while loop |
