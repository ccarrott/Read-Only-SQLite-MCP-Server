# ROADMAP.md — Project Milestones & Execution Stages

```
   [Milestone 0] --------> [Milestone 1] --------> [Milestone 2] --------> [Milestone 3] --------> [Milestone 4]
Env & Test Fixtures     Native Security Driver    FastMCP Tools & Res.    Stdio & CLI Server      Antigravity E2E
 (Sample DB & Pytest)   (Authorizer & Reader)   (List/Describe/Query)   (Argparse & Stderr)     (Config & Verify)
```

---

## Milestone 0: Environment & Test Harness Foundation
* **Goal:** Set up a clean Python environment, dependency definitions, and mock database generator.
* **Deliverables:**
  * `pyproject.toml` configured with `mcp>=1.0.0`, `pydantic>=2.0.0`, `pytest`.
  * `tests/fixtures/create_sample_db.py` to generate sample SQLite database containing complex schemas, indexes, foreign keys, and BLOB columns.
* **Completion Criteria:** Running `pytest` successfully executes an initial test pass against the generated sample database.

---

## Milestone 1: Secure SQLite Core Driver
* **Goal:** Build the native 4-layer security validation system and resilient database engine.
* **Deliverables:**
  * `security.py` implementing SQLite's native `set_authorizer` callback.
  * `db.py` implementing read-only URI connection handling, progress limits, and BLOB/cell data formatting.
  * Unit tests (`test_security.py` and `test_db.py`).
* **Completion Criteria:** All defined mutation attempts (`DROP`, `INSERT`, `UPDATE`, `PRAGMA write`) are caught and blocked at the engine level with zero unhandled errors.

---

## Milestone 2: FastMCP Tools, Resources & Prompts
* **Goal:** Implement the formal MCP tool and resource interfaces using `FastMCP`.
* **Deliverables:**
  * `tools.py`: Implement `list_tables`, `describe_table`, and `execute_query`.
  * `resources.py`: Implement dynamic database schema resource (`sqlite://schema`).
  * `prompts.py`: Implement schema optimization prompts.
* **Completion Criteria:** All tools process inputs cleanly and return validated Pydantic models / JSON payloads without throwing unhandled exceptions.

---

## Milestone 3: Stdio Server Lifecycle & CLI Wiring
* **Goal:** Wire the MCP server to standard I/O and CLI argument parsing for host execution.
* **Deliverables:**
  * `server.py` exposing CLI interface (`--db-path`) and booting FastMCP over `stdio`.
  * Logging configuration explicitly bound to `sys.stderr`.
* **Completion Criteria:** Server boots silently over stdio, parses CLI args correctly, completes MCP handshake, and processes tool call requests via standard JSON-RPC.

---

## Milestone 4: Antigravity E2E Integration & Verification
* **Goal:** Plug the server into Antigravity and verify real AI interaction.
* **Deliverables:**
  * Working `mcp_config.json` configuration snippet.
  * `README.md` with execution steps.
  * `TESTING.md` verifying real agent operations.
* **Completion Criteria:** Antigravity agent connects, discovers tools/resources, inspects a sample SQLite database, and answers user queries cleanly.

---

## Milestone 5: Post-Review Hardening & Open-Source Maintenance
* **Goal:** Address external review findings, harden edge cases, and ensure open-source precision.
* **Deliverables:**
  * URI percent-encoding via `Path.resolve().as_uri() + "?mode=ro"`.
  * Parameterized table-valued PRAGMA functions (`pragma_table_info(?)`, etc.) handling special-character and apostrophe identifiers.
  * Isolated per-query instruction limiters and configurable analytical budget (`SQLITE_MAX_INSTRUCTIONS`).
  * Dependency bound refinement (`mcp>=1.3.0,<2.0.0`) and claims calibration.
  * Updated `GEMINI.md` engineering rules.
* **Completion Criteria:** All 69 automated unit/integration tests pass with 0 warnings in MCP Inspector.

---

## Milestone 6: Test Layer Isolation & Full Quote Syntax
* **Goal:** Direct layer verification in tests and complete SQLite quoting syntax in statement scanning.
* **Deliverables:**
  * Direct filesystem-level `mode=ro` testing in `test_db.py`.
  * Safe dynamic environment parsing in `get_default_max_instructions()`.
  * Extended quoting scanner covering `[...]` and backticks in `security.py`.
* **Completion Criteria:** All 72 tests pass with direct layer isolation verified.

---

## Milestone 7: Production Connection Isolation, Bracket Grammar & Clean Repo
* **Goal:** Production factory connection layer isolation, strict bracket grammar, CI workflow, and repository reorganization.
* **Deliverables:**
  * Test Layer 1 isolation directly against `DatabaseManager.get_connection()`.
  * Strict bracket quoting grammar (close on first `]`).
  * Parameterized tests for rejection of stacked statements with bracketed/backtick identifiers.
  * Stderr warning diagnostics on invalid `SQLITE_MAX_INSTRUCTIONS`.
  * GitHub Actions CI workflow (`.github/workflows/ci.yml`) and `SECURITY.md`.
  * Clean repository structure with documentation located in `docs/`.
* **Completion Criteria:** All 76 tests pass across all test suites, CI workflow configured, clean repository layout.

---

## Milestone 8: CI Matrix Isolation, Pin Verification & Security Boundary Tightening
* **Goal:** Reliable CI matrix execution across Python versions, empirical dependency lower-bound pin, and tightened security documentation.
* **Deliverables:**
  * CI workflow using `actions/setup-python@v5`, explicit `python --version` logging, and minimum bound test job.
  * Verified lower-bound dependency pin `mcp>=1.22.0,<2.0.0` based on structured output support and Pydantic compatibility.
  * Prompt schema markdown fencing and focus argument sanitization.
  * Tightened response bounding and access boundary descriptions in `SECURITY.md`.
  * Linked `docs/SCENARIO.md` in `README.md`.
* **Completion Criteria:** All 76 tests pass with 91% code coverage, and the minimum bound installs and runs without errors.