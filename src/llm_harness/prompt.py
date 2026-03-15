from __future__ import annotations

from pathlib import Path

from llm_harness.sandbox import MAX_OUTPUT_CHARS

SYSTEM_PROMPT_PATH = Path(__file__).parent / "prompts" / "system.md"


def build_system_prompt(
    *,
    base_prompt: str,
    workspace: Path | None = None,
) -> str:
    if not workspace:
        return base_prompt

    file_count = sum(1 for p in workspace.rglob("*") if p.is_file())
    system = SYSTEM_PROMPT_PATH.read_text().strip().format(
        file_count=file_count,
        max_output_chars=MAX_OUTPUT_CHARS,
    )
    return f"{base_prompt}\n\n{system}"
