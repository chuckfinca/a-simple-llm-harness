# A Simple LLM Harness

A minimal agent loop for exploring document workspaces with tool-calling LLMs.
The model gets one tool — `run_python` — which executes code in a sandboxed
Docker container with read-only access to workspace files. No framework,
no vector database, no retrieval pipeline.

## Setup

```
uv sync
cp .env.example .env   # set LH_MODEL and LH_WORKSPACE
uv run python -m llm_harness
```

Requires Docker (the sandbox image builds automatically on first use).

## Architecture

```
src/llm_harness/

  agent.py        Agent loop — calls LLM, executes tools, yields events
  sandbox.py      Docker container execution
  tools.py        Tool definitions and dispatch
  prompt.py       System prompt assembly
  telemetry.py    Trace and turn dataclasses
  types.py        Event types
  display.py      Terminal output
```

## Eval

```
uv run python scripts/collect_traces.py
uv run python scripts/collect_traces.py --workers 4
uv run python scripts/collect_traces.py --filter highest-revenue
```

19 questions across 5 document corpora, measured with code-based assertions.

| Category | Tests | Example |
|---|---|---|
| `single_fact` | Look up one value | Amazon's net income in FY 2025 |
| `single_doc` | Read one document | Federalist No. 10 on factions |
| `multi_doc` | Synthesize across files | Highest revenue in dataset |
| `comparison` | Compare two things | JPMorgan Chase vs UnitedHealth |
| `enumeration` | Search and list | Countries in Africa |

Traces save as JSON in `traces/<model>/` with CSV in `traces/results.csv`.
`notebooks/trace_analysis.ipynb` provides run-over-run dashboards and an
interactive trace viewer.

### Test data

- `federalist-papers` — 85 files, political philosophy
- `origin-of-species` — 15 files, natural science
- `sherlock-holmes` — 24 files, fiction
- `world-factbook` — 29 files, structured country data
- `sec-10k` — ~25 files, SEC 10-K annual filings (generated)

## Development

```
uv run pytest
uv run ruff check .
uv run mypy src/
```
