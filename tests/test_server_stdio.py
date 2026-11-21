"""Integration tests for CLI argument parsing and Stdio JSON-RPC server lifecycle."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import pytest

from sqlite_mcp.server import parse_arguments


class TestArgumentParser:
    """Verifies CLI argument handling and environment variable fallbacks."""

    def test_explicit_db_path(self) -> None:
        args = parse_arguments(["--db-path", "sample.db", "--log-level", "DEBUG"])
        assert args.db_path == "sample.db"
        assert args.log_level == "DEBUG"

    def test_env_var_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SQLITE_DB_PATH", "env_sample.db")
        args = parse_arguments([])
        assert args.db_path == "env_sample.db"

    def test_missing_db_path_exits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SQLITE_DB_PATH", raising=False)
        with pytest.raises(SystemExit):
            parse_arguments([])


class TestStdioSubprocessServer:
    """Verifies end-to-end JSON-RPC 2.0 communication over standard input/output."""

    def test_stdio_jsonrpc_lifecycle(self, sample_db_path: Path) -> None:
        proc = subprocess.Popen(
            [sys.executable, "-m", "sqlite_mcp.server", "--db-path", str(sample_db_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        try:
            # 1. MCP initialize handshake
            init_req = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test-runner", "version": "1.0.0"},
                },
            }
            proc.stdin.write(json.dumps(init_req) + "\n")
            proc.stdin.flush()

            init_resp_line = proc.stdout.readline()
            assert init_resp_line, "Expected JSON-RPC response from server"
            init_data = json.loads(init_resp_line)
            assert init_data["id"] == 1
            assert init_data["result"]["serverInfo"]["name"] == "sqlite-explorer"

            # 2. initialized notification
            proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
            proc.stdin.flush()

            # 3. tools/list request
            tools_req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
            proc.stdin.write(json.dumps(tools_req) + "\n")
            proc.stdin.flush()

            tools_resp_line = proc.stdout.readline()
            tools_data = json.loads(tools_resp_line)
            tool_names = [t["name"] for t in tools_data["result"]["tools"]]
            assert "list_tables" in tool_names
            assert "describe_table" in tool_names
            assert "execute_query" in tool_names

            # 4. tools/call request for list_tables
            call_req = {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "list_tables", "arguments": {}},
            }
            proc.stdin.write(json.dumps(call_req) + "\n")
            proc.stdin.flush()

            call_resp_line = proc.stdout.readline()
            call_data = json.loads(call_resp_line)
            assert call_data["id"] == 3
            text_result = call_data["result"]["content"][0]["text"]
            parsed_result = json.loads(text_result)
            assert parsed_result["success"] is True
            table_names = [t["name"] for t in parsed_result["tables"]]
            assert "users" in table_names
            assert "products" in table_names

            # 5. tools/call request for execute_query
            query_req = {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "execute_query",
                    "arguments": {"query": "SELECT count(*) as total FROM users;"},
                },
            }
            proc.stdin.write(json.dumps(query_req) + "\n")
            proc.stdin.flush()

            query_resp_line = proc.stdout.readline()
            query_data = json.loads(query_resp_line)
            assert query_data["id"] == 4
            query_result = json.loads(query_data["result"]["content"][0]["text"])
            assert query_result["success"] is True
            assert query_result["columns"] == ["total"]
            assert query_result["rows"][0][0] == 3

        finally:
            proc.terminate()
            stdout_rem, stderr_data = proc.communicate(timeout=5)

            # Stdio hygiene verification: All server log strings must have gone to stderr
            assert "Initializing SQLite MCP Server" in stderr_data
            assert "Starting FastMCP stdio transport listener" in stderr_data
