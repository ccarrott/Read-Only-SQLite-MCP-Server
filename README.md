# Safe Read-Only SQLite Explorer MCP Server

A safe SQLite database inspection and exploration server built on the Model Context Protocol (MCP) using `FastMCP`.

Enables AI coding assistants and autonomous agents (such as Antigravity, Cursor, and Claude Desktop) to inspect schemas, execute analytical queries, and review data models with strict, multi-layer read-only guarantees.

---

## 1. Multi-Layer Security Model

To prevent accidental data corruption, unauthorized mutations, or Denial-of-Service through unindexed Cartesian joins, the server enforces a strict **4-Layer Defense**:

| Defense Layer | Mechanism | Protection Scope |
| --- | --- | --- |
| **Layer 1: Driver / OS** | Percent-Encoded URI Read-Only Mode (`mode=ro`, `uri=True`) | Blocks write operations at the SQLite VFS / OS file descriptor level. Uses RFC 3986 percent-encoding to prevent delimiter attacks via `#`, `?`, or `%` characters in paths. |
| **Layer 2: Engine Authorizer** | C Authorizer Hook (`conn.set_authorizer`) | Denies `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `ATTACH`, and `PRAGMA` write actions directly inside the SQLite engine parser before query planning. |
| **Layer 3: Pragma Enforcement** | `PRAGMA query_only = ON;` | Enforces query-only mode at the database engine level upon connection creation. |
| **Layer 4: Query Sanitizer** | Leading Statement Validation | Enforces that queries strictly begin with `SELECT`, `EXPLAIN`, or `WITH`, and denies stacked or multi-statement query injections. |

### Additional Safeguards:
* **Progress Handler Step Limit (CPU DoS):** Automatically interrupts runaway queries (e.g., infinite recursive CTEs or unindexed Cartesian joins) exceeding virtual machine instruction limits (`SQLITE_MAX_INSTRUCTIONS`, default 10,000,000).
* **Value Length Limiting (Memory DoS):** Enforces an in-engine ceiling on string and blob sizes via `conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, ...)` (`SQLITE_MAX_VALUE_LENGTH`, default 10,000,000 bytes) on Python 3.11+. Python 3.10 relies on host process memory limits.
* **BLOB & Data Serialization Protection:** Formats raw binary data (`bytes`) as `<BLOB N bytes>` to prevent JSON-RPC serialization crashes (`TypeError`).
* **Result Ceiling:** Automatically truncates text fields over 500 characters (`... [truncated]`) and enforces row ceilings (default 100, max 1000).
* **Parameterized Schema Introspection:** Uses SQLite's table-valued PRAGMA functions (`pragma_table_info(?)`, `pragma_foreign_key_list(?)`, `pragma_index_list(?)`) with bound parameters to eliminate escaping issues on identifiers with apostrophes.

---

## 2. Capabilities

### Tools
* **`list_tables`**: Lists all user tables, views, and index counts within the SQLite database.
* **`describe_table`**: Returns detailed column definitions (column name, data type, nullability, defaults, primary key flags), foreign key constraints, indexes, and raw `CREATE TABLE` DDL.
* **`execute_query`**: Executes read-only SQL queries (`SELECT`, `EXPLAIN`, `WITH`) under strict pagination and formatting limits. Returns formatted JSON along with execution timing.

### Resources
* **`sqlite://schema`**: Dynamic Markdown resource summarizing the entire database structure, tables, columns, constraints, foreign keys, indexes, and raw DDL for rapid LLM absorption.

### Prompts
* **`analyze_schema`**: Structured DBA review prompt guiding the model to evaluate normalization, index coverage, foreign key completeness, and query optimization opportunities.

---

## 3. Installation & Setup

### Prerequisites
* Python 3.10+
* `uv` or standard Python `venv`

### Setup with `uv` (Recommended)
```bash
# Clone the repository and navigate to the directory
cd Read-Only-SQLite-MCP-Server

# Create a virtual environment and install dependencies
uv venv .venv
uv pip install -e ".[dev]"
```

### Generate Sample Database
```bash
python tests/fixtures/create_sample_db.py -o sample.db
```

---

## 4. Running the Server

### Command Line
Run over standard I/O (`stdio`):
```bash
python -m sqlite_mcp.server --db-path ./sample.db
```

Alternatively, supply the database path via environment variable:
```bash
export SQLITE_DB_PATH="./sample.db"
python -m sqlite_mcp.server
```

### Logging Protocol
* `stdout` is reserved strictly for JSON-RPC 2.0 protocol packets.
* All server diagnostics, startup messages, and error traces route exclusively to `sys.stderr`.

---

## 5. Antigravity & MCP Client Integration

Add the server to your MCP client configuration (e.g., `mcp_config.json`):

```json
{
  "mcpServers": {
    "sqlite-explorer": {
      "command": "python",
      "args": [
        "-m",
        "sqlite_mcp.server",
        "--db-path",
        "/absolute/path/to/your/database.db"
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

---

## 6. Automated Test Suite

Run the full automated test suite covering security authorizers, data sanitization, FastMCP tool contracts, and stdio JSON-RPC lifecycle:

```bash
pytest -v
```

The test suite verifies:
* Tested mutation vectors (`DROP`, `INSERT`, `UPDATE`, `ALTER`, `ATTACH`, `PRAGMA write`) are caught and rejected.
* Layer 1 OS/VFS `mode=ro` protection is verified in isolation with percent-encoded URIs.
* Multi-statement query injection is denied across all quoting styles (single quotes, double quotes, brackets, and backticks).
* BLOBs and long strings serialize without errors.
* Runaway loops and unindexed Cartesian joins trigger virtual machine instruction limit interrupts.
* End-to-end stdio subprocess handshake passes without protocol corruption.

---

## 7. Architecture & Documentation

Detailed project architecture, testing strategies, and change logs are organized in the `docs/` directory:

* [`docs/SCENARIO.md`](docs/SCENARIO.md) — Requirements, constraints, security boundaries, and product definition.
* [`docs/PLAN.md`](docs/PLAN.md) — Architectural design, module layout, and implementation breakdown.
* [`docs/ROADMAP.md`](docs/ROADMAP.md) — Project milestones, execution stages, and verification criteria.
* [`docs/TESTING.md`](docs/TESTING.md) — Test suite design, edge-case testing matrices, and agent verification checklists.
* [`docs/HISTORY.md`](docs/HISTORY.md) — Chronological development ledger, architectural decisions, and review resolutions.
* [`SECURITY.md`](SECURITY.md) — Security policy, 4-layer defense breakdown, threat model, and vulnerability reporting.
