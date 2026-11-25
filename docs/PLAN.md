# PLAN.md — Complete Technical Implementation & Strategy Plan

## 1. System Architecture & Module Structure

The project follows a modular, low-overhead Python structure:

```
Read-Only-SQLite-MCP-Server/
├── README.md
├── SECURITY.md
├── pyproject.toml
├── GEMINI.md
├── mcp_config.json
├── docs/
│   ├── PLAN.md
│   ├── ROADMAP.md
│   ├── SCENARIO.md
│   ├── TESTING.md
│   └── HISTORY.md
├── .github/
│   └── workflows/
│       └── ci.yml
├── src/
│   └── sqlite_mcp/
│       ├── __init__.py
│       ├── server.py        # Entry point, FastMCP initialization, CLI arg parsing
│       ├── db.py            # SQLite connection, authorizer hook, execution engine
│       ├── security.py      # SQLite authorizer callback & SQL sanitizer
│       ├── tools.py         # MCP tool handler definitions
│       ├── resources.py     # MCP resource provider definitions
│       └── prompts.py       # MCP prompt templates
└── tests/
    ├── conftest.py
    ├── fixtures/
    ├── test_fixtures.py
    ├── test_security.py    # Unit tests for read-only security authorizer
    ├── test_db.py          # Unit tests for SQLite reader engine & BLOB handling
    ├── test_mcp_tools.py   # E2E integration tests for MCP tools
    └── test_server_stdio.py # Subprocess stdio JSON-RPC lifecycle tests
```

---

## 2. Architectural Design Details

### 2.1 Native Engine Authorizer Security (`security.py`)
Rather than maintaining a custom regex or complex AST parser, `security.py` uses SQLite's native `set_authorizer` C API exposed by Python's `sqlite3` driver:

```python
import sqlite3

# Native SQLite Action Codes to DENY (excerpt — see src/sqlite_mcp/security.py for full list)
FORBIDDEN_ACTIONS = {
    sqlite3.SQLITE_INSERT,
    sqlite3.SQLITE_UPDATE,
    sqlite3.SQLITE_DELETE,
    sqlite3.SQLITE_DROP_TABLE,
    sqlite3.SQLITE_DROP_INDEX,
    sqlite3.SQLITE_DROP_VIEW,
    sqlite3.SQLITE_CREATE_TABLE,
    sqlite3.SQLITE_CREATE_INDEX,
    sqlite3.SQLITE_CREATE_VIEW,
    sqlite3.SQLITE_CREATE_VTABLE,
    sqlite3.SQLITE_DROP_VTABLE,
    sqlite3.SQLITE_ALTER_TABLE,
    sqlite3.SQLITE_ATTACH,
    sqlite3.SQLITE_DETACH,
    sqlite3.SQLITE_REINDEX,
    sqlite3.SQLITE_ANALYZE,
    sqlite3.SQLITE_TRANSACTION,
    sqlite3.SQLITE_SAVEPOINT,
}

def read_only_authorizer(action_code, arg1, arg2, db_name, trigger_name):
    """Strict native C-level authorizer callback for user query execution."""
    if action_code in FORBIDDEN_ACTIONS:
        return sqlite3.SQLITE_DENY
    if action_code == sqlite3.SQLITE_PRAGMA:
        pragma_name = (arg1 or "").lower()
        if pragma_name in SAFE_READ_TABLE_PRAGMAS:
            return sqlite3.SQLITE_OK
        if pragma_name in SAFE_READ_GLOBAL_PRAGMAS and arg2 is None:
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK
```

(`introspection_authorizer` wraps `read_only_authorizer` strictly for internal schema queries to accommodate an internal `SQLITE_UPDATE` callback on `sqlite_master` observed on SQLite 3.40.1.)

### 2.2 Connection Management & Resilience (`db.py`)
* Connection setup: `sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True, timeout=10.0)`.
* Register `conn.set_authorizer(read_only_authorizer)` for user queries; `conn.set_authorizer(introspection_authorizer)` for internal metadata introspection.
* Execute `PRAGMA query_only = ON;`.
* On Python 3.11+, enforce in-engine memory limit: `conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, max_value_length)`.
* **BLOB & Data Formatting:** Convert query tuples using a custom row sanitizer:
  - `bytes` -> `f"<BLOB {len(val)} bytes>"`
  - `None` -> `None` (JSON `null`)
  - Strings $> 500$ chars -> `val[:500] + "... [truncated]"`
* Register step progress handler: `conn.set_progress_handler(progress_callback, step)` to abort queries executing more than `SQLITE_MAX_INSTRUCTIONS` virtual VM instructions (preventing infinite loops or unindexed Cartesian joins).

### 2.3 FastMCP Server Protocol (`server.py` & `tools.py`)
Using `from mcp.server.fastmcp import FastMCP`:
* **CLI Argument Parsing:** Parse `--db-path` on startup with fallback to environment variable `SQLITE_DB_PATH`.
* **Logging Setup:** Redirect all logger outputs explicitly to `sys.stderr` (`logging.StreamHandler(sys.stderr)`).
* **Graceful Failures:** Catch `sqlite3.Error` and `PermissionError` cleanly, returning formatted JSON errors back to the AI model without breaking the JSON-RPC pipe.

---

## 3. Engineering Mindset & Principles

1. **Textbook Native Security Over Custom Parsers:**
   * Leverage SQLite's built-in `set_authorizer()` and `PRAGMA query_only`. Native engine hooks cannot be bypassed by SQL comment tricks or string obfuscation.
2. **Strict Protocol Hygiene:**
   * **`print()` statements anywhere in stdout will corrupt the JSON-RPC wire format.** All logging must go to `sys.stderr`.
3. **Data Safety in Serialization:**
   * Always sanitize raw database outputs before passing them to JSON serializers. Never assume database values are clean UTF-8 strings.
4. **Deterministic & Fast:**
   * Fast startup (<100ms), low memory footprint, zero network calls.

---

## 4. Phase-by-Phase Task Breakdown

### Phase 1: Environment & Test Database Fixture
- [x] Initialize Python project with `pyproject.toml` (dependencies: `mcp>=1.0.0,<2.0.0`, `pydantic>=2.0.0`, `pytest`).
- [x] Create test SQLite generator (`tests/fixtures/create_sample_db.py`) populated with tables (`users`, `orders`, `products`), BLOB data, foreign keys, and indexes (extended in Milestone 10 with `audit_logs` implicit PK FK and expression index).

### Phase 2: Security & Engine Driver Implementation
- [x] Develop `security.py`: Native `set_authorizer` callback and statement prefix checker.
- [x] Write `test_security.py`: Verify rejection of `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `ATTACH`, and `PRAGMA` write calls.
- [x] Develop `db.py`: Connection manager with URI read-only mode, step-count limit handler, and BLOB/cell truncation formatter.

### Phase 3: FastMCP Tools, Resources & Prompts
- [x] Build `list_tables` tool handler using `@mcp.tool()`.
- [x] Build `describe_table` tool handler with full column definitions, constraints, and raw DDL.
- [x] Build `execute_query` tool handler with safe JSON formatting and row limits.
- [x] Build `sqlite://schema` resource using `@mcp.resource()`.
- [x] Build `analyze_schema` prompt template using `@mcp.prompt()`.

### Phase 4: Stdio Wiring & CLI Integration
- [x] Implement `server.py` entry point with `argparse` for `--db-path` and FastMCP execution.
- [x] Ensure all logging routes exclusively to `sys.stderr`.
- [x] Write integration tests for JSON-RPC communication over stdio.

### Phase 5: Antigravity Config & Final Verification
- [x] Configure local `mcp_config.json` for Antigravity integration.
- [x] Perform real-world verification via agent chat.
- [x] Document final setup instructions in `README.md`.

### Phase 6: Post-Review Hardening & Engine Precision
- [x] Implement RFC 3986 URI percent-encoding via `Path.resolve().as_uri() + "?mode=ro"` in `db.py`.
- [x] Switch schema introspection to parameterized table-valued PRAGMAs (`pragma_table_info(?)`, `pragma_foreign_key_list(?)`, `pragma_index_list(?)`, `pragma_index_info(?)`).
- [x] Isolate instruction limiter state per query and expose `SQLITE_MAX_INSTRUCTIONS` configuration.
- [x] Refine `pyproject.toml` dependency bound to `mcp>=1.3.0,<2.0.0` and add `pytest-cov`.
- [x] Add unit tests for special characters in paths, apostrophe-containing identifiers, and limiter isolation.
- [x] Update `GEMINI.md` with URI encoding, table-valued PRAGMA, and claims discipline rules.

### Phase 7: Production Layer Isolation, Bracket Grammar & Repo Polish
- [x] Directly test Layer 1 URI isolation on `mgr.get_connection()` with authorizer and query-only cleared.
- [x] Fix square bracket grammar in `has_stacked_statements` to close strictly on first `]`.
- [x] Add negative stacked statement test cases for bracket and backtick identifiers.
- [x] Emit `sys.stderr` warning on invalid `SQLITE_MAX_INSTRUCTIONS` values.
- [x] Remove dead code (`QueryInstructionLimiter.reset()`).
- [x] Reorganize documentation into `docs/` and add `.github/workflows/ci.yml` and `SECURITY.md`.

### Phase 8: CI Matrix Isolation, Pin Verification & Security Boundary Tightening
- [x] Configure CI workflow to use `actions/setup-python@v5`, logging `python --version` and adding a minimum bound test job.
- [x] Empirically verify `mcp>=1.22.0,<2.0.0` as the verified lower bound for structured output schemas and Pydantic compatibility.
- [x] Fence database schema markdown and sanitize prompt focus in `prompts.py`.
- [x] Tighten `SECURITY.md` terminology (bounding response size, database-wide scope, untrusted prompt schema).
- [x] Link `docs/SCENARIO.md` in `README.md`.

### Phase 9: Windows Python 3.10 Engine Compatibility & Dynamic Prompt Fencing
- [x] Permit internal schema updates on `sqlite_master` in `security.py` for older bundled SQLite (3.40.1).
- [x] Fix Python 3.10 `set_authorizer(None)` issue in `test_db.py` via `set_authorizer(lambda *args: sqlite3.SQLITE_OK)`.
- [x] Implement dynamic multi-backtick fencing in `src/sqlite_mcp/prompts.py`.
- [x] Add dynamic fence test `test_analyze_schema_prompt_dynamic_fence_with_backticks` in `tests/test_mcp_tools.py`.
- [x] Clarify structural formatting vs semantic injection in `SECURITY.md`.

### Phase 10: Schema Introspection Hardening, Memory DoS Defense & Authorizer Separation
- [x] Support implicit PK foreign keys (`ForeignKeyInfo.to_column: Optional[str]`) and expression/rowid index labels (`"<expression>"`, `"<rowid>"`).
- [x] Add `audit_logs` and expression index fixtures to `tests/fixtures/create_sample_db.py` and case-insensitive `COLLATE NOCASE` lookup in `describe_table`.
- [x] Enforce memory value limit (`SQLITE_MAX_VALUE_LENGTH` via `conn.setlimit(SQLITE_LIMIT_LENGTH, ...)`) on Python 3.11+ and document Python 3.10 boundary.
- [x] Separate strict user-query `read_only_authorizer` from `introspection_authorizer` (`for_introspection=True`), and return clear instruction-limit abort errors.
- [x] Escape single quotes in prompt `focus` parameter and align `SECURITY.md`, `TESTING.md`, `README.md`, and `mcp_config.json`.

### Phase 11: MCP Tool Annotations, M8ven Verification & Repo Polish
- [x] Add explicit MCP `ToolAnnotations` (`readOnlyHint=True`, `destructiveHint=False`, `idempotentHint=True`, `openWorldHint=False`) to `list_tables`, `describe_table`, and `execute_query`.
- [x] Verify `ToolAnnotations` presence via both `FastMCP.list_tools()` and live stdio `tools/list`.
- [x] Add `SQLITE_CREATE_VTABLE`, `SQLITE_DROP_VTABLE`, and `SQLITE_TRANSACTION` to `FORBIDDEN_ACTIONS` in `src/sqlite_mcp/security.py` with unit tests.
- [x] Add M8ven ownership badge to `README.md`, ignore `.venv*/` in `.gitignore`, and resolve stale doc references.