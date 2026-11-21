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
* Result: 52 passed in 1.02s (mutation attempts blocked, BLOBs serialized safely, instruction limits triggered).

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
* Result: 65 passed in 3.36s across all security vectors, database operations, tools, resources, prompts, and stdio JSON-RPC lifecycle.
* Database & server verified ready for live client connections.

---

## [Refinement] — MCP Inspector Schema Portability Warnings Resolved

### Problem
MCP Inspector flagged schema portability warnings on `execute_query` (`outputSchema.properties.rows.items.items`) and `describe_table` (`outputSchema.$defs.ColumnInfo.properties.default_value.anyOf[0]`). Using Python `Any` in Pydantic models caused empty schema objects (`{}`), which some strict MCP clients refuse.

### Fix
* Replaced bare `Any` in `QueryExecutionResponse.rows` with concrete union `CellValue = Union[str, int, float, bool, None]`.
* Replaced bare `Any` in `ColumnInfo.default_value` with `Optional[Union[str, int, float, bool]]`.
* Verified all 65 automated tests pass cleanly with strict MCP schema compatibility.

---

## [Completed] — Milestone 5: Post-Review Hardening & Engine Precision

### Context & Review
Analyzed external code review from independent peer audit. Validated that while core write-blocking invariants held firm, improvements were needed for URI percent-encoding, parameterized table-valued pragmas, limiter isolation, and documentation precision.

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

---

## [Completed] — Milestone 6: Test Isolation & Scanner Quote Expansion

### Context & Refinement
Addressed follow-up peer review regarding test layer isolation, dynamic environment parsing, and quotation coverage in statement parsing.

### Accomplishments
* **Direct Layer 1 Test Isolation:** Updated `test_uri_encoding_with_special_characters` to test `sqlite3.connect` with raw `mode=ro` URI independently without Layer 2 authorizer or Layer 3 pragma masking, proving filesystem-level write blocking.
* **Resilient Environment Parsing:** Implemented `get_default_max_instructions()` with safe fallback to `10_000_000`, eliminating import-time integer parsing crashes and enabling dynamic runtime reconfiguration.
* **Expanded Identifier Quotation Support:** Extended `has_stacked_statements` in `security.py` to support SQLite square brackets (`[...]`) and backticks (`` `...` ``), eliminating false positives when semicolons appear inside bracketed or backtick-quoted table/column names.
* **Repository-Wide Spec Sweep:** Cleared all remaining uncalibrated claims across `README.md`, `ROADMAP.md`, `PLAN.md`, and documented `SQLITE_MAX_INSTRUCTIONS` in `mcp_config.json`.
* **Engineering Rules Update:** Added Sections 2.6, 2.7, and 2.8 to `GEMINI.md` governing defense layer test isolation, dynamic config, and complete quotation scanning.

### Verification Results
* Command: `pytest -v`
* Result: 72 passed with verified layer isolation.

---

## [Completed] — Milestone 7: Production Layer Isolation, Bracket Grammar & Repo Polish

### Context & Refinement
Addressed final code review points:
1. Production Layer 1 test isolation directly verifying `mgr.get_connection()`.
2. SQLite bracket quoting grammar correction (immediate termination on first `]`, no escaping).
3. Stacked statement rejection tests with brackets and backticks.
4. User-friendly stderr warning on invalid `SQLITE_MAX_INSTRUCTIONS` configuration.
5. Removal of unused dead code (`QueryInstructionLimiter.reset()`).
6. Clean repository layout (`docs/` folder reorganization, `.github/workflows/ci.yml`, `SECURITY.md`).

### Accomplishments
* **Production Connection Layer 1 Isolation:** In `test_uri_encoding_with_special_characters`, obtained `mgr.get_connection()`, cleared authorizer (`set_authorizer(None)`), deactivated query-only (`PRAGMA query_only = OFF;`), and asserted that writes fail with `"attempt to write a readonly database"`. This directly tests that `mgr.get_connection()` generates a valid `mode=ro` URI without relying on Layer 2 or Layer 3.
* **Exact Bracket Quoting Grammar:** Fixed `has_stacked_statements` in `security.py` so that square bracket identifiers (`[...]`) close strictly on the first `]`, matching SQLite's engine specification.
* **Added Stacked Quoting Rejection Tests:** Added parameterized negative tests in `tests/test_security.py` verifying that queries with stacked statements following bracketed or backtick identifiers (e.g. `SELECT [name] FROM users; DROP TABLE orders;`) are properly rejected.
* **Configuration Stderr Diagnostics:** Emitted a clear diagnostic warning to `sys.stderr` when `SQLITE_MAX_INSTRUCTIONS` cannot be parsed or is non-positive, ensuring users get feedback while protocol stability on `stdout` is maintained.
* **Dead Code Cleanup:** Removed unused `QueryInstructionLimiter.reset()`.
* **Clean Repository Structure:** Moved internal specifications (`PLAN.md`, `ROADMAP.md`, `SCENARIO.md`, `TESTING.md`, `HISTORY.md`) into `docs/`. Added `.github/workflows/ci.yml` and `SECURITY.md`.

### Verification Results
* Command: `pytest -v`
* Result: 76 passed in 3.58s across all test suites.

---

## [Completed] — Milestone 8: CI Matrix Isolation, Pin Verification & Security Boundary Tightening

### Context & Refinement
Addressed reviewer follow-up regarding CI matrix execution fidelity, empirical `mcp` SDK version constraints for structured output, and security documentation tightening:
1. `uv python install` in CI does not add the installed interpreter to system `PATH`, causing matrix jobs to execute on the runner default Python.
2. `mcp` lower bound needed verification against PyPI and Git changelog for structured output (`outputSchema`) and Pydantic compatibility.
3. `SECURITY.md` tightened to state "bound response size", document database-wide read scope, and address untrusted database content in prompt generation.
4. Fenced schema text and sanitized prompt arguments in `analyze_schema`.
5. Missing `docs/SCENARIO.md` link added to `README.md`.

### Accomplishments
* **CI Python Matrix Correction:** Updated `.github/workflows/ci.yml` to use `actions/setup-python@v5` with `python-version: ${{ matrix.python-version }}` and standard `python -m pip install -e ".[dev]"`. Added an explicit `python --version` verification step and an automated `test-min-bound` job testing against `mcp==1.22.0` on Python 3.10.
* **Empirical `mcp` Version Verification:**
  - Researched SDK repository: PR #993 ("feat: Add structured output support for tool functions") introduced `outputSchema` generation in `mcp v1.10.0` (published 2025-06-26).
  - Identified and tested Pydantic compatibility: `mcp 1.10.0` through `1.21.0` attempt to import `pydantic._internal._typing_extra.eval_type_backport`, raising `ImportError` on modern Pydantic releases (`>=2.14`).
  - Empirically tested versions in an isolated environment: `mcp 1.22.0` is the earliest version resolving the Pydantic import issue while supporting structured output schemas.
  - Set lower bound to `mcp>=1.22.0,<2.0.0` in `pyproject.toml` and verified all 76 tests pass cleanly.
* **Prompt Hardening & Testing:** In `src/sqlite_mcp/prompts.py`, wrapped database schema markdown in explicit fences (`### Target Database Schema (Untrusted Database Content):\n```markdown ... ````) and sanitized the `focus` parameter to single-line text (`" ".join(focus.split())`). Updated `tests/test_mcp_tools.py` with multi-line injection sanitization assertions.
* **Documentation Calibration:** Tightened `SECURITY.md` (bounded response size, database-wide access boundary, untrusted prompt schema context) and added `docs/SCENARIO.md` to `README.md`.

### Verification Results
* Command: `python -m pytest -v --cov=sqlite_mcp --cov-report=term-missing`
* Result: 76 passed in 4.68s with 91% overall coverage (`db.py` 99%, `tools.py` 95%, `security.py` 92%).

---

## [Completed] — Milestone 9: Python 3.10 Compatibility & Dynamic Prompt Fencing

### Context & Refinement
Addressed CI failure on Python 3.10 and reviewer feedback regarding prompt block integrity:
1. Python 3.10 jobs failed in CI during Layer 1 test isolation because CPython 3.10 `sqlite3.Connection.set_authorizer(None)` does not unregister the authorizer hook (CPython issue bpo-44431).
2. The schema fence in `analyze_schema` used a static 3-backtick fence (` ```markdown `), which collided with inner ```` ```sql ```` DDL blocks.
3. The prompt sanitization claim in `SECURITY.md` needed precision: structural formatting breakouts are mitigated, but semantic instruction text is not filtered.

### Accomplishments
* **Python 3.10 Layer 1 Isolation Fix:** In `tests/test_db.py`, updated `test_uri_encoding_with_special_characters` to bypass Layer 2 via `ro_conn.set_authorizer(lambda *args: sqlite3.SQLITE_OK)` rather than `set_authorizer(None)`. This cleanly permits all actions at Layer 2 across Python 3.10, 3.11, 3.12, and 3.13, verifying that `ro_conn.execute("INSERT ...")` is rejected purely by Layer 1 (`mode=ro`). Verified locally against Python 3.10.22.
* **Dynamic Multi-Backtick Fencing:** Refactored `analyze_schema` in `src/sqlite_mcp/prompts.py` to calculate fence length dynamically: `` "`" * max(4, max_run + 1) ``, where `max_run` is the longest consecutive run of backticks in `schema_markdown`. This guarantees that inner 3-backtick DDL blocks (```` ```sql ````) and backtick-containing identifiers cannot close the outer block early.
* **Added Dynamic Fence Test:** Implemented `test_analyze_schema_prompt_dynamic_fence_with_backticks` in `tests/test_mcp_tools.py`, generating a database table with 4 consecutive backticks and verifying that the outer fence expands to 5 backticks, enclosing the entire schema.
* **Calibrated Threat Model:** Updated `SECURITY.md` to state that dynamic fencing and whitespace flattening reduce structural formatting breakouts without claiming to neutralize semantic prompt injection.

### Verification Results
* Command: `python -m pytest -v --cov=sqlite_mcp --cov-report=term-missing`
* Result: 77 passed in 6.22s with 91% overall coverage (`db.py` 99%, `tools.py` 95%, `security.py` 92%).
* Local Python 3.10 Verification: 77 passed in 4.00s.