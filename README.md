# LLM Harness

Generic LLM agent harness with tool-use support.

## Setup

```
uv sync
```

The sandbox Docker image is built automatically on first use. Docker must be running.

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

## Testing the harness

Run with `uv run python -m llm_harness`. Test questions for the Federalist
Papers workspace (exercises file tool patterns):

- "What does Federalist No. 10 argue about factions?" (search + read)
- "Which papers discuss the judiciary?" (multi-file search)
- "What are the main themes across the Federalist Papers?" (broad exploration)
- "What does Hamilton say about standing armies?" (specific detail search)
- "How do Hamilton and Madison differ on federal power?" (cross-document comparison)

## Development

```
uv run pytest
uv run ruff check .
uv run ruff format .
uv run mypy src/
```
