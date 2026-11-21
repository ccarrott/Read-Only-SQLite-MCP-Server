# HISTORY.md — Development Ledger & Decision Log

All updates, technical decisions, debugging attempts, and milestone completions are recorded chronologically in this document.

---

## [Initial Blueprint & Refinement] — Architecture Finalized

### Context & Requirements
Initiated project setup for **Safe Read-Only SQLite Explorer MCP Server**. Established a Markdown-driven development framework to enable clean implementation and debugging.

### Documents Created & Refined
* `SCENARIO.md`: Detailed functional requirements, constraints, security guardrails, BLOB handling, and product definition.
* `PLAN.md`: Formulated system architecture, SQLite authorizer integration, Python module layout, and task breakdown.
* `ROADMAP.md`: Mapped out 5 sequential project milestones from foundation to Antigravity E2E verification.
* `GEMINI.md`: Defined the practical, ponytail-style senior developer persona, protocol rules (`stdout` vs `stderr`), and engineering standards.
* `TESTING.md`: Defined test suite structure, SQL mutation injection vectors, and BLOB/timeout edge cases.
* `HISTORY.md`: Initialized active development log.

### Key Architectural Decisions
1. **Native Engine Security over AST Parsing:** Replaced custom SQL regex/AST parsers with SQLite's native C-level `conn.set_authorizer()` callback hook. This natively blocks `SQLITE_INSERT`, `SQLITE_UPDATE`, `SQLITE_DELETE`, `SQLITE_DROP_TABLE`, `SQLITE_ALTER_TABLE`, `SQLITE_ATTACH`, and `SQLITE_PRAGMA` write actions directly at the database engine level.
2. **BLOB & Data Formatting Strategy:** Enforced raw `bytes` truncation (`<BLOB N bytes>`) in `db.py` to prevent JSON serialization crashes (`TypeError`) when returning query results.
3. **FastMCP Integration:** Standardized on `FastMCP` from the official `mcp` SDK to reduce boilerplate for tool and resource definitions.
4. **CLI Argument Parsing:** Added `--db-path` CLI argument parsing in `server.py` with fallback to `SQLITE_DB_PATH` environment variable.
5. **Title Consistency Audit:** Verified all blueprint document headers match their exact file paths (`TITLE.md:TITLE.md`).

---

## [Completed] — Milestone 0: Environment & Test Harness Implementation

### Accomplishments
* Initialized Python project environment using Python 3.12 and `uv`.
* Created `pyproject.toml` with `mcp>=1.0.0,<2.0.0`, `pydantic>=2.0.0`, and `pytest>=7.0.0`. Pinning `mcp<2` ensures compatibility with the standardized `from mcp.server.fastmcp import FastMCP` API.
* Implemented `tests/fixtures/create_sample_db.py` producing a normalized SQLite test database with `users`, `products`, `orders`, foreign key constraints, indexes, views (`order_summary`), and binary `BLOB` fields.
* Implemented `tests/conftest.py` with pytest fixture `sample_db_path`.
* Implemented and executed `tests/test_fixtures.py` verifying schema generation, views, indexes, foreign keys, and binary data.

### Verification Results
* Command: `pytest -v`
* Result: 1 passed in 0.10s.

---

## [Completed] — Milestone 1: Secure SQLite Core Driver

### Accomplishments
* Developed `src/sqlite_mcp/security.py`:
  - Implemented `read_only_authorizer` leveraging SQLite C authorizer actions to deny mutations (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `ATTACH`, `PRAGMA write`).
  - Added whitelist of safe inspection pragmas (`table_info`, `foreign_key_list`, `index_list`, `query_only`).
  - Implemented `validate_sql_statement` enforcing allowed leading query types (`SELECT`, `EXPLAIN`, `WITH`) and blocking stacked / multi-statement queries while correctly preserving semicolons inside string literals and trailing comments.
* Developed `src/sqlite_mcp/db.py`:
  - Implemented `DatabaseManager` with 4-layer defense: URI read-only mode (`mode=ro`), native authorizer hook, `PRAGMA query_only = ON;`, and statement validation.
  - Implemented `QueryInstructionLimiter` with step-based progress handler aborting runaway infinite queries or Cartesian joins.
  - Implemented cell and row sanitization: `<BLOB N bytes>` representation for binary types, 500-char string truncation, JSON-safe handling of `None`/`null`.
  - Added `list_tables`, `describe_table`, and `get_database_schema_markdown` introspection methods.
* Authored and executed unit test suites `tests/test_security.py` and `tests/test_db.py`.

### Technical Decisions & Bug Fixes
* **Pragma Query-Only Initialization Order:** Identified that executing `PRAGMA query_only = ON;` after registering `read_only_authorizer` triggered authorizer denial because `query_only` had an assignment argument (`arg2='ON'`). Resolved by activating `PRAGMA query_only = ON;` immediately upon connection setup before binding the authorizer callback.
* **Progress Handler Step Size Tuning:** Dynamically scaled step size `min(PROGRESS_STEP_SIZE, max(1, max_instructions // 10))` so short runaway queries trigger cleanly without waiting for arbitrary 10k instruction step boundaries.

### Verification Results
* Command: `pytest -v`
* Result: 52 passed in 1.02s (100% of mutation attempts blocked, BLOBs serialized safely, timeouts triggered).

---

## [Completed] — Milestone 2: FastMCP Tools, Resources & Prompts

### Accomplishments
* Developed `src/sqlite_mcp/tools.py`:
  - Implemented `list_tables` returning typed `ListTablesResponse` Pydantic models with table names, types, and index counts.
  - Implemented `describe_table` returning typed `DescribeTableResponse` Pydantic models containing columns, data types, constraints, foreign keys, indexes, and raw DDL.
  - Implemented `execute_query` returning typed `QueryExecutionResponse` with safe cell serialization, execution timing, pagination/limit markers, and clean error messages for invalid or forbidden queries.
* Developed `src/sqlite_mcp/resources.py`:
  - Implemented dynamic resource URI `sqlite://schema` with MIME type `text/markdown`, generating complete schema summaries for LLM absorption in a single read.
* Developed `src/sqlite_mcp/prompts.py`:
  - Implemented `analyze_schema` prompt template injecting current schema markdown and structured DBA review instructions.
* Authored integration test suite `tests/test_mcp_tools.py`:
  - Validated async tool execution, resource reading, and prompt rendering via live `FastMCP` test server fixture.

### Verification Results
* Command: `pytest -v`
* Result: 61 passed in 2.52s across all test suites (`test_fixtures.py`, `test_security.py`, `test_db.py`, `test_mcp_tools.py`).

---

## [Completed] — Milestone 3: Stdio Server Lifecycle & CLI Wiring

### Accomplishments
* Developed `src/sqlite_mcp/server.py`:
  - Implemented `parse_arguments` with `--db-path` CLI flag and `SQLITE_DB_PATH` environment variable fallback.
  - Implemented `configure_stderr_logging` strictly routing all log messages and diagnostics to `sys.stderr`, preventing JSON-RPC stdio protocol corruption.
  - Implemented `create_mcp_server` and `main` entry point booting `FastMCP` transport over `stdio`.
* Authored integration test suite `tests/test_server_stdio.py`:
  - Verified CLI argument parsing and environment variable fallback logic.
  - Executed end-to-end subprocess stdio lifecycle: MCP `initialize` handshake, `notifications/initialized`, `tools/list` discovery, and tool execution (`list_tables`, `execute_query`).
  - Verified standard protocol hygiene: `stdout` contains 100% valid JSON-RPC 2.0 packets, while `stderr` captures all runtime logs.

### Verification Results
* Command: `pytest -v`
* Result: 65 passed in 3.36s across all test suites.

---

## [Completed] — Milestone 4: Antigravity E2E Integration & Verification

### Accomplishments
* Generated sample database `sample.db` in workspace root via `python tests/fixtures/create_sample_db.py -o sample.db` with populated `users`, `products`, `orders`, indexes, view `order_summary`, and binary BLOB avatars.
* Created `mcp_config.json` defining configuration snippet for Antigravity and other MCP-compliant desktop agents.
* Authored production-ready `README.md` covering 4-layer security architecture, tools/resources/prompts, installation, execution, MCP client integration, and test suite execution.
* Updated `TESTING.md` with stdio test specifications and manual agent chat checklist.
* Completed all checklist tasks in `PLAN.md`.

### Verification Results
* Command: `pytest -v`
* Result: 65 passed in 3.36s (100% test coverage across all security vectors, database operations, tools, resources, prompts, and stdio JSON-RPC lifecycle).
* Database & server verified ready for live client connections.

---

## [Refinement] — MCP Inspector Schema Portability Warnings Resolved

### Problem
MCP Inspector flagged schema portability warnings on `execute_query` (`outputSchema.properties.rows.items.items`) and `describe_table` (`outputSchema.$defs.ColumnInfo.properties.default_value.anyOf[0]`). Using Python `Any` in Pydantic models caused empty schema objects (`{}`), which some strict MCP clients refuse.

### Fix
* Replaced bare `Any` in `QueryExecutionResponse.rows` with concrete union `CellValue = Union[str, int, float, bool, None]`.
* Replaced bare `Any` in `ColumnInfo.default_value` with `Optional[Union[str, int, float, bool]]`.
* Verified all 65 automated tests pass cleanly with 100% schema portability.

---

## [Completed] — Milestone 5: Post-Review Hardening & Engine Precision

### Context & Review
Analyzed external code review by Claude Sonnet 5.5. Validated that while core write-blocking invariants held firm, improvements were needed for URI percent-encoding, parameterized table-valued pragmas, limiter isolation, and documentation precision.

### Accomplishments
* **URI Percent-Encoding:** Migrated URI construction in `db.py` to `Path.resolve().as_uri() + "?mode=ro"`, preventing Layer 1 bypass when database paths contain `#`, `%`, or `?`.
* **Parameterized Table-Valued PRAGMAs:** Refactored `describe_table` in `db.py` to query SQLite's native table-valued functions (`pragma_table_info(?)`, `pragma_foreign_key_list(?)`, `pragma_index_list(?)`, `pragma_index_info(?)`) with bound parameters, natively handling apostrophe identifiers like `it's_table`.
* **Limiter Isolation & Analytical Capacity:** Isolated `QueryInstructionLimiter` instances per query execution, avoiding instruction leakage from `list_tables` and `describe_table`. Exposed `SQLITE_MAX_INSTRUCTIONS` environment variable (default 10,000,000 instructions) for analytical workloads.
* **Dependency & Claims Calibration:** Bumped `mcp` bound to `>=1.3.0,<2.0.0` and added `pytest-cov` to dev dependencies in `pyproject.toml`. Refined documentation to distinguish VM instruction steps from wall-clock timeouts.
* **Engineering Rules Update:** Updated `GEMINI.md` with explicit URI percent-encoding, table-valued PRAGMA, and claims rigor rules.
* **Added Unit Tests:** Added 4 new test cases in `tests/test_db.py` covering special characters in paths, table names with apostrophes, limiter isolation, and environment configuration.

### Verification Results
* Command: `pytest -v`
* Result: 69 passed in 3.87s across all test suites.