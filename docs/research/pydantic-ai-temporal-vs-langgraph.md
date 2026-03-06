# Pydantic AI + Temporal vs LangGraph
**Date:** 2026-03-05
**Trigger:** Samuel Colvin podcast on Hugo Bowne-Anderson's Vanishing Gradients

---

## Context

Our earlier research (Feb 2026) concluded Pydantic AI wasn't mature enough for
big/complex projects. That was fair for the pre-v1 era (frequent breaking
changes through mid-2025). As of March 2026, Pydantic AI v1 has been stable
since Sept 2025 with an API stability commitment.

We know we will need human-in-the-loop approval gates, which requires durable
execution with real wait semantics.

## The Durability Argument

Colvin's core technical critique: LangGraph's checkpoint-based persistence
replays from the beginning of a failed node. Tool side effects (charging a
card, sending an email) re-execute unless the developer manually handles
idempotency. Temporal records the result of every Activity, so completed work
is skipped on replay.

This matters for us specifically because long-running workflows involve
consequential actions and human approval gates that may pause for hours or days.

## Comparison

| Dimension              | Pydantic AI + Temporal          | LangGraph                        |
|------------------------|---------------------------------|----------------------------------|
| Best for               | Linear workflows, durability    | Complex branching, parallel exec |
| Durability model       | Activity-based (rock-solid)     | Checkpoint-based (dev-managed)   |
| Type safety            | End-to-end, static analysis     | Breaks at state boundaries       |
| Parallel execution     | Not in pydantic-graph           | First-class                      |
| Observability          | OpenTelemetry native (no lock-in) | LangSmith (proprietary, paid)  |
| Maturity (Thoughtworks)| Trial                           | Adopt                            |
| Production evidence    | Growing (8M downloads/mo)       | Extensive (34.5M, 400+ companies)|
| Ecosystem              | Smaller                         | Much larger                      |
| Multi-agent            | Manual wiring                   | First-class primitives           |
| Operational burden     | Must run Temporal server         | Built-in checkpointing           |

## Ecosystem Gap: What It Actually Costs

- Fewer community answers when stuck (~4x less volume than LangGraph)
- Fewer pre-built integrations (vector stores, document loaders, etc.)
- Fewer developers who know it (hiring)

These matter less for us because we own our orchestration layer and use LiteLLM
directly rather than framework-provided connectors.

## Where PAI+T Pain Would Be Felt

1. Temporal is infrastructure to operate (server or Temporal Cloud)
2. No parallel graph execution — need asyncio for concurrent tool calls
3. Complex multi-agent handoffs require manual code vs LangGraph primitives

## The Loop Tradeoff

Durability requires the framework to control the loop (for both LangGraph and
Temporal). You cannot get durable execution while running your own while loop.

This means adopting either framework = giving up direct loop control. However,
the surrounding code (tools, telemetry, LiteLLM boundary) stays unchanged.

## Migration Path from Our Current Architecture

Our design maps cleanly onto Temporal's model:

| Current                | Temporal equivalent               |
|------------------------|-----------------------------------|
| `tools.py` functions   | Temporal Activities (each durable)|
| `agent.py` loop        | Temporal Workflow (framework loop)|
| `telemetry.py`         | Unchanged (LiteLLM callbacks)     |
| LiteLLM boundary       | Unchanged                         |
| `CompletionFunc`       | Called inside a Workflow step      |

Migration = delete our loop, wrap tool calls as Activities, define the agent
as a Workflow. Everything else stays.

## pydantic-graph: What It Can and Can't Do

pydantic-graph is a separate library from pydantic-ai. It has two APIs with a
key tradeoff between them.

### Stable API (single-threaded, what we'd use)

- Sequential chains, branching, conditional routing, loops/cycles
- State threaded through all nodes via a shared dataclass
- Built-in persistence (file, memory) for interrupt-and-resume
- Step-by-step execution with inspection between nodes
- Type-checked routing via union return types on node `run()` methods

### Beta API (adds parallelism)

- Fan-out (broadcast to multiple nodes), fan-in (join with reducers)
- Dynamic map over iterables
- No native persistence — must use Temporal/DBOS for durability

### The persistence/parallelism split

| Capability          | Stable API | Beta API |
|---------------------|------------|----------|
| Sequential/branching| Yes        | Yes      |
| Parallel execution  | No         | Yes      |
| Native persistence  | Yes        | No       |
| Temporal integration| Not wired  | Not wired|

Temporal integration is documented for `Agent` only, not for graph nodes.
Making individual graph nodes durable Temporal Activities would be manual
assembly with no official pattern.

### Not supported (and not planned)

- No native `interrupt()` for HITL (issue #1607, closed "not planned")
- No subgraph support (manual workaround only)
- No graph-level streaming (issue #732, closed "not planned")
- No node-level retry/rollback/saga patterns
- No node reusability across graphs (issue #798, open, unresolved)

### What this means for our HITL requirement

pydantic-graph's stable API can support approval gates, but requires manual
assembly: save state via persistence, present the question externally, resume
via `iter_from_persistence()`. This works for linear workflows with a few
gates. LangGraph's one-line `interrupt(payload)` is more ergonomic for complex
HITL patterns.

### pydantic-graph vs LangGraph primitives

| Capability            | LangGraph              | pydantic-graph              |
|-----------------------|------------------------|-----------------------------|
| Conditional routing   | External routing fn    | Return type on node (typed) |
| Parallel fan-out      | Automatic + Send API   | Beta API broadcast/map      |
| Fan-in / reduce       | State field reducers   | Beta API join nodes         |
| Subgraphs             | First-class            | Not supported               |
| HITL interrupt        | `interrupt(payload)`   | Manual with persistence     |
| Streaming             | `graph.stream()`       | Not supported               |
| Persistence           | Multiple backends      | File/memory (stable only)   |
| Type safety           | Partial                | End-to-end                  |

## Decision

No framework adoption now. Our current custom loop is correct for the prototype
phase.

When we add human-in-the-loop approval gates, Pydantic AI + Temporal is the
preferred direction given our priorities (durability, type safety, OTel, no
vendor lock-in). However: the Temporal + pydantic-graph integration has gaps
today. If our workflows stay mostly linear with approval gates, PAI's stable
API + manual HITL assembly is workable. If we need complex graph orchestration,
LangGraph has a real lead in ergonomics and maturity.

Watch for: Temporal integration with pydantic-graph nodes (not just agents),
and native `interrupt()` support. These would close the gap.

## Sources

- [Vanishing Gradients Ep 71: Durable Agents](https://hugobowne.substack.com/p/ai-is-still-engineering-why-durability)
- [Pydantic AI v1 announcement](https://pydantic.dev/articles/pydantic-ai-v1)
- [Temporal + Pydantic AI integration](https://temporal.io/blog/build-durable-ai-agents-pydantic-ai-and-temporal)
- [LangGraph 1.0 release](https://changelog.langchain.com/announcements/langgraph-1-0-is-now-generally-available)
- [Thoughtworks Radar: Pydantic AI (Trial)](https://www.thoughtworks.com/radar/languages-and-frameworks/pydantic-ai)
- [Thoughtworks Radar: LangGraph (Adopt)](https://www.thoughtworks.com/en-us/radar/languages-and-frameworks/langgraph)
- [Grid Dynamics: LangGraph → Temporal migration](https://temporal.io/blog/prototype-to-prod-ready-agentic-ai-grid-dynamics)
- [pydantic-graph docs](https://ai.pydantic.dev/graph/)
- [pydantic-graph beta API](https://ai.pydantic.dev/graph/beta/)
- [Beta graph persistence issue #3697](https://github.com/pydantic/pydantic-ai/issues/3697)
- [HITL with graph issue #1607 (closed)](https://github.com/pydantic/pydantic-ai/issues/1607)
- [Graph streaming issue #732 (closed)](https://github.com/pydantic/pydantic-ai/issues/732)
- [Node reusability issue #798 (open)](https://github.com/pydantic/pydantic-ai/issues/798)
- [Pydantic AI roadmap issue #913](https://github.com/pydantic/pydantic-ai/issues/913)
