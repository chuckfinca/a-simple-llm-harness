# Code Mode / Code-as-Tool-Use: 2026 Landscape

**Date:** 2026-03-14
**Sources:** Trends scout, scratch builder, and production engineer research agents

## Summary

Code-as-tool-use (aka "Code Mode") has moved from experimental to production-grade
in early 2026. The pattern is converging across multiple independent teams but is
NOT a wholesale replacement for structured tool calls — the consensus is a hybrid
approach. This document captures the 2026 state of the art.

## Key Findings

### 1. Code Mode Is Now Production-Grade

- Anthropic: PTC reached GA with Sonnet 4.6 (Feb 17, 2026)
- Cloudflare: Code Mode in production for 2,500 API endpoints — 99.9% token reduction
- Letta: PTC at the harness layer, works with ANY LLM (not just Anthropic)
- Pydantic AI: Active PR (#4153) for native Code Mode support
- UTCP: Open-source plug-and-play Code Mode library (TypeScript + Python)
- Block/Goose v1.17.0: Code Mode via embedded JavaScript engine (no Docker needed)

### 2. The "Two Tools" Pattern Is Converging

Multiple independent teams arrived at: collapse N tools into exactly two:
- `search` — discover available operations
- `execute` — run code that calls them

Cloudflare, Meta-MCP, UTCP, and open-ptc-agent all converged here independently.
Achieves 88-99.9% token reduction. Best for large tool catalogs (50+ tools).
For small tool sets (<10) it adds unnecessary indirection.

### 3. The Harness Matters More Than the Model

Can Boluk (Feb 2026): Changed only the harness, improved 15 LLMs by 5-14 points.
One model: 6.7% → 68.3% (10x improvement). Anthropic, Fowler, and LangChain all
published the same conclusion: the competitive moat is the orchestration layer.

Source: https://blog.can.ac/2026/02/12/the-harness-problem/

### 4. Hybrid Is Winning Over Pure Approaches

Every production implementation supports BOTH structured tool calls and code
execution simultaneously. Anthropic's `allowed_callers` field configures per-tool.
Simple single-step tools stay as direct calls; chaining, batch processing, and
data filtering use code execution. Nobody is ripping out structured tool calls.

HuggingFace "structured code agents" (JSON wrapper around generated code)
outperformed both pure approaches by 2-7 percentage points.

### 5. Dynamic Tool Loading Is Now a First-Party Feature

Anthropic shipped a Tool Search Tool — mark tools with `defer_loading: true`,
provide a search tool. Reduced token usage from ~55K to ~8.7K (85% reduction).
Caveat: Arcade's stress test with 4,000+ tools showed only 60% retrieval accuracy.

## Sandbox Landscape (2026)

| Sandbox | Isolation | Cold Start | Notes |
|---------|-----------|------------|-------|
| E2B | Firecracker microVM | ~150ms | Strongest isolation, ~half of Fortune 500 |
| Daytona | Docker containers | 27-90ms | Fastest fresh start |
| Blaxel | Firecracker + hibernate | ~25ms resume | Zero cost when idle |
| Sprites.dev (Fly.io) | Firecracker + checkpoint | <2s | Persistent filesystem state |
| Deno Sandbox | Firecracker | <1s | Secrets never enter sandbox |
| Pydantic Monty | Rust interpreter | Microseconds | Python subset only, v0.0.3 |
| Cloudflare Workers | V8 isolates | Milliseconds | JS/TS only, no filesystem |
| Docker (our setup) | Namespace + cgroup | 500ms-2s | Well-understood, solid security |

### Security: AST Sandboxes Are Dead

Every AST-based or in-process sandbox shipped in 2025-2026 has been broken:
- n8n (CVE-2026-25049, CVSS 9.4): Template literals bypassed AST sanitizer
- Agenta (CVE-2026-27952, CVSS 8.8): numpy allowlist → sys.modules → os.system
- vm2 (CVE-2026-22709, CVSS 9.8): Promise prototype manipulation
- Enclave (CVE-2026-27597): Critical RCE in JS sandbox for AI agents

**2026 consensus: process-level or VM-level isolation is the minimum.**
Our Docker + --network=none is on the right side of this line.

Simon Willison's "lethal trifecta": catastrophic risk = private data access +
untrusted content exposure + external communication ability. Remove any one
(our --network=none removes #3) and you eliminate the worst attacks.

## Observability for Code-Executing Agents

### OpenTelemetry GenAI Semantic Conventions (still experimental)
- Agent spans: `invoke_agent` operation with standardized attributes
- Tool execution spans: INTERNAL span kind
- Code execution spans: first-class concept

### The Pattern: Instrument Injected Functions
Wrap each function with a logging decorator before sandbox injection.
Every function call becomes a traced span with input/output/timing.
The sandbox is a trace context propagation boundary.

### Three Approaches in the Wild
1. **Anthropic PTC (host-bridge)**: Best observability — structured `tool_use` blocks
   preserved with `caller` field. Get BOTH code AND structured traces.
2. **OpenHands (event-sourced)**: Immutable typed events with deterministic replay.
3. **smolagents (minimal)**: Single `python_interpreter` ToolCall per step.
   Individual tool calls invisible without logging decorators.

## Tool Documentation Patterns

From Anthropic's "Writing Tools for Agents" (2026):
- Docstrings ARE the interface (especially in code mode)
- Parameter naming matters more than descriptions (`user_id` not `user`)
- Return value documentation is critical (model must parse results in code)
- Namespace tools by domain (`spreadsheet_read_range` not `read_range`)
- Error messages should be actionable (list alternatives, not just error codes)

## Architecture Patterns

### Pattern 1: Hybrid Loop
Planner (LLM) + Supervisor (deterministic) + Verifier + Tool Layer + Context Manager.
Deterministic code owns execution, state, safety. LLM only reasons and plans.

### Pattern 2: CodeAct (Code-as-Unified-Action-Space)
Model writes Python/TS that calls tools as functions in sandbox.
Intermediate data stays in sandbox; only print output enters context.
Variants: injected functions, filesystem discovery, host bridging, AST interpretation.

### Pattern 3: Two-Tool Meta Pattern
`search_docs` + `execute_code`. Agent discovers what it needs, writes code to use it.

### Pattern 4: Skills as Higher-Order Abstractions
Bundles instructions, scripts, templates, reference docs into loadable units.
Claude Code, Codex, Cursor all use this. Spring AI shipped Java implementation.

### Pattern 5: Evolving Tool Libraries (Agent as Toolsmith)
Agent saves successful code actions as reusable tools. Tool library grows at runtime.

## What's NOT Working

- AST-based sandboxes (all broken — see Security section)
- Equal-status multi-agent (20 agents → throughput of 2-3)
- Pure code-only with weak models (amplifies capability gap)
- 60-80% success rate ceiling for complex multi-tool PTC scenarios
- 67.3% of AI-generated PRs get rejected (OpenClaw study)
- Agents introduce "pattern pollution" — old patterns persist and propagate

## Implications for Our Harness

Our trajectory (growing tool set, capable code models) points toward code mode.
The incremental path:
1. Now: Clean up system prompt / tool description boundary
2. When adding spreadsheet tools: Expose as Python functions in Docker sandbox
3. Observability: Logging decorators on injected functions
4. Later (>20 tools): Add tool search/discovery

## Key Sources

- Anthropic Advanced Tool Use: https://www.anthropic.com/engineering/advanced-tool-use
- Anthropic Writing Tools: https://www.anthropic.com/engineering/writing-tools-for-agents
- Cloudflare Code Mode: https://blog.cloudflare.com/code-mode-mcp/
- Can Boluk Harness Problem: https://blog.can.ac/2026/02/12/the-harness-problem/
- UTCP Code Mode: https://github.com/universal-tool-calling-protocol/code-mode
- Letta PTC: https://www.letta.com/blog/programmatic-tool-calling-with-any-llm
- Pydantic Monty: https://pydantic.dev/articles/pydantic-monty
- open-ptc-agent: https://github.com/Chen-zexi/open-ptc-agent
- OpenAI Harness Engineering: https://openai.com/index/harness-engineering/
- Martin Fowler: https://martinfowler.com/articles/exploring-gen-ai/harness-engineering.html
- Philipp Schmid: https://www.philschmid.de/agent-harness-2026
- Inngest Utah: https://www.inngest.com/blog/your-agent-needs-a-harness-not-a-framework
- OpenDev paper: https://arxiv.org/html/2603.05344v1
- AgentScript: https://anandchowdhary.com/blog/2026/agentscript
- CodeAct paper: https://arxiv.org/html/2402.01030v4
- HuggingFace structured code agents: https://huggingface.co/blog/structured-codeagent
- Simon Willison sandbox field guide: https://simonwillison.net/2026/Jan/6/a-field-guide-to-sandboxes-for-ai/
- NVIDIA sandboxing guidance: https://developer.nvidia.com/blog/practical-security-guidance-for-sandboxing-agentic-workflows-and-managing-execution-risk/
- Arize observability-driven sandboxing: https://arize.com/blog/how-observability-driven-sandboxing-secures-ai-agents/
- OpenTelemetry GenAI conventions: https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/
