import sys
import asyncio
import json
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Import your native custom tool engines
from app.tools import ast_parser, ruff_linter, bandit_scanner

# Initialize the MCP Server instance
app = Server("auto-reviewer-tools")

@app.list_tools()
async def list_tools() -> list[Tool]:
    """Advertise available tools to any MCP client that connects."""
    return [
        Tool(
            name="ast_parser",
            description=(
                "Analyzes Python source code structure. "
                "Returns functions, classes, imports, and cyclomatic complexity. "
                "Use this to understand code architecture and flag overly complex functions."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python source code to analyze"}
                },
                "required": ["code"]
            }
        ),
        Tool(
            name="ruff_linter",
            description=(
                "Runs Ruff linter on Python source code. "
                "Catches style violations, unused variables, incorrect patterns, "
                "and hundreds of other lint rules. Fast and comprehensive."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python source code to lint"}
                },
                "required": ["code"]
            }
        ),
        Tool(
            name="bandit_scanner",
            description=(
                "Runs Bandit security scanner on Python source code. "
                "Detects SQL injection, shell injection, hardcoded secrets, "
                "weak cryptography, and other security vulnerabilities."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python source code to scan for security issues"}
                },
                "required": ["code"]
            }
        ),
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Route an incoming tool call to the correct module and return results."""
    code = arguments.get("code", "")
    
    if name == "ast_parser":
        result = ast_parser.run(code)
    elif name == "ruff_linter":
        result = ruff_linter.run(code)
    elif name == "bandit_scanner":
        result = bandit_scanner.run(code)
    else:
        result = {"error": f"Unknown tool: {name}"}
        
    return [TextContent(type="text", text=json.dumps(result))]

async def main():
    """Start the MCP server over stdio."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())