from __future__ import annotations

import json

from llm_harness.tools import TOOL_DEFINITIONS, execute_tool


class TestToolDefinitions:
    def test_all_tools_have_required_fields(self) -> None:
        for tool in TOOL_DEFINITIONS:
            assert tool["type"] == "function"
            fn = tool["function"]
            assert "name" in fn
            assert "description" in fn
            assert "parameters" in fn


class TestCalculator:
    def test_basic_arithmetic(self) -> None:
        result = json.loads(execute_tool("calculator", '{"expression": "2 + 2"}'))
        assert result["result"] == 4

    def test_sqrt(self) -> None:
        result = json.loads(execute_tool("calculator", '{"expression": "sqrt(16)"}'))
        assert result["result"] == 4.0

    def test_bad_expression_returns_error(self) -> None:
        result = json.loads(
            execute_tool("calculator", '{"expression": "undefined_var"}')
        )
        assert "error" in result


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


class TestExecuteTool:
    def test_unknown_tool_returns_error(self) -> None:
        result = json.loads(execute_tool("nonexistent", "{}"))
        assert "error" in result

    def test_invalid_json_returns_error(self) -> None:
        result = json.loads(execute_tool("calculator", "not json"))
        assert "error" in result
