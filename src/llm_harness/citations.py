"""Parse and verify inline citations from agent responses.

The agent is instructed to cite evidence as <cite file="X">passage</cite>,
or <cite file="X"/> when citing a whole file. This module extracts those
tags, verifies the passage against workspace files, and replaces each tag
with a Unicode superscript footnote number.

XML-style tags are used because markdown renderers ignore them, regex
parsing is unambiguous, and they survive provider differences in how
models format inline content. The previous bracket-based syntax broke
whenever the model added emphasis characters around the citation.
"""

from __future__ import annotations

import re
from pathlib import Path

_CITE_ELEMENT_RE = re.compile(
    r'<cite\s+file=(?P<q>["\'])(?P<file>[^"\']+)(?P=q)\s*>'
    r'(?P<quote>.*?)'
    r'</cite\s*>',
    re.DOTALL,
)
_CITE_SELF_CLOSING_RE = re.compile(
    r'<cite\s+file=(?P<q>["\'])(?P<file>[^"\']+)(?P=q)\s*/>',
)

_SUPERSCRIPT_DIGITS = str.maketrans(
    "0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹"
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


def _resolve_quote(workspace: Path, filename: str, quote: str) -> dict:
    """Find quote in workspace files; return source dict with line + matched."""
    matched = False
    line = None
    candidates = [filename, f"{filename}.md"]
    stem = Path(filename).stem
    candidates.extend(
        str(sub.relative_to(workspace)) for sub in workspace.rglob(f"{stem}.*")
    )
    for candidate in dict.fromkeys(candidates):
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
        "doc": Path(filename).stem.replace("_", " ").replace("-", " "),
        "file": filename,
        "quote": quote,
        "line": line,
        "matched": matched,
    }


def _whole_file_source(filename: str) -> dict:
    return {
        "doc": Path(filename).stem.replace("_", " ").replace("-", " "),
        "file": filename,
        "quote": "",
        "line": None,
        "matched": True,
    }


def process_citations(
    answer: str, workspace: Path | None
) -> tuple[str, list[dict]]:
    """Parse <cite> tags, verify quoted passages against workspace files.

    Returns (clean_answer, sources) where clean_answer has citation tags
    replaced with Unicode superscript numbers and sources is a list of dicts
    with keys: id, doc, file, quote, line, matched.
    """
    if not answer or not workspace:
        return answer or "", []

    sources: list[dict] = []
    seen: dict[tuple[str, str], int] = {}

    def _register(filename: str, quote: str) -> int:
        key = (filename, quote)
        if key in seen:
            return seen[key]
        idx = len(sources) + 1
        seen[key] = idx
        source = (
            _resolve_quote(workspace, filename, quote)
            if quote
            else _whole_file_source(filename)
        )
        sources.append({"id": idx, **source})
        return idx

    def _replace_element(match: re.Match) -> str:
        filename = match.group("file").strip()
        quote = match.group("quote").strip()
        return superscript(_register(filename, quote))

    def _replace_self_closing(match: re.Match) -> str:
        filename = match.group("file").strip()
        return superscript(_register(filename, ""))

    clean = _CITE_ELEMENT_RE.sub(_replace_element, answer)
    clean = _CITE_SELF_CLOSING_RE.sub(_replace_self_closing, clean)
    return clean, sources
