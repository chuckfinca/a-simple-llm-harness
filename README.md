# LLM Harness

A minimal agent harness for evaluating LLM tool use. No framework — the agent
loop is a generator that yields events, tool execution is sandboxed in Docker,
and prompt modules attach conditionally based on what capabilities are
configured.

## Architecture

```
__main__.py          CLI REPL — reads events, dispatches to display.py
    │
    ▼
agent.py             Agent loop — calls LLM, executes tools, yields events
    │
    ├─► tools.py     Tool definitions (OpenAI schema) + dispatch
    │       │
    │       ▼
    │   sandbox.py   Docker execution — all tools run in sandboxed containers
    │       │
    │       ▼
    │   files.py     File tool implementations (runs inside Docker)
    │
    ├─► prompt.py    System prompt assembly from markdown modules
    │       │
    │       ▼
    │   prompts/     workspace.md, search_strategy.md, citations.md
    │
    └─► types.py     ToolCallEvent, ToolResultEvent, ResponseEvent
```

The agent loop is decoupled from everything. It takes a `completion` function
(any callable matching litellm's signature), yields events, and the caller
decides what to do with them — display in a terminal, collect traces for
evaluation, or run assertions in tests.

### Sandboxing

All tool execution runs in Docker containers with no capabilities, no network,
read-only filesystem, 512MB memory, and 100 PID limit. The workspace is
mounted read-only. Even file reads are sandboxed.

### Conditional prompts

The base prompt is general-purpose ("helpful assistant with tools"). When a
workspace is configured, `prompt.py` appends three modules: retrieval
identity, search strategy, and citation format. Future capabilities get their
own modules without touching the base prompt.

## Setup

```
uv sync
```

Docker must be running. The sandbox image is built automatically on first use.

Configure in `.env`:

```
LH_MODEL=openrouter/qwen/qwen3-coder
LH_SYSTEM_PROMPT=You are a helpful assistant with access to tools for computation, code execution, and file exploration.
LH_WORKSPACE=./test-data/federalist-papers
```

Run the interactive CLI:

```
uv run python -m llm_harness
```

## Evaluation

`scripts/collect_traces.py` runs 14 questions across 4 document corpora and
measures pass/fail with code-based assertions.

```
LH_MODEL=openrouter/qwen/qwen3-coder uv run python scripts/collect_traces.py --workers 4
```

Each question has a category (what skill it tests) and assertions:

| Category | Tests | Example |
|---|---|---|
| `single_fact` | Look up one specific value | Population of Japan |
| `single_doc` | Find and read one document | Fed No. 10 on factions |
| `multi_doc` | Synthesize across files | Main themes across papers |
| `comparison` | Find and compare two things | Hamilton vs Madison |
| `enumeration` | Search and list items | Countries in Africa |

Output:
- **JSON traces** in `traces/<model>/<workspace>/` — full conversation
  including tool calls, for manual review
- **CSV** in `traces/results.csv` — per-question metrics: pass/fail,
  tool sequence, citations, tokens, cost, latency

### Test data

Four document corpora in `test-data/`:

- `federalist-papers` (85 files) — political philosophy
- `origin-of-species` (15 files) — natural science
- `sherlock-holmes` (24 files) — fiction
- `world-factbook` (29 files) — structured country data

### Integration tests

`tests/test_retrieval_grounding.py` runs counterfactual mutations — changing
facts, adding synthetic documents, removing files — to verify the model reads
documents instead of answering from training data. These make real API calls:

```
uv run pytest tests/test_retrieval_grounding.py -m integration
```

## Adding a capability

Each capability needs up to three things: prompt instructions, tool
definitions, and tool dispatch.

1. Create a markdown file in `src/llm_harness/prompts/` (e.g.,
   `spreadsheet.md`). Start with a `##` header. Use `{variable}` for
   runtime values filled at startup.
2. Add a conditional block in `prompt.py`'s `build_system_prompt()`:
   ```python
   if spreadsheets:
       sections.append(_load_prompt("spreadsheet").format(...))
   ```
3. Add tool definitions and dispatch in `tools.py`.

Prompt sections are joined with `"\n\n"`. Order matters for cache
friendliness: static sections first, session-specific sections last.

## Development

```
uv run pytest
uv run ruff check .
uv run ruff format .
uv run mypy src/
```
