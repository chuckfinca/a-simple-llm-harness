from __future__ import annotations

from pathlib import Path

PROMPTS_DIR = Path(__file__).parent / "prompts"


def build_system_prompt(
    *,
    base_prompt: str,
    workspace: Path | None = None,
) -> str:
    sections = [base_prompt]

    if workspace:
        file_count = sum(1 for p in workspace.rglob("*") if p.is_file())
        sections.append(
            _load_prompt("workspace").format(file_count=file_count)
        )
        sections.append(_load_prompt("search_strategy"))
        sections.append(_load_prompt("citations"))

    return "\n\n".join(sections)


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text().strip()
