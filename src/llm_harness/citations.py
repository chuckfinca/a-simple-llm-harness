"""Parse and verify inline citations from agent responses.

The agent is instructed to cite evidence as [filename: "quoted passage"].
This module extracts those citations, verifies the quoted text against
workspace files, and replaces them with Unicode superscript numbers.
"""

from __future__ import annotations

import re
from pathlib import Path

_CITATION_RE = re.compile(
    r'\[([^:\[\]]+):\s*(["\u201c](?:[^"\u201d]*)["\u201d](?:\s*,\s*["\u201c](?:[^"\u201d]*)["\u201d])*)\]'
)
_BARE_CITATION_RE = re.compile(r'\[([a-zA-Z0-9_\-]+\.\w+)\]')
_BARE_LIST_CITATION_RE = re.compile(
    r'\[([a-zA-Z0-9_\-]+\.\w+(?:\s*,\s*[a-zA-Z0-9_\-]+\.\w+)+)\]'
)
_QUOTES_RE = re.compile(r'["\u201c]([^"\u201d]*)["\u201d]')
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


def _bare_source(filename: str, idx: int) -> dict:
    """Source dict for a citation that has no quoted passage."""
    return {
        "doc": Path(filename).stem.replace("_", " ").replace("-", " "),
        "file": filename,
        "quote": "",
        "line": None,
        "matched": True,
        "id": idx,
    }


def _apply_full_citations(
    answer: str,
    workspace: Path,
    sources: list[dict],
    seen: dict[tuple[str, str], int],
) -> str:
    def _replace(match: re.Match) -> str:
        filename = match.group(1).strip()
        quotes = _QUOTES_RE.findall(match.group(2))
        superscripts = []
        for quote in quotes:
            quote = quote.strip()
            key = (filename, quote)
            if key in seen:
                superscripts.append(superscript(seen[key]))
                continue
            idx = len(sources) + 1
            seen[key] = idx
            sources.append({"id": idx, **_resolve_quote(workspace, filename, quote)})
            superscripts.append(superscript(idx))
        return "".join(superscripts)

    return _CITATION_RE.sub(_replace, answer)


def _apply_bare_list_citations(
    answer: str,
    sources: list[dict],
    seen: dict[tuple[str, str], int],
) -> str:
    def _replace(match: re.Match) -> str:
        filenames = [f.strip() for f in match.group(1).split(",")]
        superscripts = []
        for filename in filenames:
            key = (filename, "")
            if key in seen:
                superscripts.append(superscript(seen[key]))
                continue
            idx = len(sources) + 1
            seen[key] = idx
            sources.append(_bare_source(filename, idx))
            superscripts.append(superscript(idx))
        return "".join(superscripts)

    return _BARE_LIST_CITATION_RE.sub(_replace, answer)


def _apply_bare_citations(
    answer: str,
    sources: list[dict],
    seen: dict[tuple[str, str], int],
) -> str:
    def _replace(match: re.Match) -> str:
        filename = match.group(1).strip()
        key = (filename, "")
        if key in seen:
            return superscript(seen[key])
        idx = len(sources) + 1
        seen[key] = idx
        sources.append(_bare_source(filename, idx))
        return superscript(idx)

    return _BARE_CITATION_RE.sub(_replace, answer)


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
    clean_answer = _apply_full_citations(answer, workspace, sources, seen)
    clean_answer = _apply_bare_list_citations(clean_answer, sources, seen)
    clean_answer = _apply_bare_citations(clean_answer, sources, seen)
    return clean_answer, sources
