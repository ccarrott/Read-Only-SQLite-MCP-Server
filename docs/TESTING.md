# TESTING.md — Testing Strategy & Verification Protocols

This document outlines the test suite structure, edge-case scenarios, and manual verification steps required to validate the MCP server.

## 1. Automated Test Suites

### 1.1 Native Security Authorizer Tests (`tests/test_security.py`)

Verifies that SQLite's native `set_authorizer` callback blocks all data-modifying or schema-altering SQL statements at the database engine level.

| Test Case | Input Query | Expected Result | 
| ----- | ----- | ----- | 
| **Standard Select** | `SELECT * FROM users` | PASS | 
| **CTE Select** | `WITH summary AS (SELECT * FROM orders) SELECT * FROM summary` | PASS | 
| **Explain Query** | `EXPLAIN QUERY PLAN SELECT * FROM users` | PASS | 
| **Direct Delete** | `DELETE FROM users WHERE id = 1` | REJECT (Engine Authorizer Deny) | 
| **Direct Drop** | `DROP TABLE users` | REJECT (Engine Authorizer Deny) | 
| **Direct Insert** | `INSERT INTO users (name) VALUES ('test')` | REJECT (Engine Authorizer Deny) | 
| **Direct Update** | `UPDATE users SET name = 'test'` | REJECT (Engine Authorizer Deny) | 
| **Alter Table** | `ALTER TABLE users ADD COLUMN age INT` | REJECT (Engine Authorizer Deny) | 
| **PRAGMA Write** | `PRAGMA writable_schema = ON` | REJECT (Engine Authorizer Deny) | 
| **Attach Database** | `ATTACH DATABASE 'other.db' AS other` | REJECT (Engine Authorizer Deny) | 
| **Virtual Table** | `CREATE VIRTUAL TABLE v USING fts5(x)` | REJECT (Statement / Authorizer Deny) | 
| **Transaction Control** | `BEGIN TRANSACTION` | REJECT (Statement / Authorizer Deny) | 
| **Stacked Statement** | `SELECT * FROM users; DROP TABLE orders;` | REJECT (Multi-Statement Deny) | 

Also verifies strict authorizer isolation (`read_only_authorizer` denies `SQLITE_UPDATE` even on internal schema tables and denies `SQLITE_CREATE_VTABLE`, `SQLITE_DROP_VTABLE`, and `SQLITE_TRANSACTION`) versus `introspection_authorizer` (allows internal `SQLITE_UPDATE` on `sqlite_master` while denying user table writes).

### 1.2 Database Engine & Data Safety Tests (`tests/test_db.py`)

Verifies execution behavior against real SQLite files and edge-case data types.

* **Read-Only Enforcement:** Executing writes on a connection opened by `db.py` must raise `sqlite3.OperationalError: attempt to write a readonly database` or `sqlite3.DatabaseError: not authorized` (and attempting `WITH t AS (SELECT 1) UPDATE sqlite_master ...` fails leaving schema unchanged).

* **Case-Insensitive Table Lookup:** `describe_table("USERS")` resolves canonical table name `users` via `COLLATE NOCASE`.

* **Memory Value Length Limit:** On Python 3.11+, `conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, ...)` rejects oversized values (`zeroblob(5000)` under a 1,000-byte cap) with `"string or blob too big"`. Configurable via `SQLITE_MAX_VALUE_LENGTH`.

* **BLOB Serialization Protection:** Tables containing raw `bytes` binary columns must return `<BLOB N bytes>` strings without throwing JSON `TypeError`.

* **Row Limit Truncation:** Queries returning 5,000 rows must be truncated cleanly to 100 rows (or user-specified limit up to 1,000).

* **Cell Truncation:** Text fields exceeding 500 characters must be truncated with `... [truncated]`.

* **Progress Handler Instruction Limit:** Long-running queries (e.g., recursive CTEs or unindexed Cartesian joins) must trigger `sqlite3.OperationalError: Query aborted: instruction limit exceeded` via the VM step progress handler.

### 1.3 FastMCP Tool Tests (`tests/test_mcp_tools.py`)

Verifies JSON-RPC tool contracts.

* All three tools (`list_tables`, `describe_table`, `execute_query`) expose explicit `ToolAnnotations`: `readOnlyHint=True`, `destructiveHint=False`, `idempotentHint=True`, `openWorldHint=False`.

* `list_tables()` returns clean JSON listing all user tables and views.

* `describe_table(table_name="users")` returns column definitions, constraints, foreign keys, and raw DDL (case-insensitive via `COLLATE NOCASE`). Handles implicit foreign keys (`to = NULL`) and expression indexes (`name = NULL` -> `"<expression>"`).

* `execute_query(query="SELECT 1")` returns formatted JSON payload with execution timing.

* `read_resource(uri="sqlite://schema")` returns full database schema markdown.

* `get_prompt(name="analyze_schema")` formats DBA audit review prompt with dynamic multi-backtick fencing and whitespace/single-quote sanitization.

### 1.4 Stdio Server Lifecycle Tests (`tests/test_server_stdio.py`)

Verifies host process execution, CLI parsing, and protocol wire fidelity.

* `parse_arguments` validates `--db-path`, environment variable `SQLITE_DB_PATH`, and `--log-level`.

* Subprocess execution over stdin/stdout handles standard JSON-RPC 2.0 lifecycle:
  1. `initialize`
  2. `notifications/initialized`
  3. `tools/list` (including `annotations` object verification)
  4. `tools/call` for `list_tables` and `execute_query`

* Stdio hygiene verification: Confirms `stdout` contains only JSON-RPC packets while all logging statements write to `stderr`.

## 2. Manual Integration Verification with Antigravity

### 2.1 Sample `mcp_config.json` Configuration

Add the server entry to your local Antigravity MCP configuration:

```json
{
  "mcpServers": {
    "sqlite-explorer": {
      "command": "python",
      "args": [
        "-m",
        "sqlite_mcp.server",
        "--db-path",
        "/absolute/path/to/sample.db"
      ],
      "env": {
        "LOG_LEVEL": "INFO",
        "SQLITE_MAX_INSTRUCTIONS": "10000000",
        "SQLITE_MAX_VALUE_LENGTH": "10000000"
      }
    }
  }
}
```

### 2.2 Agent Interaction Verification Checklist

Prompt the Antigravity agent with the following checklist in chat:

1. *"What tables exist in the database?"* (Triggers `list_tables`)

2. *"Can you describe the schema for the `users` table?"* (Triggers `describe_table`)

3. *"Show me the 5 most recent orders."* (Triggers `execute_query`)

4. *"Try deleting user with ID 1."* (Verifies agent receives native engine security rejection error gracefully)