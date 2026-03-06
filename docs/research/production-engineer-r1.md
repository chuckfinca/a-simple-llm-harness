# Production Engineering for LLM Harnesses — Round 1 Research

**Date:** 2026-02-26
**Researcher:** Production Engineer Agent
**Focus:** Evaluation & Observability, Cost & Latency Engineering, Security & Trust, Reliability Patterns

---

## Executive Summary

After reviewing 1,200+ production LLM deployments and current research:

- **Infrastructure failures, not model failures, cause most production incidents.** Context explosion, tool confusion, and missing circuit breakers are the primary culprits—not model intelligence.
- **The 80/20 problem is universal:** Reaching 80% quality is quick. Pushing past 95% consumes most of development time.
- **Costs can spiral catastrophically.** A real system went from $500/month to $847,000/month—a 1,694× increase—due to an undetected agent loop. Token budget guardrails are non-negotiable.
- **Prompt injection is still an unsolved problem.** Defense works in layers, but no single defense is robust. Move safety logic to infrastructure, not prompts.
- **MCP introduces an entirely new attack surface** via tool poisoning, rug-pull attacks, and cross-server manipulation.
- **LLM-as-judge evals work but have known biases.** They must be validated against human ground truth and never used as the sole evaluation mechanism.
- **Trajectory-level evaluation** (not just final output) is now the standard for agentic systems.

---

## Domain 1: Evaluation & Observability

### 1.1 The Eval Gap — Why It's the Hardest Part

The field universally acknowledges that evaluation is the most under-invested area in LLM product development. Hamel Husain (ML engineer who has trained 2,000+ PMs and engineers at OpenAI, Anthropic, and Google) argues: **"Unsuccessful AI products share a common root cause: failing to create robust evaluation systems."**

Key principles from his work ([hamel.dev/blog/posts/evals/](https://hamel.dev/blog/posts/evals/)):

- Start with **Level 1: Unit Tests** — scoped assertions by feature and scenario, run on every code change.
- Build **Level 2: Human + LLM-as-judge** — log traces obsessively, remove all friction from looking at data. "You are doing it wrong if you aren't looking at lots of data."
- Only reach **Level 3: A/B Testing** after Levels 1 and 2 are solid.
- The evaluation pipeline doubles as a fine-tuning pipeline — build it early.

### 1.2 Agent Evaluation vs. LLM Evaluation

Standard LLM evaluation (single-turn) is inadequate for agents. Agent evaluation must assess:

- **Tool selection accuracy** — did the agent pick the right tool and construct valid parameters?
- **Trajectory coherence** — did the reasoning chain make sense across all steps?
- **Error recovery** — did the agent handle failures appropriately?
- **Goal completion** — was the final outcome correct?

**Trajectory-level evaluation** is now the accepted framework. From LangChain/LangSmith docs:
> "Final response evaluation tells you what went wrong. Trajectory evaluation tells you where it went wrong. Single step evaluation tells you why it went wrong."

Amazon's AgentCore Evaluations (2025) uses **13 pre-built evaluators** covering: correctness, helpfulness, tool selection accuracy, safety, goal success rate, and context relevance across 4 dimensions: Quality, Performance, Responsibility, and Cost.

### 1.3 LLM-as-Judge — Works, But With Known Failure Modes

LLM-as-judge has become standard for scalability (Cox Automotive's production system generates test conversations, runs them through agents, then uses independent models to score quality). However, known limitations as of 2025:

| Failure Mode | Details |
|---|---|
| Non-determinism | Same response → different scores on re-run |
| Verbosity bias | Longer responses systematically score higher |
| Self-enhancement bias | Models favor outputs similar to their own style |
| Domain expert gap | SME agreement with LLM judges: 68% (dietetics), 64% (mental health) |
| Adversarial manipulation | "Null" nonsense responses can trick GPT-4 evaluator with persuasive framing |

**Mitigation:** Validate judge alignment with human ground truth. Use pairwise comparison rather than pointwise scoring (more stable). Never rely on LLM-as-judge alone in high-stakes domains.

Source: [dl.acm.org/doi/10.1145/3708359.3712091](https://dl.acm.org/doi/10.1145/3708359.3712091), [Confident AI LLM-as-judge guide](https://www.confident-ai.com/blog/why-llm-as-a-judge-is-the-best-llm-evaluation-method)

### 1.4 Leading Observability Platforms (2025)

| Platform | Model | Best For | Open Source? |
|---|---|---|---|
| **Langfuse** | Open-source (MIT core) | Self-hosting, vendor-neutral, OpenTelemetry-native | Yes |
| **Braintrust** | SaaS | Trajectory-level scoring, unified evals + observability | No |
| **Arize Phoenix** | SaaS/OSS | Multi-agent observability, LLM benchmarks | Hybrid |
| **Datadog LLM Obs** | SaaS | Existing Datadog customers, end-to-end tracing | No |
| **Maxim AI** | SaaS | Agentic simulation, enterprise integrations | No |
| **W&B Weave** | SaaS | Teams already on W&B, experiment tracking | No |

**Key data points tracked by Braintrust per trace:**
> Duration, LLM duration, time-to-first-token, LLM calls, tool calls, errors (LLM vs. tool), prompt tokens, cached tokens, completion tokens, reasoning tokens, estimated cost.

Source: [braintrust.dev articles](https://www.braintrust.dev/articles/top-5-platforms-agent-evals-2025), [agenta.ai top observability platforms](https://agenta.ai/blog/top-llm-observability-platforms)

### 1.5 OpenTelemetry — The Emerging Standard

OpenTelemetry is developing official GenAI Semantic Conventions that standardize span attributes across frameworks:

- GenAI spans: model name, token counts, latency, tool calls, errors
- Agent-specific: task definitions, action traces, memory lookups, inter-agent communication

Datadog natively supports OTel GenAI Semantic Conventions as of 2025. The conventions are **still maturing** — agentic system conventions are in active development (Issue #2664 in the OTel semantic-conventions repo). This is an area of flux; lock-in to proprietary tracing APIs carries risk.

Source: [opentelemetry.io/blog/2025/ai-agent-observability/](https://opentelemetry.io/blog/2025/ai-agent-observability/)

### 1.6 Production Monitoring Anti-patterns

From ZenML's 1,200 production deployments analysis ([zenml.io/blog](https://www.zenml.io/blog/what-1200-production-deployments-reveal-about-llmops-in-2025)):

- **Context rot:** Agents with 100+ turns and 50+ tool calls degrade between 50k–150k tokens, regardless of theoretical model context window. Prune aggressively.
- **Tool overload:** Going from 20 tools to 50+ overlapping tools caused observable reliability degradation in multiple production systems.
- **Red teaming as continuous practice:** Cox Automotive made each security exploit a regression test. Red teaming is not a one-time pre-launch activity.

---

## Domain 2: Cost & Latency Engineering

### 2.1 The Cost Reality

LLM inference costs have fallen 10× annually, but **consumption has scaled faster**. The critical insight: **agentic systems cost 100× more than chat interfaces** because tool outputs consume "100× more tokens than user messages."

**Real production horror stories:**
- **GetOnStack:** Escalated from $127/week to $47,000/4-weeks due to an undetected infinite agent loop.
- **A PoC that scaled:** $50 monthly in PoC → $2.5 million/month in production (a 50,000× increase).
- **Worst case on record:** $500/month → $847,000/month (1,694×) from runaway loops.

Source: [zenml.io deployment analysis](https://www.zenml.io/blog/what-1200-production-deployments-reveal-about-llmops-in-2025), [Medium: Token Cost Trap](https://medium.com/@klaushofenbitzer/token-cost-trap-why-your-ai-agents-roi-breaks-at-scale-and-how-to-fix-it-4e4a9f6f5b9a)

### 2.2 Prompt Caching — The Highest-ROI Optimization

Prompt caching is the single highest-impact cost reduction technique available today:

| Metric | Impact |
|---|---|
| Cost reduction | Up to 90% on cached tokens |
| Latency reduction | Up to 85% on long prompts |
| Cache write premium | +25% one-time on first write |
| Cache read price | 10% of normal input price |
| Real example | Care Access: 86% cost cut, 3× speed improvement |

**Architecture required:** Separate static context (system prompts, tools, background knowledge) from dynamic context (user turns). Cache the static prefix. This is an architectural decision that must be made upfront.

Source: [Anthropic prompt caching announcement](https://www.anthropic.com/news/prompt-caching), [promptbuilder.cc/blog](https://promptbuilder.cc/blog/prompt-caching-token-economics-2025), [Medium: $720 → $72](https://medium.com/@labeveryday/prompt-caching-is-a-must-how-i-went-from-spending-720-to-72-monthly-on-api-costs-3086f3635d63)

### 2.3 Model Routing

**Core pattern:** Route simple requests to cheap/fast models, complex requests to powerful/expensive models. RouteLLM (LMSYS) showed: trained routers reduce costs by up to 85% while maintaining 95% GPT-4 performance.

**Production routing tiers:**
1. **Gemini Flash Lite** ($0.075/$0.30 per 1M in/out) — high-volume, low-value, low-sensitivity tasks
2. **Claude Haiku / GPT-4o-mini** — medium complexity, conversational interactions
3. **Claude Sonnet / GPT-4o** — standard production workload
4. **Claude Opus / GPT-o3** — critical reasoning, low volume, high value

**Implementation reality check:** Don't build routing if LLM costs are <$300/month. The engineering investment only pays off at significant scale.

**Calibration challenge:** Too aggressive → poor quality responses. Too conservative → over-route to expensive models. Requires ongoing monitoring.

Source: [lmsys.org RouteLLM](https://lmsys.org/blog/2024-07-01-routellm/), [logrocket.com LLM routing](https://blog.logrocket.com/llm-routing-right-model-for-requests/), [portkey.ai routing techniques](https://portkey.ai/blog/llm-routing-techniques-for-high-volume-applications/)

### 2.4 Fine-Tuning: When Smaller Models Win

**Robinhood case study:** An 8B fine-tuned model matched frontier model quality while reducing P90 latencies from 55 seconds to under 1 second — a 55× latency improvement.

**When fine-tuning beats frontier models:**
- Narrow, well-defined task domains (legal, medical, financial)
- High-volume inference where cost compounds
- Latency SLAs that frontier models cannot satisfy
- Tasks where a 1B specialized model achieves 99% accuracy vs. GPT-4

**Caution:** Fine-tuning requires high-quality labeled data, infrastructure investment, and ongoing maintenance. Don't fine-tune until you have production data proving frontier models are insufficient.

Source: [together.ai fine-tune blog](https://www.together.ai/blog/fine-tune-small-open-source-llms-outperform-closed-models), [ZenML analysis (Robinhood)](https://www.zenml.io/blog/what-1200-production-deployments-reveal-about-llmops-in-2025)

### 2.5 Token Budget Management — Mandatory Guardrails

Every production agentic system must implement:

1. **Hard turn limits** — absolute stop after N LLM calls per session (circuit breaker)
2. **Cost caps per conversation** — auto-escalate to human when budget exceeded (Cox Automotive pattern)
3. **Loop detection** — detect repetitive outputs and terminate before runaway occurs
4. **Context pruning** — summarize or drop old turns rather than growing unbounded
5. **Durable execution** — if an agent fails mid-task, resume (not restart) using Temporal/Inngest (Slack, Railway patterns)

Source: [zenml.io agent deployment gap](https://www.zenml.io/blog/the-agent-deployment-gap-why-your-llm-loop-isnt-production-ready-and-what-to-do-about-it), [fixbrokenaiapps.com loops](https://www.fixbrokenaiapps.com/blog/ai-agents-infinite-loops)

### 2.6 Latency Patterns

**Time-to-first-useful-output** is a better UX metric than end-to-end latency for agentic tasks. Strategies:

- Streaming from the first agent response
- Parallel tool calls where dependency order allows
- Background agents for non-blocking work (user doesn't wait)
- Shadow mode for validation before live processing (Ramp's approach)

---

## Domain 3: Security & Trust Boundaries

### 3.1 OWASP Top 10 for LLM Applications (2025)

The OWASP Top 10 for LLMs was updated in 2025. Key additions and changes:

- **LLM01: Prompt Injection** — still #1
- **LLM02: Sensitive Information Disclosure** — surged to #2 (42% of organizations rank PII leakage as top risk per Gartner)
- **LLM08: Excessive Agency** — significantly expanded as "2025 is the year of LLM agents"

Source: [genai.owasp.org/resource/owasp-top-10-for-llm-applications-2025/](https://genai.owasp.org/resource/owasp-top-10-for-llm-applications-2025/)

### 3.2 OWASP Top 10 for Agentic Applications (2026)

OWASP released a dedicated agentic security list in December 2025, representing 100+ researchers and practitioners:

| ID | Risk | Description |
|---|---|---|
| ASI01 | Agent Goal Hijack | Attackers redirect agent objectives via manipulated instructions/tool outputs |
| ASI02 | Tool Misuse | Agents bent legitimate tools into destructive outcomes |
| ASI03 | Identity & Privilege Abuse | Leaked credentials enable scope beyond intended access |
| ASI04 | Agentic Supply Chain Vulnerabilities | Runtime components poisoned; NL execution paths enable RCE |
| ASI05 | Unexpected Code Execution | Unintended code execution through natural language pathways |
| ASI06 | Memory & Context Poisoning | Persistent corruption of agent memory, RAG stores, or context |
| ASI07 | Insecure Inter-Agent Communication | Spoofed, manipulated, or intercepted agent-to-agent messages |
| ASI08 | Cascading Failures | Single-point faults propagate through multi-agent workflows |
| ASI09 | Human–Agent Trust Exploitation | Persuasive agents lead operators to approve unsafe actions |
| ASI10 | Rogue Agents | Compromised/misaligned agents diverge from intended behavior |

Source: [genai.owasp.org agentic top 10](https://genai.owasp.org/2025/12/09/owasp-top-10-for-agentic-applications-the-benchmark-for-agentic-security-in-the-age-of-autonomous-ai/)

### 3.3 Prompt Injection — Still Unsolved

**Direct prompt injection:** User input alters model behavior directly.
**Indirect prompt injection:** Malicious instructions embedded in retrieved content (web pages, documents, emails). **This is the primary agentic attack surface.**

Research finding (2025): **Adaptive attacks bypass all 8 tested defenses.** Despite defenses designed for indirect prompt injection, robustness "remains questionable due to insufficient testing against adaptive attacks." Researchers successfully bypassed every defense tested.

**What Microsoft does** (published 2025): Design patterns, not prompt instructions. FIDES (information-flow control) is one approach — deterministic prevention by tracking instruction provenance. But adoption is still nascent.

**The real-world number:** 82.4% of LLMs will execute malicious tool calls from "peer agents" in multi-agent systems; 41.2% for direct prompt injection. The multi-agent architecture makes this dramatically worse.

**Production-hardened defenses that work:**
1. **Session tainting** (Oso pattern): Once a session touches untrusted data, it loses access to sensitive tools for its duration. No model behavior involved — purely structural.
2. **API-layer authorization** (Komodo Health pattern): LLM has zero knowledge of auth. All access control happens at the API layer where the model cannot circumvent it.
3. **Dual-layer permissions** (Wakam pattern): Users can only invoke agents if they hold permissions for that agent's data sources.

**The core principle from ZenML analysis:**
> "Move safety logic out of prompts into infrastructure. Every new model brings new prompt injection exploits within hours."

Source: [simonwillison.net prompt injection](https://simonwillison.net/2025/Nov/2/new-prompt-injection-papers/), [microsoft.com MSRC blog](https://www.microsoft.com/en-us/msrc/blog/2025/07/how-microsoft-defends-against-indirect-prompt-injection-attacks), [arxiv 2509.14285](https://arxiv.org/abs/2509.14285)

### 3.4 MCP Security — Emergent and Alarming

The Model Context Protocol (MCP) dramatically expands the attack surface. New attack classes discovered in 2025:

**Tool Poisoning:** Malicious instructions embedded in tool descriptions visible to the LLM but not displayed to users. A tool can instruct the model to exfiltrate data while appearing to do something benign.

**Rug Pull Attacks:** Tools mutate their own definitions after installation. You approve a safe-looking tool on Day 1; by Day 7, it's quietly rerouting your API keys to an attacker.

**Cross-Server Manipulation:** With multiple MCP servers connected to one agent, a malicious server can override or intercept calls to trusted servers.

**CVE-2025-6514:** Critical OS command-injection bug in mcp-remote (a popular OAuth proxy for MCP). Disclosed by JFrog, mid-2025.

**Invariant Labs demo:** Malicious MCP server silently exfiltrated a user's entire WhatsApp history by combining tool poisoning with a legitimate whatsapp-mcp server.

**MCPTox benchmark:** Tool poisoning attacks are "alarmingly common" in MCP ecosystems.

Source: [simonwillison.net MCP injection](https://simonwillison.net/2025/Apr/9/mcp-prompt-injection/), [invariantlabs.ai](https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks), [authzed.com MCP breach timeline](https://authzed.com/blog/timeline-mcp-breaches)

### 3.5 Sandboxing — Non-Negotiable for Code Execution

For any agent that generates and executes code:

**Must-have:** Docker containers as minimum baseline. This confines the blast radius of successful injection attacks.

**Production-grade options:**
- **e2b** — Open-source secure cloud runtime using Firecracker microVMs. Built specifically for AI agent code execution.
- **gVisor** — Kernel sandboxing for Kubernetes, used in the open-source Agent Sandbox Kubernetes controller.
- **LXC** — Standard Linux containers, same isolation as Docker.

**Finding from INNOQ (2025):** Container isolation alone is insufficient for untrusted AI-generated code. Defense-in-depth combining OS primitives, hardware virtualization, AND network segmentation is "now mandatory."

**Performance cost:** Sandboxing adds ~200–500ms to execution. Since each LLM roundtrip already takes seconds, the user-visible impact is minimal and justified by the security guarantee.

Source: [innoq.com sandboxing](https://www.innoq.com/en/blog/2025/12/dev-sandbox/), [amirmalik.net code sandboxes](https://amirmalik.net/2025/03/07/code-sandboxes-for-llm-ai-agents), [infoq.com agent sandbox kubernetes](https://www.infoq.com/news/2025/12/agent-sandbox-kubernetes/)

### 3.6 Human-in-the-Loop Patterns

**When to require human approval:**
- Financial transactions above threshold values
- Production database writes or schema changes
- External communications (email, Slack, API calls to third parties)
- Actions that affect permissions or access control
- Any irreversible action with significant blast radius

**Implementation patterns:**

1. **LangGraph interrupt()** — pause graph execution, serialize state, await human approval, resume. Standard pattern in LangGraph applications.
2. **Permit.io MCP approach** — authorization-as-a-service where approval is itself an MCP tool call. Agent requests permission; human grants or denies via UI.
3. **HumanLayer / GotoHuman / Redouble AI** — specialized SaaS for AI approval workflows. Handles async approval with notification routing.

**Design principle:** Approval flows must not destroy throughput. Design for async approval with timeout handling. If human doesn't respond within N minutes, fail safe (decline the action, not proceed).

Source: [permit.io HITL blog](https://www.permit.io/blog/human-in-the-loop-for-ai-agents-best-practices-frameworks-use-cases-and-demo), [langchain.com LangGraph](https://www.langchain.com/langgraph)

### 3.7 PII and Data Privacy

**The grim finding (AgentLeak benchmark, 2026):** Every model tested leaked PII through internal channels. No model family proved immune.

**Specific agentic risk vectors:**
- Tool queries with sensitive parameters logged to third-party services
- PII persisting across multi-turn conversations beyond its intended scope
- Agent-generated logs writing PII to downstream systems without clear data boundaries
- Multi-agent pipelines where one agent's output (containing PII) becomes another's context

**Production approaches:**
- **Pre-processing redaction:** Sanitize all user inputs before they enter the LLM context window
- **API-layer PII filtering:** Use a proxy/gateway that strips PII before forwarding to model
- **Audit logging:** Log all agent actions for compliance; ensure logs themselves are appropriately protected
- **Kong PII Sanitization:** Kong's API gateway provides PII sanitization middleware specifically for LLM/agentic pipelines

Source: [arxiv AgentLeak](https://arxiv.org/html/2602.11510), [pangea.cloud PII guide](https://pangea.cloud/blog/a-developers-guide-to-preventing-sensitive-information-disclosure/), [konghq.com PII](https://konghq.com/blog/enterprise/building-pii-sanitization-for-llms-and-agentic-ai)

---

## Domain 4: Reliability Patterns

### 4.1 What Breaks in Production (That Doesn't Break in Dev)

From multi-source analysis (ZenML, arxiv 2503.13657, ReliabilityBench):

**Failure rates:** 41–86.7% of multi-agent systems fail in production. Most breakdowns occur within hours of deployment.

**Root cause distribution:**
- ~79% of problems originate from specification and coordination issues, not implementation bugs
- Inter-agent misalignment is the single most common failure mode
- Context window violations (one agent's output exceeds another's input budget) cause silent degradation

**The compounding math:** If each step has 95% reliability, a 20-step workflow has only 36% end-to-end success rate. This mathematical reality is non-negotiable.

**Production-specific failure modes not visible in dev:**
1. **Infinite loops** — agent misinterprets termination signals; context keeps growing
2. **Repetitive responses** — same answer returned 58–59 times (observed in production)
3. **Context rot** — performance degrades gradually over long conversations; dev sessions are short
4. **Tool confusion** — works with 5 tools in dev; breaks with 25 tools in prod
5. **Auth/session complexity** — dev uses fixed credentials; prod needs per-user OAuth, session tokens, expiry handling
6. **Cost surprises** — $50 in dev; $50,000 in prod at real traffic levels

Source: [arxiv 2503.13657](https://arxiv.org/html/2503.13657v1), [zenml.io deployment gap](https://www.zenml.io/blog/the-agent-deployment-gap-why-your-llm-loop-isnt-production-ready-and-what-to-do-about-it), [arxiv ReliabilityBench](https://arxiv.org/html/2601.06112v1)

### 4.2 Reliability Architecture Patterns

**Pattern 1: Durable Execution**
Use workflow engines (Temporal, Inngest) to maintain agent state across failures. If an agent fails mid-task, it resumes from the exact checkpoint — not restarting the entire conversation. Slack and Railway use this pattern in production.

**Pattern 2: Circuit Breakers**
Via LLM gateways (Portkey, LiteLLM, etc.):
- Monitor error rate thresholds per provider/model
- Automatically remove unhealthy providers from routing
- Recover after configurable cooldown without manual intervention
- Portkey handles 10B+ requests/month with this pattern; claims 99.9999% uptime

**Pattern 3: Graceful Degradation**
Design fallback chains: expensive model → cheaper model → cached response → human handoff. Cox Automotive's production system automatically hands off to humans when the agent exceeds turn or cost thresholds.

**Pattern 4: Shadow Mode Validation**
Run agents on real production data in non-destructive mode, compare outputs to human decisions, only go live after hitting accuracy thresholds. Ramp uses this pattern for financial transaction processing.

**Pattern 5: Hard Limits**
Every agent must have: max turn count, max cost per conversation, execution timeout. These are the absolute fail-safes. Not optional.

Source: [portkey.ai reliability patterns](https://portkey.ai/blog/retries-fallbacks-and-circuit-breakers-in-llm-apps/), [ilovedevops.substack.com LLM pipelines](https://ilovedevops.substack.com/p/building-reliable-llm-pipelines-error)

### 4.3 LLM Gateway — The Missing Infrastructure Layer

Production systems consistently benefit from an LLM gateway layer sitting between application code and model providers:

**Capabilities provided:**
- Unified API across multiple providers (OpenAI, Anthropic, Google, local models)
- Automatic retry with exponential backoff (default: 429, 500, 502, 503, 504)
- Fallback chains across providers
- Circuit breakers with configurable thresholds
- Cost tracking and budget enforcement
- PII redaction middleware
- Semantic caching

**Leading gateways (2025):**
- **Portkey** — most production-proven, 10B+ monthly requests, enterprise-grade
- **LiteLLM** — open source, wide model support, popular for self-hosting
- **Helicone** — focused on observability + gateway combined
- **AWS AI Gateway / Azure APIM** — for cloud-native deployments

Source: [portkey.ai blog](https://portkey.ai/blog/what-is-an-llm-gateway/), [helicone.ai gateway comparison](https://www.helicone.ai/blog/top-llm-gateways-comparison-2025)

---

## Key Findings & Gaps for Round 2

### High Confidence Findings

1. **Prompt caching is the #1 quick-win optimization.** Implement from day one with proper static/dynamic context separation.
2. **Hard limits (turn count, cost cap) are non-negotiable.** The production horror stories all involve runaway loops without hard stops.
3. **Trajectory evaluation is the right eval paradigm for agents.** Final-answer eval alone is insufficient.
4. **Move security to infrastructure, not prompts.** Session tainting, API-layer auth, dual-layer permissions work. Prompt-based defenses don't.
5. **MCP significantly expands the attack surface.** Any harness using MCP needs strict controls on server installation and definition mutation alerts.

### Moderate Confidence (Needs Validation)

6. **Model routing pays off at scale, not at small volumes.** The threshold appears to be >10,000 requests/day where routing engineering cost amortizes.
7. **Durable execution (Temporal/Inngest) is becoming standard for production agents.** Worth investigating whether lighter-weight patterns suffice for simpler use cases.

### Areas Needing Deeper Research for Round 2

1. **Cost benchmarks by architecture type** — what does a simple RAG agent cost vs. a multi-agent orchestration at comparable task complexity?
2. **Eval tooling maturity comparison** — head-to-head between Langfuse, Braintrust, and Arize for agentic trace evaluation. Which has the best agent trajectory support?
3. **MCP security controls in practice** — are any production teams using MCP at scale with adequate security? What does that look like?
4. **When does fine-tuning actually make sense** — what's the data threshold, task clarity threshold, and volume threshold for fine-tuning to pay off vs. prompt engineering?

---

## Sources

### Primary Sources (High Reliability)

1. [ZenML: 1,200 Production Deployments Reveal About LLMOps in 2025](https://www.zenml.io/blog/what-1200-production-deployments-reveal-about-llmops-in-2025) — Comprehensive analysis of real production deployments. Highest-value source.
2. [Hamel Husain: Your AI Product Needs Evals](https://hamel.dev/blog/posts/evals/) — Field-tested eval framework from practitioner with 2,000+ students at leading AI companies.
3. [OWASP Top 10 for LLM Applications 2025](https://genai.owasp.org/resource/owasp-top-10-for-llm-applications-2025/) — Industry-standard security reference.
4. [OWASP Top 10 for Agentic Applications 2026](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/) — 100+ researcher consensus on agentic-specific risks.
5. [Portkey: Retries, Fallbacks, Circuit Breakers](https://portkey.ai/blog/retries-fallbacks-and-circuit-breakers-in-llm-apps/) — Proven patterns from infrastructure handling 10B+ requests/month.
6. [Simon Willison: MCP Prompt Injection](https://simonwillison.net/2025/Apr/9/mcp-prompt-injection/) — Reliable independent security researcher on MCP risks.
7. [Anthropic: Prompt Caching](https://www.anthropic.com/news/prompt-caching) — Primary source, official numbers.
8. [LMSYS: RouteLLM](https://lmsys.org/blog/2024-07-01-routellm/) — Research-backed model routing with benchmark results.
9. [Microsoft MSRC: Defending Against Indirect Prompt Injection](https://www.microsoft.com/en-us/msrc/blog/2025/07/how-microsoft-defends-against-indirect-prompt-injection-attacks) — Production-scale defense patterns from major operator.
10. [ArXiv: Why Do Multi-Agent LLM Systems Fail?](https://arxiv.org/html/2503.13657v1) — Systematic failure analysis, peer-reviewed.
11. [ArXiv: ReliabilityBench](https://arxiv.org/html/2601.06112v1) — Benchmarking agent reliability under production-like conditions.
12. [OpenTelemetry: AI Agent Observability](https://opentelemetry.io/blog/2025/ai-agent-observability/) — Emerging standard for LLM/agent tracing.
13. [Invariant Labs: MCP Tool Poisoning](https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks) — Primary disclosure of MCP tool poisoning attacks.
14. [ArXiv AgentLeak: Privacy Leakage in Multi-Agent Systems](https://arxiv.org/html/2602.11510) — February 2026 benchmark showing universal PII leakage.
15. [INNOQ: Sandboxed Coding Agents](https://www.innoq.com/en/blog/2025/12/dev-sandbox/) — Practitioner experience with container isolation for agents.
