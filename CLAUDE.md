Write code that any developer can understand on first read. Prefer clarity
over cleverness — a straightforward implementation beats an elegant
abstraction that requires explanation.

Name functions and variables so precisely that comments become redundant.
When a comment is necessary, explain *why*, never *what*.

Keep modules small and focused on a single responsibility. If a function
needs a comment to explain its control flow, it should be split up.

## Testing the harness

Run with `uv run python -m llm_harness`. Test questions for the Federalist
Papers workspace (exercises file tool patterns):

- "What does Federalist No. 10 argue about factions?" (search + read)
- "Which papers discuss the judiciary?" (multi-file search)
- "What are the main themes across the Federalist Papers?" (broad exploration)
- "What does Hamilton say about standing armies?" (specific detail search)
- "How do Hamilton and Madison differ on federal power?" (cross-document comparison)
