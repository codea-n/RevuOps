import json
import pytest
from unittest.mock import patch, AsyncMock
from mcp.types import TextContent
from app.tools.mcp_server import list_tools, call_tool


class TestListTools:
    @pytest.mark.asyncio
    async def test_returns_three_tools(self):
        tools = await list_tools()
        assert len(tools) == 3

    @pytest.mark.asyncio
    async def test_tool_names(self):
        tools = await list_tools()
        names = {t.name for t in tools}
        assert names == {"ast_parser", "ruff_linter", "bandit_scanner"}

    @pytest.mark.asyncio
    async def test_each_tool_has_description(self):
        tools = await list_tools()
        for tool in tools:
            assert tool.description, f"Tool '{tool.name}' has no description"

    @pytest.mark.asyncio
    async def test_each_tool_has_input_schema(self):
        tools = await list_tools()
        for tool in tools:
            assert tool.inputSchema is not None, f"Tool '{tool.name}' missing inputSchema"

    @pytest.mark.asyncio
    async def test_each_tool_schema_requires_code(self):
        tools = await list_tools()
        for tool in tools:
            required = tool.inputSchema.get("required", [])
            assert "code" in required, f"Tool '{tool.name}' schema must require 'code'"


# ── call_tool: routing ───────────────────────────────────

class TestCallToolRouting:
    @pytest.mark.asyncio
    async def test_ast_parser_route(self):
        """call_tool routes 'ast_parser' to ast_parser.run()"""
        fake_result = {"functions": [], "classes": [], "imports": [],
                       "has_parse_error": False, "parse_error_msg": "",
                       "complexity_warnings": []}
        with patch("app.tools.mcp_server.ast_parser.run", return_value=fake_result) as mock_run:
            result = await call_tool("ast_parser", {"code": "x = 1"})
            mock_run.assert_called_once_with("x = 1")

    @pytest.mark.asyncio
    async def test_ruff_linter_route(self):
        """call_tool routes 'ruff_linter' to ruff_linter.run()"""
        with patch("app.tools.mcp_server.ruff_linter.run", return_value=[]) as mock_run:
            result = await call_tool("ruff_linter", {"code": "import os"})
            mock_run.assert_called_once_with("import os")

    @pytest.mark.asyncio
    async def test_bandit_scanner_route(self):
        """call_tool routes 'bandit_scanner' to bandit_scanner.run()"""
        with patch("app.tools.mcp_server.bandit_scanner.run", return_value=[]) as mock_run:
            result = await call_tool("bandit_scanner", {"code": "eval('x')"})
            mock_run.assert_called_once_with("eval('x')")

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self):
        result = await call_tool("nonexistent_tool", {"code": "x = 1"})
        payload = json.loads(result[0].text)
        assert "error" in payload
        assert "nonexistent_tool" in payload["error"]


# ── call_tool: return type ──────────────────────────────

class TestCallToolReturnType:
    @pytest.mark.asyncio
    async def test_returns_list(self):
        with patch("app.tools.mcp_server.ast_parser.run", return_value={}):
            result = await call_tool("ast_parser", {"code": ""})
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_returns_text_content(self):
        with patch("app.tools.mcp_server.ast_parser.run", return_value={}):
            result = await call_tool("ast_parser", {"code": ""})
        assert isinstance(result[0], TextContent)

    @pytest.mark.asyncio
    async def test_text_content_type_field(self):
        with patch("app.tools.mcp_server.ast_parser.run", return_value={}):
            result = await call_tool("ast_parser", {"code": ""})
        assert result[0].type == "text"

    @pytest.mark.asyncio
    async def test_response_is_valid_json(self):
        fake = {"functions": [{"name": "foo", "loc": 5}]}
        with patch("app.tools.mcp_server.ast_parser.run", return_value=fake):
            result = await call_tool("ast_parser", {"code": "def foo(): pass"})
        parsed = json.loads(result[0].text)   # must not raise
        assert isinstance(parsed, dict)

    @pytest.mark.asyncio
    async def test_ast_result_preserved_in_json(self):
        fake = {"functions": [{"name": "my_fn", "loc": 10, "complexity": 2}]}
        with patch("app.tools.mcp_server.ast_parser.run", return_value=fake):
            result = await call_tool("ast_parser", {"code": "def my_fn(): pass"})
        payload = json.loads(result[0].text)
        assert payload["functions"][0]["name"] == "my_fn"


class TestCallToolMissingArgs:
    @pytest.mark.asyncio
    async def test_empty_arguments_defaults_to_empty_string(self):
        """arguments.get('code', '') means missing key is handled, not a crash."""
        with patch("app.tools.mcp_server.ast_parser.run", return_value={}) as mock_run:
            await call_tool("ast_parser", {})   # no 'code' key
        mock_run.assert_called_once_with("")

    @pytest.mark.asyncio
    async def test_empty_code_does_not_crash(self):
        with patch("app.tools.mcp_server.ruff_linter.run", return_value=[]):
            result = await call_tool("ruff_linter", {"code": ""})
        assert isinstance(result, list)