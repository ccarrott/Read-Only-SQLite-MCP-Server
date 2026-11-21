"""Integration tests for FastMCP tools, resources, and prompt definitions."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from mcp.server.fastmcp import FastMCP
from sqlite_mcp.server import create_mcp_server


@pytest.fixture
def mcp_server(sample_db_path: Path) -> FastMCP:
    """Instantiates a FastMCP server configured with the sample database."""
    return create_mcp_server(sample_db_path)


class TestFastMCPTools:
    """Verifies tool calling behavior and JSON responses via FastMCP."""

    @pytest.mark.anyio
    async def test_list_tables_tool(self, mcp_server: FastMCP) -> None:
        contents, result = await mcp_server.call_tool("list_tables", {})
        assert result["success"] is True
        assert result["total_count"] >= 4  # users, products, orders, order_summary

        table_names = [t["name"] for t in result["tables"]]
        assert "users" in table_names
        assert "products" in table_names
        assert "orders" in table_names
        assert "order_summary" in table_names
        assert all(not name.startswith("sqlite_") for name in table_names)

    @pytest.mark.anyio
    async def test_describe_table_tool_existing(self, mcp_server: FastMCP) -> None:
        contents, result = await mcp_server.call_tool("describe_table", {"table_name": "users"})
        assert result["success"] is True
        assert result["table_name"] == "users"
        assert result["type"] == "table"
        assert "CREATE TABLE users" in result["ddl"]

        col_names = [col["name"] for col in result["columns"]]
        assert "id" in col_names
        assert "email" in col_names
        assert "avatar" in col_names
        assert "bio" in col_names

        # Verify index presence
        idx_names = [idx["name"] for idx in result["indexes"]]
        assert "idx_users_email" in idx_names

    @pytest.mark.anyio
    async def test_describe_table_tool_nonexistent(self, mcp_server: FastMCP) -> None:
        contents, result = await mcp_server.call_tool("describe_table", {"table_name": "ghost_table"})
        assert result["success"] is False
        assert "does not exist" in result["error"].lower()

    @pytest.mark.anyio
    async def test_execute_query_tool_success(self, mcp_server: FastMCP) -> None:
        contents, result = await mcp_server.call_tool(
            "execute_query",
            {"query": "SELECT id, name FROM users ORDER BY id ASC LIMIT 2;"},
        )
        assert result["success"] is True
        assert result["columns"] == ["id", "name"]
        assert len(result["rows"]) == 2
        assert result["rows"][0][1] == "Alice Smith"
        assert result["is_truncated"] is False
        assert result["execution_time_ms"] >= 0

    @pytest.mark.anyio
    async def test_execute_query_tool_blob_sanitization(self, mcp_server: FastMCP) -> None:
        contents, result = await mcp_server.call_tool(
            "execute_query",
            {"query": "SELECT avatar, bio FROM users WHERE id = 1;"},
        )
        assert result["success"] is True
        row = result["rows"][0]
        assert row[0].startswith("<BLOB ")
        assert row[1].endswith("... [truncated]")

    @pytest.mark.anyio
    async def test_execute_query_tool_security_rejection(self, mcp_server: FastMCP) -> None:
        contents, result = await mcp_server.call_tool(
            "execute_query",
            {"query": "DROP TABLE users;"},
        )
        assert result["success"] is False
        assert "forbidden" in result["error"].lower()

    @pytest.mark.anyio
    async def test_execute_query_tool_sql_syntax_error(self, mcp_server: FastMCP) -> None:
        contents, result = await mcp_server.call_tool(
            "execute_query",
            {"query": "SELECT FROM users;"},
        )
        assert result["success"] is False
        assert "syntax error" in result["error"].lower()


class TestFastMCPResources:
    """Verifies resource retrieval."""

    @pytest.mark.anyio
    async def test_read_schema_resource(self, mcp_server: FastMCP) -> None:
        resources = await mcp_server.read_resource("sqlite://schema")
        assert len(resources) == 1
        content = resources[0].content
        assert "# Database Schema" in content
        assert "## Table: `users`" in content
        assert "## Table: `orders`" in content
        assert "## View: `order_summary`" in content


class TestFastMCPPrompts:
    """Verifies pre-engineered prompt rendering."""

    @pytest.mark.anyio
    async def test_analyze_schema_prompt(self, mcp_server: FastMCP) -> None:
        prompt_res = await mcp_server.get_prompt("analyze_schema", {"focus": "indexes"})
        assert len(prompt_res.messages) == 1
        prompt_text = prompt_res.messages[0].content.text
        assert "indexes" in prompt_text
        assert "Database Schema" in prompt_text
        assert "Review Guidelines" in prompt_text
