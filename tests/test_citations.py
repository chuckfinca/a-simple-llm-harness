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
        assert superscript(1) == "¹"
        assert superscript(5) == "⁵"

    def test_multi_digit(self) -> None:
        assert superscript(12) == "¹²"


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
        quote = "The quick brown fox… over the lazy dog"
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
        answer = 'AppSimple is a consultancy <cite file="facts.md">AppSimple LLC is a consultancy.</cite>.'
        clean, sources = process_citations(answer, workspace)
        assert "<cite" not in clean
        assert "</cite>" not in clean
        assert len(sources) == 1
        assert sources[0]["matched"] is True
        assert sources[0]["line"] == 1

    def test_adjacent_citations(self) -> None:
        workspace = self._make_workspace({
            "facts.md": "Swift expert.\nPython proficient."
        })
        answer = (
            'Skills '
            '<cite file="facts.md">Swift expert.</cite>'
            '<cite file="facts.md">Python proficient.</cite>.'
        )
        _, sources = process_citations(answer, workspace)
        assert len(sources) == 2
        assert all(s["matched"] for s in sources)

    def test_deduplication(self) -> None:
        workspace = self._make_workspace({"facts.md": "Founded in 2013."})
        answer = (
            'A <cite file="facts.md">Founded in 2013.</cite>. '
            'B <cite file="facts.md">Founded in 2013.</cite>.'
        )
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
        answer = 'Claim <cite file="facts.md">Nonexistent text.</cite>.'
        _, sources = process_citations(answer, workspace)
        assert len(sources) == 1
        assert sources[0]["matched"] is False

    def test_filename_without_extension(self) -> None:
        workspace = self._make_workspace({"facts.md": "Some fact."})
        answer = 'Claim <cite file="facts">Some fact.</cite>.'
        _, sources = process_citations(answer, workspace)
        assert sources[0]["matched"] is True

    def test_doc_display_name(self) -> None:
        workspace = self._make_workspace({"ai-and-ml-services.md": "AI content."})
        answer = 'Claim <cite file="ai-and-ml-services.md">AI content.</cite>.'
        _, sources = process_citations(answer, workspace)
        assert sources[0]["doc"] == "ai and ml services"

    def test_self_closing_whole_file(self) -> None:
        workspace = self._make_workspace({"facts.md": "Some content."})
        answer = 'Darwin argues against this <cite file="facts.md"/>.'
        clean, sources = process_citations(answer, workspace)
        assert "<cite" not in clean
        assert len(sources) == 1
        assert sources[0]["quote"] == ""
        assert sources[0]["doc"] == "facts"

    def test_single_quote_attribute(self) -> None:
        workspace = self._make_workspace({"facts.md": "Founded in 2013."})
        answer = "Claim <cite file='facts.md'>Founded in 2013.</cite>."
        clean, sources = process_citations(answer, workspace)
        assert "<cite" not in clean
        assert sources[0]["matched"] is True

    def test_quote_containing_double_quotes(self) -> None:
        """Passages with embedded quote chars survive parsing because the
        passage is the element body, not an attribute value."""
        workspace = self._make_workspace({
            "facts.md": 'He said "hello" and walked away.'
        })
        answer = (
            'Claim <cite file="facts.md">'
            'He said "hello" and walked away.'
            '</cite>.'
        )
        _, sources = process_citations(answer, workspace)
        assert sources[0]["matched"] is True

    def test_passage_spanning_newlines(self) -> None:
        workspace = self._make_workspace({
            "facts.md": "First line.\nSecond line."
        })
        answer = (
            'Claim <cite file="facts.md">First line.\n'
            'Second line.</cite>.'
        )
        _, sources = process_citations(answer, workspace)
        assert sources[0]["matched"] is True

    def test_legacy_bracket_syntax_left_alone(self) -> None:
        """Old [file: "quote"] syntax is no longer parsed. It renders as
        literal text rather than silently failing — making drift visible."""
        workspace = self._make_workspace({"facts.md": "Some fact."})
        answer = 'Claim [facts.md: "Some fact."].'
        clean, sources = process_citations(answer, workspace)
        assert clean == answer
        assert sources == []
