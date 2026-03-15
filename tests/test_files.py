from __future__ import annotations

import json
from pathlib import Path

from llm_harness.files import _list_files as list_files
from llm_harness.files import _read_file as read_file
from llm_harness.files import _search_files as search_files


def _setup_workspace(tmp_path: Path) -> None:
    (tmp_path / "readme.md").write_text("# Hello\nThis is a test.\n")
    (tmp_path / "notes.txt").write_text("Line one\nLine two\nLine three\n")
    sub = tmp_path / "subdir"
    sub.mkdir()
    (sub / "deep.md").write_text("Deep file content\n")


class TestListFiles:
    def test_lists_all_files(self, tmp_path: Path) -> None:
        _setup_workspace(tmp_path)
        result = json.loads(list_files(tmp_path))
        assert result["count"] == 3
        paths = {f["path"] for f in result["files"]}
        assert "readme.md" in paths
        assert "notes.txt" in paths
        assert "subdir/deep.md" in paths

    def test_lists_subdirectory(self, tmp_path: Path) -> None:
        _setup_workspace(tmp_path)
        result = json.loads(list_files(tmp_path, "subdir"))
        assert result["count"] == 1
        assert result["files"][0]["path"] == "subdir/deep.md"

    def test_filters_by_pattern(self, tmp_path: Path) -> None:
        _setup_workspace(tmp_path)
        result = json.loads(list_files(tmp_path, pattern="deep"))
        assert result["count"] == 1
        assert result["files"][0]["path"] == "subdir/deep.md"

    def test_pattern_no_matches(self, tmp_path: Path) -> None:
        _setup_workspace(tmp_path)
        result = json.loads(list_files(tmp_path, pattern="nonexistent"))
        assert result["count"] == 0

    def test_path_traversal_blocked(self, tmp_path: Path) -> None:
        _setup_workspace(tmp_path)
        result = json.loads(list_files(tmp_path, "../"))
        assert "error" in result


class TestReadFile:
    def test_reads_full_file(self, tmp_path: Path) -> None:
        _setup_workspace(tmp_path)
        result = json.loads(read_file(tmp_path, "readme.md"))
        assert "# Hello" in result["content"]
        assert result["total_lines"] == 2

    def test_reads_with_offset_and_limit(self, tmp_path: Path) -> None:
        _setup_workspace(tmp_path)
        result = json.loads(read_file(tmp_path, "notes.txt", offset=1, limit=1))
        assert "Line two" in result["content"]
        assert result["lines_returned"] == 1

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        _setup_workspace(tmp_path)
        result = json.loads(read_file(tmp_path, "missing.txt"))
        assert "error" in result

    def test_path_traversal_blocked(self, tmp_path: Path) -> None:
        _setup_workspace(tmp_path)
        result = json.loads(read_file(tmp_path, "../../etc/passwd"))
        assert "error" in result


class TestSearchFiles:
    def test_finds_matching_lines(self, tmp_path: Path) -> None:
        _setup_workspace(tmp_path)
        result = json.loads(search_files(tmp_path, "Hello"))
        assert len(result["matches"]) == 1
        assert result["matches"][0]["file"] == "readme.md"

    def test_case_insensitive(self, tmp_path: Path) -> None:
        _setup_workspace(tmp_path)
        result = json.loads(search_files(tmp_path, "HELLO"))
        assert len(result["matches"]) == 1

    def test_whole_words_excludes_substrings(self, tmp_path: Path) -> None:
        _setup_workspace(tmp_path)
        (tmp_path / "words.txt").write_text("judged\njudge\nill-judged\n")
        result = json.loads(search_files(tmp_path, "judge", "*.txt"))
        texts = [m["text"] for m in result["matches"]]
        assert "judge" in texts
        assert "judged" not in texts
        assert "ill-judged" not in texts

    def test_whole_words_off_matches_substrings(self, tmp_path: Path) -> None:
        _setup_workspace(tmp_path)
        (tmp_path / "words.txt").write_text("judged\njudge\n")
        result = json.loads(search_files(tmp_path, "judge", "*.txt", whole_words=False))
        assert len(result["matches"]) == 2

    def test_no_matches(self, tmp_path: Path) -> None:
        _setup_workspace(tmp_path)
        result = json.loads(search_files(tmp_path, "nonexistent_string_xyz"))
        assert len(result["matches"]) == 0
        assert result["truncated"] is False

    def test_total_matches_and_truncation_message(self, tmp_path: Path) -> None:
        _setup_workspace(tmp_path)
        (tmp_path / "many.txt").write_text(
            "\n".join(f"match word here line {i}" for i in range(50)) + "\n"
        )
        result = json.loads(search_files(tmp_path, "match", "*.txt"))
        assert result["truncated"] is True
        assert result["total_matches"] == 50
        assert len(result["matches"]) == 30
        assert "50" in result["message"]

    def test_searches_subdirectories(self, tmp_path: Path) -> None:
        _setup_workspace(tmp_path)
        result = json.loads(search_files(tmp_path, "Deep", "*.md"))
        assert any(m["file"] == "subdir/deep.md" for m in result["matches"])
