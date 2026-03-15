from __future__ import annotations

import json

from llm_harness.tools import TOOL_DEFINITIONS, execute_tool


class TestToolDefinitions:
    def test_single_run_python_tool(self) -> None:
        assert len(TOOL_DEFINITIONS) == 1
        tool = TOOL_DEFINITIONS[0]
        assert tool["type"] == "function"
        fn = tool["function"]
        assert fn["name"] == "run_python"
        assert "description" in fn
        assert "parameters" in fn
        assert "from tools import" in fn["description"]


class TestRunPython:
    def test_hello_world(self) -> None:
        result = json.loads(execute_tool("run_python", '{"code": "print(42)"}'))
        assert result["exit_code"] == 0
        assert "42" in result["stdout"]
        assert result["timed_out"] is False

    def test_syntax_error(self) -> None:
        result = json.loads(execute_tool("run_python", '{"code": "def"}'))
        assert result["exit_code"] != 0
        assert result["stderr"]

    def test_numpy_available(self) -> None:
        code = "import numpy; print(numpy.array([1,2,3]).sum())"
        result = json.loads(execute_tool("run_python", json.dumps({"code": code})))
        assert result["exit_code"] == 0
        assert "6" in result["stdout"]

    def test_tools_importable_with_workspace(self) -> None:
        """When workspace is provided, `from tools import ...` works inside sandbox."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "test.txt").write_text("hello world\n")

            code = (
                "from tools import list_files\n"
                "import json\n"
                "result = json.loads(list_files('.'))\n"
                "print(result['count'])\n"
            )
            result = json.loads(
                execute_tool(
                    "run_python",
                    json.dumps({"code": code}),
                    workspace=workspace,
                )
            )
            assert result["exit_code"] == 0
            assert "1" in result["stdout"]

    def test_sub_call_traces_in_stderr(self) -> None:
        """Tool function calls emit __TOOL_CALL__ lines to stderr."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "test.txt").write_text("hello\n")

            code = "from tools import list_files; list_files('.')"
            result = json.loads(
                execute_tool(
                    "run_python",
                    json.dumps({"code": code}),
                    workspace=workspace,
                )
            )
            assert result["exit_code"] == 0
            assert "__TOOL_CALL__:" in result["stderr"]


class TestExecuteTool:
    def test_unknown_tool_returns_error(self) -> None:
        result = json.loads(execute_tool("nonexistent", "{}"))
        assert "error" in result

    def test_invalid_json_returns_error(self) -> None:
        result = json.loads(execute_tool("run_python", "not json"))
        assert "error" in result
