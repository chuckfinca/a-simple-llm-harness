# LLM Harness

Generic LLM agent harness with tool-use support.

## Setup

```
uv sync
```

The sandbox Docker image is built automatically on first use. Docker must be running.

## Development

```
uv run pytest
uv run ruff check .
uv run ruff format .
uv run mypy src/
```
