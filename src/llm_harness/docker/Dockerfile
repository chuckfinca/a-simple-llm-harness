FROM python:3.12-slim

# duckdb lets atelier's region/orientation/ask agents query the
# DuckDB-over-Arrow ir.duckdb projection (ATELIER_LLM_QUERY_ENGINE=duckdb).
# The sandbox runs with --network=none, so it must be baked in — the
# agent can't pip-install at runtime. sqlite3 is stdlib (default engine).
RUN pip install --no-cache-dir numpy pandas scipy duckdb

RUN useradd --create-home --shell /bin/false sandbox
USER sandbox
WORKDIR /home/sandbox
