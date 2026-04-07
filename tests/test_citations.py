from __future__ import annotations

import tempfile
from pathlib import Path

from llm_harness.citations import (
    _find_ellipsis_segment,
    _find_exact,
    _find_word_window,
    process_citations,
    superscript,
)


class TestSuperscript:
    def test_single_digit(self) -> None:
        assert superscript(1) == "\u00b9"
        assert superscript(5) == "\u2075"

    def test_multi_digit(self) -> None:
        assert superscript(12) == "\u00b9\u00b2"


class TestFindExact:
    def test_exact_match(self) -> None:
        assert _find_exact("hello world", "world") == 6

    def test_case_insensitive(self) -> None:
        assert _find_exact("Hello World", "hello world") >= 0

    def test_no_match(self) -> None:
        assert _find_exact("hello world", "xyz") == -1


class TestFindEllipsisSegment:
    def test_splits_on_ellipsis(self) -> None:
        text = "The quick brown fox jumps over the lazy dog"
        quote = "The quick brown fox... over the lazy dog"
        assert _find_ellipsis_segment(text, quote) >= 0

    def test_skips_short_segments(self) -> None:
        text = "The quick brown fox"
        quote = "The... fox"
        assert _find_ellipsis_segment(text, quote) == -1

    def test_unicode_ellipsis(self) -> None:
        text = "The quick brown fox jumps over the lazy dog"
        quote = "The quick brown fox\u2026 over the lazy dog"
        assert _find_ellipsis_segment(text, quote) >= 0


class TestFindWordWindow:
    def test_matches_five_word_window(self) -> None:
        text = "Charles has over twelve years of software development experience"
        quote = "over twelve years of software"
        assert _find_word_window(text, quote) >= 0

    def test_short_quote_returns_negative(self) -> None:
        assert _find_word_window("some text", "two words", window_size=5) == -1

    def test_no_match(self) -> None:
        assert _find_word_window("hello world foo bar baz", "entirely different words here now") == -1


class TestProcessCitations:
    def _make_workspace(self, files: dict[str, str]) -> Path:
        tmp = Path(tempfile.mkdtemp())
        for name, content in files.items():
            (tmp / name).write_text(content)
        return tmp

    def test_single_citation(self) -> None:
        workspace = self._make_workspace({
            "facts.md": "AppSimple LLC is a consultancy.\nFounded in 2013."
        })
        answer = 'AppSimple is a consultancy [facts.md: "AppSimple LLC is a consultancy."].'
        clean, sources = process_citations(answer, workspace)
        assert "[" not in clean
        assert len(sources) == 1
        assert sources[0]["matched"] is True
        assert sources[0]["line"] == 1

    def test_multi_quote_citation(self) -> None:
        workspace = self._make_workspace({
            "facts.md": "Swift expert.\nPython proficient."
        })
        answer = 'Skills [facts.md: "Swift expert.", "Python proficient."].'
        _, sources = process_citations(answer, workspace)
        assert len(sources) == 2
        assert all(s["matched"] for s in sources)

    def test_deduplication(self) -> None:
        workspace = self._make_workspace({"facts.md": "Founded in 2013."})
        answer = 'A [facts.md: "Founded in 2013."]. B [facts.md: "Founded in 2013."].'
        _, sources = process_citations(answer, workspace)
        assert len(sources) == 1

    def test_no_workspace(self) -> None:
        clean, sources = process_citations("Some answer.", None)
        assert clean == "Some answer."
        assert sources == []

    def test_no_citations(self) -> None:
        workspace = self._make_workspace({"facts.md": "content"})
        clean, sources = process_citations("No citations here.", workspace)
        assert clean == "No citations here."
        assert sources == []

    def test_unmatched_quote(self) -> None:
        workspace = self._make_workspace({"facts.md": "Actual content."})
        answer = 'Claim [facts.md: "Nonexistent text."].'
        _, sources = process_citations(answer, workspace)
        assert len(sources) == 1
        assert sources[0]["matched"] is False

    def test_filename_without_extension(self) -> None:
        workspace = self._make_workspace({"facts.md": "Some fact."})
        answer = 'Claim [facts: "Some fact."].'
        _, sources = process_citations(answer, workspace)
        assert sources[0]["matched"] is True

    def test_doc_display_name(self) -> None:
        workspace = self._make_workspace({"ai-and-ml-services.md": "AI content."})
        answer = 'Claim [ai-and-ml-services.md: "AI content."].'
        _, sources = process_citations(answer, workspace)
        assert sources[0]["doc"] == "ai and ml services"

    def test_smart_quotes(self) -> None:
        workspace = self._make_workspace({"facts.md": "Founded in 2013."})
        answer = 'Claim [facts.md: \u201cFounded in 2013.\u201d].'
        clean, sources = process_citations(answer, workspace)
        assert "[" not in clean
        assert len(sources) == 1
        assert sources[0]["matched"] is True

    def test_bare_filename_reference(self) -> None:
        workspace = self._make_workspace({"facts.md": "Some content."})
        answer = "Darwin argues against this [facts.md]."
        clean, sources = process_citations(answer, workspace)
        assert "[" not in clean
        assert len(sources) == 1
        assert sources[0]["quote"] == ""
        assert sources[0]["doc"] == "facts"
