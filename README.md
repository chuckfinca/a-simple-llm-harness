---
title: Document Explorer
emoji: 📄
colorFrom: blue
colorTo: green
sdk: gradio
sdk_version: "6.9.0"
app_file: app.py
pinned: false
---

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

### Web interface

Upload documents and ask questions in the browser:

```
uv run python app.py
```

Set `LH_ACCESS_TOKEN` in `.env` to require authentication.

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
uv run python scripts/collect_traces.py --filter highest-revenue
```

Questions are defined in `test-data/<workspace>/questions.json`, measured
with code-based assertions. Categories test general capabilities:

| Category | Capability | Example |
|---|---|---|
| `single_fact` | Look up one value | Amazon's net income in FY 2025 |
| `single_doc` | Read one document | Federalist No. 10 on factions |
| `multi_doc` | Synthesize across files | Highest revenue in dataset |
| `comparison` | Compare two things | JPMorgan Chase vs UnitedHealth |
| `enumeration` | Search and list | Countries in Africa |
| `cross_reference` | Find connections between data points | Tension between Federalist 10 and 51 |
| `anomaly_detection` | Spot what's unusual | GDP vs human development outlier |
| `trend_synthesis` | Describe trajectory with causes | Watson's evolving characterization of Holmes |
| `cited_analysis` | Make claims and cite evidence | Darwin's weakest rebuttal by modern standards |
| `analysis` | Open-ended analytical commentary | Occupancy trend for exec summary |

Questions run independently by default. Questions in the same **session**
share message history and scratchpad, so the model builds on prior
exploration instead of starting fresh. This supports two use cases:

- **Standalone questions** — each gets a clean conversation (the common case
  for factual retrieval and document Q&A).
- **Session questions** — a sequence of questions that share context, useful
  when generating related sections of a report where earlier analysis
  informs later commentary.

Sessions are defined per-question in `questions.json` via the `session`
field. Questions without a session run standalone.

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
