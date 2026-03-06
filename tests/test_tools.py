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


class TestExecuteTool:
    def test_unknown_tool_returns_error(self) -> None:
        result = json.loads(execute_tool("nonexistent", "{}"))
        assert "error" in result

    def test_invalid_json_returns_error(self) -> None:
        result = json.loads(execute_tool("calculator", "not json"))
        assert "error" in result
