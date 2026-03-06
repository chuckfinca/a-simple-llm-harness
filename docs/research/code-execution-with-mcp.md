# Code Execution with MCP: Implications for Our Architecture
**Date:** 2026-03-04
**Source:** https://www.anthropic.com/engineering/code-execution-with-mcp

---

## What the Article Proposes

Instead of passing all tool definitions to the model upfront (burning tokens),
give it a code execution sandbox where it discovers and calls tools lazily by
writing code. Tools are presented as importable APIs, not JSON schemas.

Two key ideas:

1. **Lazy tool loading** — the model explores a filesystem of tool definitions
   on demand instead of receiving all schemas every turn. Demonstrated 98.7%
   token reduction (150K → 2K) with many tools.

2. **Code execution as a tool** — multi-step operations (loops, filtering,
   chaining API calls) happen in a sandbox outside the agent loop, avoiding
   one model turn per step.

## How It Maps to Our Architecture

Our loop is already structured for this:

- `agent.py` — the loop, model-agnostic, accepts any tool definitions
- `tools.py` — tool schemas + dispatch, separate concern

Both ideas would be new entries in `tools.py` without touching the loop:

- A `run_code` tool (sandbox for model-generated code)
- A `search_tools` / `list_tools` tool (lazy discovery)

## When to Revisit

- **Lazy loading** — irrelevant with 2 tools, critical with 10+. Watch for
  token cost becoming a meaningful fraction of per-turn spend.
- **Code execution** — relevant when we have multi-step data processing tasks
  (e.g., filtering documents, chaining API calls). Requires secure
  sandboxing infrastructure.

## Key Caveat

Code execution requires sandboxing, resource limits, and monitoring. The
operational complexity must be weighed against token savings.
