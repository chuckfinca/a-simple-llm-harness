"""Parse and verify inline citations from agent responses.

The agent is instructed to cite evidence as [filename: "quoted passage"].
This module extracts those citations, verifies the quoted text against
workspace files, and replaces them with Unicode superscript numbers.
"""

from __future__ import annotations

import re
from pathlib import Path

_CITATION_RE = re.compile(
    r'\[([^:\[\]]+):\s*("(?:[^"]*)"(?:\s*,\s*"(?:[^"]*)")*)\]'
)
_QUOTES_RE = re.compile(r'"([^"]*)"')
_SUPERSCRIPT_DIGITS = str.maketrans(
    "0123456789", "\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079"
)


def superscript(n: int) -> str:
    return str(n).translate(_SUPERSCRIPT_DIGITS)


def _find_exact(text: str, quote: str) -> int:
    pos = text.find(quote)
    if pos == -1:
        pos = text.lower().find(quote.lower())
    return pos


def _find_ellipsis_segment(text: str, quote: str) -> int:
    segments = re.split(r"\.\.\.|…", quote)
    for segment in segments:
        segment = segment.strip()
        if len(segment) < 10:
            continue
        pos = _find_exact(text, segment)
        if pos >= 0:
            return pos
    return -1


def _find_word_window(text: str, quote: str, window_size: int = 5) -> int:
    words = quote.split()
    if len(words) < window_size:
        return -1
    text_lower = text.lower()
    for i in range(len(words) - window_size + 1):
        window = " ".join(words[i : i + window_size]).lower()
        pos = text_lower.find(window)
        if pos >= 0:
            return pos
    return -1


def _find_quote_in_text(text: str, quote: str) -> int:
    for strategy in (_find_exact, _find_ellipsis_segment, _find_word_window):
        pos = strategy(text, quote)
        if pos >= 0:
            return pos
    return -1


def process_citations(
    answer: str, workspace: Path | None
) -> tuple[str, list[dict]]:
    """Parse [filename: "quote"] citations, verify against workspace files.

    Returns (clean_answer, sources) where clean_answer has citations replaced
    with Unicode superscript numbers and sources is a list of dicts with keys:
    id, doc, file, quote, line, matched.
    """
    if not answer or not workspace:
        return answer or "", []

    sources: list[dict] = []
    seen: dict[tuple[str, str], int] = {}

    def _resolve_quote(filename: str, quote: str) -> dict:
        matched = False
        line = None
        for candidate in [filename, f"{filename}.md"]:
            filepath = workspace / candidate
            if filepath.is_file():
                try:
                    text = filepath.read_text(errors="replace")
                    pos = _find_quote_in_text(text, quote)
                    if pos >= 0:
                        matched = True
                        line = text[:pos].count("\n") + 1
                        break
                except OSError:
                    pass
        return {
            "doc": filename.replace(".md", "").replace("_", " ").replace("-", " "),
            "file": filename,
            "quote": quote,
            "line": line,
            "matched": matched,
        }

    def _replace(match: re.Match) -> str:
        filename = match.group(1).strip()
        raw_quotes = match.group(2)
        quotes = _QUOTES_RE.findall(raw_quotes)

        superscripts = []
        for quote in quotes:
            quote = quote.strip()
            key = (filename, quote)
            if key in seen:
                superscripts.append(superscript(seen[key]))
                continue
            idx = len(sources) + 1
            seen[key] = idx
            sources.append({"id": idx, **_resolve_quote(filename, quote)})
            superscripts.append(superscript(idx))

        return "".join(superscripts)

    clean_answer = _CITATION_RE.sub(_replace, answer)
    return clean_answer, sources
