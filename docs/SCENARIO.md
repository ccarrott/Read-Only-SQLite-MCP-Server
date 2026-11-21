# SCENARIO.md — Safe Read-Only SQLite Explorer MCP Server

## 1. Executive Summary & Context
Modern AI coding assistants and autonomous agents (such as Antigravity, Cursor, and Claude Desktop) frequently need to inspect local databases to understand schema designs, verify data states, debug queries, or answer data-driven questions. However, granting an AI unchecked database access introduces significant risks: accidental table drops, corrupting data via rogue `UPDATE`/`DELETE` statements, or locking up the application with unindexed, expensive queries.

This project creates a **Safe Read-Only SQLite Explorer MCP Server**. Built using Python and the official Model Context Protocol SDK (`FastMCP`) over standard I/O (`stdio`), it exposes database inspection capabilities to any MCP-compliant client while enforcing strict, multi-layered read-only security boundaries.

---

## 2. Target Audience & System Role
* **Primary Client:** Antigravity Agent (and other MCP host applications).
* **Role in Architecture:** Middleware bridge between the AI model and local SQLite `.db` / `.sqlite` files.
* **Cost Profile:** $0 runtime cost. Operates locally via standard Python libraries and local process I/O.

---

## 3. Key Functional Features

### 3.1 Core Tools (Callable by AI Agent)
1. **`list_tables`**
   * Returns a clean JSON list of all user tables, views, and index counts within the target SQLite database.
   * Excludes internal SQLite metadata tables (e.g., `sqlite_sequence`, `sqlite_stat1`) unless explicitly requested.
2. **`describe_table`**
   * Accepts a `table_name` parameter.
   * Returns detailed column definitions (column name, data type, `NOT NULL` constraints, default values, primary key flag) along with foreign key relationships and index structures.
   * Returns the raw `CREATE TABLE` DDL for exact schema fidelity.
3. **`execute_query`**
   * Accepts a SQL query string.
   * Executes the query under strict read-only guarantees and returns formatted results.
   * Implements automatic pagination/row-limiting (default 100 rows, max 1000 rows) and string/BLOB truncation for large fields to prevent flooding the AI context window.

### 3.2 Core Resources (Context Provided to AI Agent)
1. **`sqlite://schema`**
   * A dynamic MCP Resource that formats the entire database schema into a single, clean Markdown document, allowing the AI agent to absorb database structure in a single context read.

### 3.3 Core Prompts (Pre-engineered Agent Templates)
1. **`analyze_schema`**
   * Formats a guided prompt for the AI to review normalization, missing indexes, missing foreign key constraints, and potential query optimization bottlenecks.

---

## 4. Hard Constraints & Security Requirements

1. **Immutable Read-Only Guarantee (4-Layer Defense):**
   * **Layer 1 (OS/Driver):** Open SQLite connection in URI read-only mode (`Path.resolve().as_uri() + "?mode=ro"`, `uri=True`).
   * **Layer 2 (Engine Authorizer):** Register native SQLite C-level authorizer (`conn.set_authorizer`) to reject `SQLITE_INSERT`, `SQLITE_UPDATE`, `SQLITE_DELETE`, `SQLITE_DROP_TABLE`, `SQLITE_ALTER_TABLE`, `SQLITE_ATTACH`, and `SQLITE_PRAGMA` write operations at the engine level.
   * **Layer 3 (Pragma Enforcement):** Execute `PRAGMA query_only = ON;` immediately upon connection setup.
   * **Layer 4 (Statement Inspection):** Normalize SQL strings to verify leading statement type is `SELECT`, `EXPLAIN`, or `WITH`.

2. **Data & Context Hygiene:**
   * **BLOB & Binary Handling:** Convert raw `bytes` data to a safe representation (`<BLOB N bytes>`) to prevent JSON serialization crashes (`TypeError: Object of type bytes is not JSON serializable`).
   * **Result Ceiling:** Hard limit of 1,000 rows max. Text cells capped at 500 characters.

3. **Stdio Protocol Hygiene:**
   * `stdout` is reserved strictly for raw MCP JSON-RPC protocol packets.
   * **Zero standard prints allowed.** All logging, debug outputs, and errors must be directed to `sys.stderr`.

4. **Zero Cloud Dependencies:**
   * Standard Python 3.10+ standard library (`sqlite3`, `sys`, `typing`, `logging`, `pathlib`, `argparse`) plus lightweight `mcp` SDK (`FastMCP`) and `pydantic`.

---

## 5. Definition of Done (Final Product)
* A single executable Python package (`sqlite_mcp`) that boots cleanly via CLI arguments (`--db-path`) or `mcp_config.json`.
* Comprehensive test suite verifying security gatekeeping (rejecting mutation attempts cleanly via engine authorizer and URI read-only mode).
* Zero hanging processes, context crashes, or unhandled exceptions on invalid SQL queries or binary data.
* Comprehensive documentation in `README.md` showing how to register the server in Antigravity.