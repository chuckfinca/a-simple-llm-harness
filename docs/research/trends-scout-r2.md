# Trends Scout — Round 2 Findings
## Context Engineering System Design, Multi-Agent Heuristics, and MCP Security
**Date:** 2026-02-26
**Research conducted by:** Trends Scout Agent
**Responding to:** Team lead challenges from Round 1

---

## Part 1: Context Engineering at the System Design Level

### The Core Mental Model

The definitive technical framing comes from the LangGraph/LangChain team (Lance Martin, June 2025):

> "The LLM context window is like RAM serving as the model's working memory, with limited capacity to handle various sources of context, similar to how an operating system curates what fits into a CPU's RAM."

Context engineering is **operating system design for LLMs** — not prompt writing. Four operations constitute the complete design space:

| Operation | What it does | When to use |
|---|---|---|
| **Write** | Persist information outside the context window | Long-running tasks; information that will be needed later but not now |
| **Select** | Pull relevant context into the window at decision time | Each agent step; RAG retrieval; memory lookups |
| **Compress** | Summarize/trim to retain only essential tokens | Context nearing limit; old conversation turns; verbose tool outputs |
| **Isolate** | Separate concerns across agents or sandboxes | Parallel subtasks; token-heavy data (images, audio); different reasoning phases |

### Concrete Implementation Pattern: The Context Pipeline

Based on analysis of Anthropic's multi-agent research system, Manus AI, Spotify's Honk, and LangGraph's production patterns, a production context pipeline looks like this:

```
Request/Turn
    │
    ▼
[1. LOAD DURABLE STATE]
    - Always-on: CLAUDE.md, agent identity, task goals
    - Retrieved: relevant memories, prior session summaries
    - External: file system scratchpad entries, todo.md
    │
    ▼
[2. SELECT WORKING CONTEXT]
    - Current turn input
    - Relevant tool outputs (references, not full objects)
    - Recent conversation history (last N turns, not full history)
    - RAG results (filtered by relevance, not all retrieved docs)
    │
    ▼
[3. ISOLATE HEAVY OBJECTS]
    - Images, audio, large docs → stay in execution environment
    - Return values only → passed to LLM, not raw objects
    - Token-heavy tool results → summarized before entering context
    │
    ▼
[4. LLM CALL]
    - Context window = durable state + selected context + (no heavy objects)
    │
    ▼
[5. POST-TURN OPERATIONS]
    - Write new notes to scratchpad
    - Update todo.md / task state
    - Store key decisions to memory
    - COMPRESS: if context > threshold, summarize trajectory
    │
    ▼
[Repeat]
```

### What Each Production System Actually Does

**Manus AI (Yichao "Peak" Ji, July 2025):**
- Bets entirely on in-context learning over fine-tuning → ships improvements in hours not weeks
- **KV-cache hit rate is the single most important production metric** (latency + cost)
  - To maximize KV-cache hits: keep stable content (system prompt, tools) at the top of context; put volatile content (user messages, recent tool outputs) at the bottom
  - Avoid dynamically adding/removing tools mid-iteration (invalidates cache)
- **Todo.md as task recitation**: agent continuously rewrites a todo.md file → biases model attention toward global plan → mitigates "lost in the middle" goal drift
- **Error preservation**: leave failed actions in context — they implicitly update the model's beliefs and reduce repetition (counterintuitive but production-validated)
- **File system as unlimited external memory**: agent reads/writes files on demand rather than trying to hold everything in context
- **Context compaction for tools**: older tool results get summarized in-place; full result available on demand
- Rebuilt the framework 4 times; explicit warning: *"the harness built today will likely be obsolete when the next frontier model arrives"*

**Anthropic's Multi-Agent Research System (June 2025):**
- Lead agent stores plan in initial message → subagents have access to overall task context before beginning
- Subagent task descriptions must contain: objective, output format, tools and sources to use, explicit task boundaries
- Context phases: before crossing token limit → summarize completed phase → store in external memory → proceed to next phase
- Extended thinking used as a "controllable scratchpad" (not user-visible)
- Tool descriptions maintained by running Claude diagnostics on them (Claude reviews and improves its own tool descriptions → 40% latency reduction)
- Source quality heuristics embedded in prompts after discovering bias toward SEO-optimized content over authoritative sources

**Claude Code / Cursor / Windsurf:**
- Context tagged by function type: "currently edited file," "referenced dependency," "error message"
- At each turn: select which files and context elements are relevant → present in structured format → separate reasoning track from visible output
- Claude Code's auto-compact: at 95% context utilization → summarize full trajectory of user-agent interactions
- Always-loaded narrow context: CLAUDE.md rules file for persistent instructions; selective per-turn file inclusion

**LangGraph's Technical Architecture for Context:**
- Two memory scopes: **thread-scoped** (short-term, persisted via checkpointing across turns) and **cross-thread** (long-term, shared across sessions via DB)
- State objects use **Pydantic schemas with selective exposure**: some fields passed to LLM (`messages`), others held in state but not exposed (internal reasoning, cached data)
- Per-node fine-grained context control: each graph node can independently select what to pass to the LLM at that step
- Six streaming modes for observability without breaking context isolation

### The Most Important Insight That's Often Missed

From the LangChain context engineering docs:

> "The architecture distinguishes between durable state (Sessions) and per-call views (working context), allowing evolution of storage schemas and prompt formats independently."

**Separation of durable state from working context is the core design pattern.** The mistake most teams make is treating the conversation history as the primary state store — it grows unboundedly, mixes different information types, and can't be selectively retrieved. Production systems externalize state and reconstruct working context on each turn.

### Sources
- [LangChain: Context Engineering for Agents](https://blog.langchain.com/context-engineering-for-agents/)
- [Lance Martin: Context Engineering for Agents](https://rlancemartin.github.io/2025/06/23/context_engineering/)
- [Manus: Context Engineering for AI Agents](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)
- [Anthropic: How We Built Our Multi-Agent Research System](https://www.anthropic.com/engineering/multi-agent-research-system)
- [Spotify: Context Engineering, Background Coding Agents](https://engineering.atspotify.com/2025/11/context-engineering-background-coding-agents-part-2)
- [GitHub: LangChain Context Engineering Repo](https://github.com/langchain-ai/context_engineering)
- [LangChain: Context Engineering in Agents (docs)](https://docs.langchain.com/oss/python/langchain/context-engineering)

---

## Part 2: Reconciling Multi-Agent Failure Rates vs. Success Rates

### The Apparent Contradiction

- **Failure rate data** (production-engineer's finding): 41–86.7% failure rate for multi-agent systems
- **Anthropic result**: 90% performance improvement over single-agent

These are not contradictory. They measure **different things** on **different tasks**. Here's the reconciliation:

### Why the Numbers Don't Conflict

**The 41–86.7% failure rate** comes from analyzing multi-agent systems deployed on tasks that were **not well-suited for multi-agent architectures** — primarily from the UC Berkeley paper "Why Do Multi-Agent LLM Systems Fail?" (March 2025), which analyzed 5 systems (ChatDev, AG2, etc.) on software development and math tasks with sequential dependencies. The failure modes were:
- Specification/system design failures (FC1): 5 failure modes
- Inter-agent misalignment (FC2): 6 failure modes
- Task verification gaps (FC3): 3 failure modes

The key finding: **79% of problems originate from specification and coordination issues, not technical implementation.**

**Anthropic's 90% improvement** comes from tasks that are **genuinely well-suited for multi-agent**: open-ended research requiring parallel exploration across multiple domains, where token usage (= more context = better results) explains 80% of performance variance.

### The Google/MIT Definitive Research (December 2025)

"Towards a Science of Scaling Agent Systems" (Google Research + MIT) is the most rigorous empirical study on this question. 180 agent configurations, controlled evaluation:

**Key quantitative findings:**
- On **parallelizable tasks** (financial reasoning): centralized multi-agent → **+80.9%** vs. single agent
- On **sequential tasks** (planning in PlanCraft): every multi-agent variant → **-39% to -70%** vs. single agent
- Independent agents (no coordination topology): error amplification **17.2×**
- Centralized coordination: error amplification **4.4×** (still 4x above single-agent)
- **The 45% threshold**: Once a single agent hits ~45% success rate, adding agents delivers diminishing or negative returns
- Predictive model for architecture selection: R² = 0.513, correctly identifies optimal approach for **87% of unseen task configurations**

### Concrete Decision Heuristics (Not "It Depends")

Based on Google/MIT research, Cognition AI, Anthropic, and Philipp Schmid's framework — a team can use this decision tree:

**Step 1: Is the task genuinely parallelizable?**

The fundamental question: **can subtasks be completed independently without seeing each other's intermediate results?**

- **YES** (parallel) → multi-agent may help
- **NO** (sequential, each step depends on previous) → single-agent, always

**How to test parallelizability**: Can you describe each subtask's requirements completely, without referencing any other subtask's output? If yes: parallelizable. If the description includes "based on what the previous agent found..." → sequential → single-agent.

**Step 2: Is it a read task or a write task?**

- **Read-dominant** (research, synthesis, analysis across multiple sources): multi-agent applies
- **Write-dominant** (code refactoring, document editing, sequential state changes): single-agent, always

Rationale: write tasks require shared implicit decisions. Two agents editing the same codebase in parallel will make contradictory decisions (Cognition's "Flappy Bird" failure). Read tasks generate independent observations that can be merged.

**Step 3: What is the baseline single-agent success rate?**

- **Below ~45%**: Multi-agent CAN help by parallelizing attempts (diverse approaches, increased coverage)
- **Above ~45%**: Adding agents delivers diminishing returns; coordination overhead may reduce performance
- **Near 100%**: Never use multi-agent — pure cost with no benefit

**Step 4: Does the task exceed a single context window?**

- **Yes, fundamentally**: multi-agent justified for the isolation benefit alone
- **No**: strong prior toward single-agent

**Step 5: Does value justify 15× token cost?**

Multi-agent has a floor cost of approximately **15× standard chat** for equivalent tasks. Is the task worth it?
- High-value business research: likely yes
- Routine structured data extraction: almost certainly no

### Summary Decision Scorecard

| Task Property | Single-Agent Score | Multi-Agent Score |
|---|---|---|
| Sequential dependencies | +3 | -3 |
| Read-dominant | 0 | +2 |
| Write-dominant | +3 | -3 |
| Baseline >45% success | +1 | -1 |
| Fits in single context window | +2 | 0 |
| Exceeds single context window | -2 | +2 |
| Low error tolerance (irreversible actions) | +3 | -2 |
| High value, parallelizable | 0 | +3 |

**If multi-agent score > single-agent score by 3+: consider multi-agent. Otherwise: single-agent.**

### Critical Production Insight: Topology Matters More Than Agent Count

The 17× error amplification from "bag of agents" vs. 4.4× for centralized coordination is the key finding. **The coordination topology is more important than how many agents you have.** Don't add agents without designing the coordination structure:
- **Centralized** (orchestrator + workers): best for most production cases, highest reliability
- **Hierarchical** (nested orchestrators): for very complex tasks with natural sub-hierarchies
- **Decentralized/peer**: highest failure rate, avoid in production

### Sources
- [Google Research: Towards a Science of Scaling Agent Systems](https://research.google/blog/towards-a-science-of-scaling-agent-systems-when-and-why-agent-systems-work/)
- [arXiv: Why Do Multi-Agent LLM Systems Fail?](https://arxiv.org/html/2503.13657v1)
- [Towards Data Science: Escaping the 17x Error Trap of the Bag of Agents](https://towardsdatascience.com/why-your-multi-agent-system-is-failing-escaping-the-17x-error-trap-of-the-bag-of-agents/)
- [Philipp Schmid: Single vs Multi-Agents](https://www.philschmid.de/single-vs-multi-agents)
- [Getmaxim: Multi-Agent System Reliability — Failure Patterns](https://www.getmaxim.ai/articles/multi-agent-system-reliability-failure-patterns-root-causes-and-production-validation-strategies/)
- [InfoQ: Google Agent Scaling Principles (Feb 2026)](https://www.infoq.com/news/2026/02/google-agent-scaling-principles/)
- [arXiv: Predicting Multi-Agent Specialization via Task Parallelizability](https://arxiv.org/pdf/2503.15703)

---

## Part 3: MCP Security — What Hardened Production Deployment Actually Looks Like

### The State of MCP Security (Early 2026)

The good news: the security community has caught up. By early 2026, there are:
- Official MCP security specification (updated Nov 2025, with detailed attack mitigations)
- OWASP Gen AI Security Project: "A Practical Guide for Secure MCP Server Development" (Feb 2026)
- Multiple commercial gateway solutions with enterprise security (Portkey, Kong, Cloudflare, MintMCP)
- OAuth 2.1 finalized as the MCP authentication standard (June 2025 spec update)
- SlowMist MCP Security Checklist on GitHub

The bad news: **most MCP implementations in the wild still don't follow these practices.** The gap between published best practices and what teams are actually deploying is large.

### The Authentication Standard: OAuth 2.1 (Not Optional)

The June 2025 MCP specification update made OAuth 2.1 the mandatory standard for HTTP-based MCP transports. What this means in practice:

**Required implementation:**
- OAuth 2.1 with PKCE (S256 method mandatory — not optional)
- Resource Indicators (RFC 8707) to scope tokens to specific servers — prevents token reuse across servers
- Authorization Code flow for user-scoped access (personal data, private repos)
- Client Credentials flow for system-scoped access (org data, public APIs)
- Short-lived tokens (minutes to hours, never days)
- Refresh tokens encrypted at rest, never exposed to LLM contexts

**For organizations not building auth from scratch:**
- Use dedicated authorization servers: Keycloak, Auth0, Okta — not custom implementations
- Never store credentials in source code, config files, or logged environment variables
- Use dedicated secrets managers (AWS Secrets Manager, Vault, etc.)

### Four Attack Vectors from the Official Spec (Must Address All Four)

The official MCP security specification (modelcontextprotocol.io) documents four primary attack patterns with mandatory mitigations:

**1. Confused Deputy Attack**
- What happens: Malicious client registers a custom redirect_uri, exploits existing consent cookies at the OAuth proxy to steal authorization codes
- Required mitigation: Per-client consent storage (registry of approved client_ids per user), validate redirect_uri with exact string matching (no wildcards), CSRF protection on consent pages, `__Host-` cookie prefix with Secure/HttpOnly/SameSite=Lax

**2. Token Passthrough (Anti-Pattern)**
- What happens: MCP server accepts tokens from clients without validating they were issued TO the MCP server — bypasses rate limiting, audit trails, and security controls
- Required mitigation: MCP servers **MUST NOT** accept tokens not explicitly issued for them; always validate JWT signatures, expiration, audience, and scope

**3. Server-Side Request Forgery (SSRF)**
- What happens: Malicious MCP server populates OAuth metadata URLs with internal IPs (192.168.x.x, 169.254.x.x for cloud metadata) — client becomes a proxy into internal network
- Required mitigation: Enforce HTTPS for all OAuth URLs in production; block requests to private IP ranges (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16); use egress proxy (Stripe's Smokescreen or equivalent); note: don't implement IP validation manually (encoding tricks bypass custom parsers)

**4. Session Hijacking**
- What happens: Attacker guesses/obtains session ID, impersonates user; especially dangerous in multi-server setups with shared queues
- Required mitigation: MCP servers MUST NOT use sessions for authentication; use cryptographically secure random session IDs; bind session IDs to user-specific information (key format: `<user_id>:<session_id>`); short expiration and rotation

### Prompt Injection / Tool Poisoning (The Hardest Problem)

This is the category with **no clean solution yet**. The attacks:
- Tool descriptions contain hidden instructions that hijack agent behavior
- Indirect injection: malicious content in retrieved data (GitHub issues, web pages) carries instructions
- Tool output poisoning: server returns malicious content designed to modify subsequent behavior

**Current best practices (incomplete but better than nothing):**
- **Scope minimization**: Start with minimal scopes (mcp:tools-basic); require explicit elevation for privileged operations; never expose all scopes upfront
- **Input/output validation**: Validate all JSON-RPC requests against schema; reject malformed inputs; sanitize all tool outputs before inserting into LLM context
- **Trust boundaries**: Separate what tools can be called from untrustworthy content (Simon Willison's "lethal trifecta": private data + external communication + untrusted content = critical risk)
- **Human-in-the-loop for state-changing operations**: Any tool that can change state triggered by untrustworthy input requires explicit human approval

**What we don't have yet**: A reliable automated defense against prompt injection in LLM contexts. The model itself can be fooled. Defense must be at the architectural level (restricting what actions are callable from untrustworthy contexts), not just at the model level.

### The Gateway Pattern: Production Security Architecture

The emerging standard for production MCP deployments is a **centralized MCP gateway** rather than direct server connections. Three major players:

**Portkey MCP Gateway:**
- Centralizes authentication, access control, and observability for all MCP servers
- No changes required to agents or MCP servers
- SOC 2 compliant; deployable as SaaS, private cloud, VPC, or self-hosted
- Enforces unified policy across all client-server interactions

**Kong Enterprise MCP Gateway (v3.12, Oct 2025):**
- OAuth 2.1 implementation positions Kong as the OAuth Resource Server
- Secures all MCP servers simultaneously via centralized OAuth plugin
- Rate limiting, request validation, traffic monitoring at gateway level
- LLM-as-a-Judge validation for output quality

**Cloudflare MCP Server Portals:**
- Single centralized gateway for all MCP servers
- Direct Cloudflare One integration for zero-trust access
- Routes all MCP traffic through Cloudflare's network for centralized policy enforcement

**What the gateway pattern solves:**
- Centralized auth enforcement — no per-server implementation required
- Unified audit trail (critical for enterprise/regulated use)
- Sequence-aware authorization: can detect and block chains of individually-allowed calls that together exceed permitted scope
- Rate limiting and monitoring at the protocol level

**What it doesn't solve:**
- Prompt injection from content retrieved through MCP tools
- Tool poisoning embedded in tool descriptions
- The fundamental trust model weakness in MCP itself

### The Security Checklist (What a Hardened MCP Deployment Looks Like)

Based on OWASP Gen AI Security Project guide (Feb 2026), MCP official security spec, SlowMist checklist, and GitGuardian's OAuth analysis:

**Transport Security:**
- [ ] HTTPS required for all remote connections (no exceptions in production)
- [ ] mTLS for sensitive server-to-server connections
- [ ] SSRF mitigation: egress proxy blocking private IP ranges

**Authentication:**
- [ ] OAuth 2.1 with PKCE (S256) for HTTP transport
- [ ] Resource Indicators (RFC 8707) — scope tokens to specific servers
- [ ] Per-client consent registry
- [ ] Exact redirect_uri matching (no wildcards)
- [ ] Short-lived tokens (hours, not days)
- [ ] Credentials in secrets manager, not env vars

**Authorization:**
- [ ] Least-privilege scopes (start with mcp:tools-basic)
- [ ] Incremental elevation only
- [ ] Token passthrough explicitly forbidden
- [ ] Server-side scope validation (don't trust client-claimed scopes)

**Input/Output:**
- [ ] JSON-RPC schema validation for all incoming requests
- [ ] Reject malformed inputs/unrecognized parameters
- [ ] Sanitize tool outputs before insertion into LLM context
- [ ] State-changing operations gated on human approval for untrustworthy content contexts

**Session Management:**
- [ ] Cryptographically secure session IDs (CSPRNG)
- [ ] Session IDs bound to user identity (`<user_id>:<session_id>`)
- [ ] Sessions not used for authentication
- [ ] Short expiration + rotation

**Monitoring:**
- [ ] All MCP events logged to central SIEM
- [ ] Alerts for unusual tool invocation patterns
- [ ] Audit trails for all state-changing operations
- [ ] Correlation IDs for scope elevation events

**Local MCP Servers:**
- [ ] Consent dialog showing exact command before execution (no truncation)
- [ ] Sandboxed execution with minimal default privileges
- [ ] Use stdio transport to limit access scope
- [ ] Require authorization token even for localhost HTTP servers

### Sources
- [MCP Official Security Best Practices](https://modelcontextprotocol.io/specification/draft/basic/security_best_practices)
- [GitGuardian: OAuth for MCP — Emerging Enterprise Patterns](https://blog.gitguardian.com/oauth-for-mcp-emerging-enterprise-patterns-for-agent-authorization/)
- [Kong: Enterprise MCP Gateway](https://konghq.com/blog/product-releases/enterprise-mcp-gateway)
- [Portkey: MCP Gateway](https://portkey.ai/features/mcp)
- [Cloudflare: Zero Trust MCP Server Portals](https://blog.cloudflare.com/zero-trust-mcp-server-portals/)
- [Security Boulevard: MCP Security Risks and Best Practices (Feb 2026)](https://securityboulevard.com/2026/02/mcp-security-risks-and-best-practices-explained/)
- [Auth0: MCP Specs Update — All About Auth (June 2025)](https://auth0.com/blog/mcp-specs-update-all-about-auth/)
- [Simon Willison: Prompt Injection Design Patterns](https://simonwillison.net/2025/Jun/13/prompt-injection-design-patterns/)
- [SlowMist: MCP Security Checklist (GitHub)](https://github.com/slowmist/MCP-Security-Checklist)
- [MCP Official Authorization Spec (Nov 2025)](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization)

---

## Synthesis: Answers to Team Lead Challenges

### Challenge 1: What does a production context pipeline ACTUALLY look like?

**Answer**: The write/select/compress/isolate framework is real but underspecified in most blog posts. The key technical insight is: **separate durable state from working context.** Externalize state (file system, database, scratchpad), reconstruct working context at each turn by selecting only what's relevant. KV-cache preservation requires stable content at top of context, volatile content at bottom. The most production-validated pattern: Manus's approach of treating the file system as unlimited external memory + continuous todo.md task recitation for goal preservation.

### Challenge 2: Reconcile 41–86.7% failure rate vs. 90% improvement

**Answer**: Not contradictory — different tasks, different measurement. The failure rate data comes from sequential, write-dominant tasks (code generation, math). The 90% improvement comes from parallel, read-dominant tasks (research). The Google/MIT study (180 configurations) provides the quantitative resolution: sequential tasks → -39% to -70% with multi-agent; parallelizable tasks → +80.9% with centralized multi-agent. The decision heuristics above are derived from this study. The "45% threshold" and "read vs. write" distinction are the two most actionable criteria.

### Challenge 3: Is anyone doing MCP security well?

**Answer**: Yes, but mostly at the gateway/infrastructure level, not at the application level. Kong, Portkey, and Cloudflare all have production-grade secure MCP gateway solutions as of late 2025. The OAuth 2.1 spec is finalized and concrete. The OWASP guide (Feb 2026) provides the implementation checklist. **The gap**: prompt injection from tool outputs remains unsolved at the protocol level — the only defense is architectural (restrict what tools are callable from untrusted content contexts). Teams using the gateway pattern have better security posture than teams connecting directly to MCP servers.

---

*End of Round 2 Findings — Trends Scout*
