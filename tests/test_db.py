"""Unit tests for SQLite database manager, data formatting, and execution safeguards."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import pytest

from sqlite_mcp.db import (
    DEFAULT_ROW_LIMIT,
    MAX_CELL_CHARS,
    MAX_ROW_LIMIT,
    DatabaseManager,
    sanitize_cell,
    sanitize_row,
)
from sqlite_mcp.security import SecurityError


@pytest.fixture
def db_manager(sample_db_path: Path) -> DatabaseManager:
    return DatabaseManager(sample_db_path)


class TestDataSanitization:
    """Verifies that cells and rows are serialized safely without throwing JSON TypeErrors."""

    def test_sanitize_blob(self) -> None:
        raw_blob = b"\x00\x01\x02\x03\x04"
        sanitized = sanitize_cell(raw_blob)
        assert sanitized == "<BLOB 5 bytes>"
        # Ensure json serializable
        assert json.dumps(sanitized) == '"<BLOB 5 bytes>"'

    def test_sanitize_none(self) -> None:
        assert sanitize_cell(None) is None
        assert json.dumps(sanitize_cell(None)) == "null"

    def test_sanitize_short_string(self) -> None:
        assert sanitize_cell("hello world") == "hello world"

    def test_sanitize_long_string(self) -> None:
        long_str = "a" * 600
        sanitized = sanitize_cell(long_str)
        assert len(sanitized) == MAX_CELL_CHARS + len("... [truncated]")
        assert sanitized.endswith("... [truncated]")
        assert sanitized.startswith("a" * 500)

    def test_sanitize_row(self) -> None:
        row = (1, "Alice", b"binary", "x" * 550, None, 42.5)
        sanitized = sanitize_row(row)
        assert sanitized[0] == 1
        assert sanitized[1] == "Alice"
        assert sanitized[2] == "<BLOB 6 bytes>"
        assert sanitized[3].endswith("... [truncated]")
        assert sanitized[4] is None
        assert sanitized[5] == 42.5
        # Must be valid JSON
        json_str = json.dumps(sanitized)
        assert "null" in json_str
        assert "<BLOB 6 bytes>" in json_str


class TestDatabaseManagerExecution:
    """Verifies DatabaseManager query execution, limits, schema introspection, and read-only defense."""

    def test_nonexistent_database(self, tmp_path: Path) -> None:
        missing = tmp_path / "does_not_exist.db"
        mgr = DatabaseManager(missing)
        with pytest.raises(FileNotFoundError):
            mgr.get_connection()

    def test_readonly_enforcement_on_connection(self, db_manager: DatabaseManager) -> None:
        conn = db_manager.get_connection()
        try:
            with pytest.raises((sqlite3.OperationalError, sqlite3.DatabaseError)) as exc_info:
                conn.execute("INSERT INTO users (name, email) VALUES ('evil', 'evil@example.com');")
            msg = str(exc_info.value).lower()
            assert "readonly" in msg or "not authorized" in msg or "denied" in msg
        finally:
            conn.close()

    def test_execute_query_success(self, db_manager: DatabaseManager) -> None:
        res = db_manager.execute_query("SELECT id, name, email FROM users ORDER BY id;")
        assert res["columns"] == ["id", "name", "email"]
        assert len(res["rows"]) == 3
        assert res["row_count"] == 3
        assert res["is_truncated"] is False
        assert res["execution_time_ms"] >= 0

    def test_blob_handling_in_execute_query(self, db_manager: DatabaseManager) -> None:
        res = db_manager.execute_query("SELECT id, avatar, bio FROM users WHERE id = 1;")
        assert len(res["rows"]) == 1
        avatar_cell = res["rows"][0][1]
        bio_cell = res["rows"][0][2]
        assert avatar_cell.startswith("<BLOB ")
        assert bio_cell.endswith("... [truncated]")
        # Must dump to JSON cleanly
        serialized = json.dumps(res)
        assert "<BLOB" in serialized

    def test_row_limiting_and_truncation(self, sample_db_path: Path) -> None:
        # Create a database with 5000 rows
        conn = sqlite3.connect(str(sample_db_path))
        conn.execute("CREATE TABLE big_table (num INTEGER);")
        conn.executemany("INSERT INTO big_table VALUES (?);", [(i,) for i in range(5000)])
        conn.commit()
        conn.close()

        mgr = DatabaseManager(sample_db_path)

        # Default limit 100
        res_default = mgr.execute_query("SELECT * FROM big_table;")
        assert res_default["row_count"] == DEFAULT_ROW_LIMIT
        assert len(res_default["rows"]) == DEFAULT_ROW_LIMIT
        assert res_default["is_truncated"] is True

        # Custom limit 250
        res_custom = mgr.execute_query("SELECT * FROM big_table;", max_rows=250)
        assert res_custom["row_count"] == 250
        assert res_custom["is_truncated"] is True

        # Ceiling cap at MAX_ROW_LIMIT (1000)
        res_capped = mgr.execute_query("SELECT * FROM big_table;", max_rows=2000)
        assert res_capped["row_count"] == MAX_ROW_LIMIT
        assert res_capped["limit_applied"] == MAX_ROW_LIMIT
        assert res_capped["is_truncated"] is True

    def test_progress_handler_timeout(self, db_manager: DatabaseManager) -> None:
        # Configure a manager with a very low instruction limit to simulate runaway query
        strict_mgr = DatabaseManager(db_manager.db_path, max_instructions=5000)
        with pytest.raises(sqlite3.OperationalError) as exc_info:
            strict_mgr.execute_query(
                "SELECT count(*) FROM (WITH RECURSIVE cnt(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM cnt WHERE x < 500000) SELECT * FROM cnt);"
            )
        assert "interrupted" in str(exc_info.value).lower()

    def test_mutation_query_rejection(self, db_manager: DatabaseManager) -> None:
        with pytest.raises(SecurityError):
            db_manager.execute_query("DROP TABLE users;")

        with pytest.raises(SecurityError):
            db_manager.execute_query("DELETE FROM users WHERE id = 1;")

    def test_list_tables(self, db_manager: DatabaseManager) -> None:
        tables = db_manager.list_tables()
        table_names = [t["name"] for t in tables]
        assert "users" in table_names
        assert "products" in table_names
        assert "orders" in table_names
        assert "order_summary" in table_names
        assert all(not name.startswith("sqlite_") for name in table_names)

    def test_describe_table(self, db_manager: DatabaseManager) -> None:
        desc = db_manager.describe_table("users")
        assert desc["table_name"] == "users"
        assert desc["type"] == "table"
        col_names = [c["name"] for c in desc["columns"]]
        assert "id" in col_names
        assert "email" in col_names
        assert "avatar" in col_names
        assert "bio" in col_names

        # Check foreign keys on orders
        orders_desc = db_manager.describe_table("orders")
        fk_targets = [fk["table"] for fk in orders_desc["foreign_keys"]]
        assert "users" in fk_targets
        assert "products" in fk_targets

        # Check invalid table raises ValueError
        with pytest.raises(ValueError):
            db_manager.describe_table("non_existent_table")

    def test_get_database_schema_markdown(self, db_manager: DatabaseManager) -> None:
        schema_md = db_manager.get_database_schema_markdown()
        assert "# Database Schema" in schema_md
        assert "## Table: `users`" in schema_md
        assert "## Table: `orders`" in schema_md
        assert "## View: `order_summary`" in schema_md
        assert "| Name | Type | Not Null | Default | PK |" in schema_md

    def test_uri_encoding_with_special_characters(self, tmp_path: Path) -> None:
        # Create a database with #, %, and spaces in the path
        special_dir = tmp_path / "folder#with%special chars!"
        special_dir.mkdir(parents=True, exist_ok=True)
        db_file = special_dir / "test#database%data.db"

        conn = sqlite3.connect(str(db_file))
        conn.execute("CREATE TABLE sample (id INT);")
        conn.execute("INSERT INTO sample VALUES (42);")
        conn.commit()
        conn.close()

        mgr = DatabaseManager(db_file)
        res = mgr.execute_query("SELECT id FROM sample;")
        assert res["rows"][0][0] == 42

        # Verify Layer 1 (mode=ro) is directly enforced on raw URI without Layer 2 authorizer or Layer 3 query_only
        raw_uri = f"{db_file.resolve().as_uri()}?mode=ro"
        raw_conn = sqlite3.connect(raw_uri, uri=True)
        try:
            with pytest.raises(sqlite3.OperationalError) as exc_info:
                raw_conn.execute("INSERT INTO sample VALUES (99);")
            assert "readonly" in str(exc_info.value).lower()
        finally:
            raw_conn.close()

        # Also verify via DatabaseManager connection that writes are blocked
        ro_conn = mgr.get_connection()
        try:
            with pytest.raises((sqlite3.OperationalError, sqlite3.DatabaseError)):
                ro_conn.execute("INSERT INTO sample VALUES (99);")
        finally:
            ro_conn.close()

    def test_describe_table_with_apostrophe(self, sample_db_path: Path) -> None:
        conn = sqlite3.connect(str(sample_db_path))
        conn.execute('CREATE TABLE "it\'s_a_table" (id INTEGER PRIMARY KEY, note TEXT);')
        conn.execute('CREATE INDEX "idx_it\'s_note" ON "it\'s_a_table"(note);')
        conn.commit()
        conn.close()

        mgr = DatabaseManager(sample_db_path)
        desc = mgr.describe_table("it's_a_table")
        assert desc["table_name"] == "it's_a_table"
        col_names = [c["name"] for c in desc["columns"]]
        assert "id" in col_names
        assert "note" in col_names
        idx_names = [idx["name"] for idx in desc["indexes"]]
        assert "idx_it's_note" in idx_names

    def test_limiter_isolation_between_operations(self, db_manager: DatabaseManager) -> None:
        # Running list_tables and describe_table repeatedly should not exhaust query limiter
        for _ in range(20):
            db_manager.list_tables()
            db_manager.describe_table("users")

        # Query execution still has its full dedicated instruction budget
        res = db_manager.execute_query("SELECT count(*) FROM users;")
        assert res["row_count"] == 1

    def test_configurable_instruction_limit_via_env(
        self, sample_db_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 1. Custom positive integer takes effect dynamically upon construction
        monkeypatch.setenv("SQLITE_MAX_INSTRUCTIONS", "25000000")
        mgr_custom = DatabaseManager(sample_db_path)
        assert mgr_custom.max_instructions == 25_000_000

        # 2. Invalid string value falls back to default safely without crashing
        monkeypatch.setenv("SQLITE_MAX_INSTRUCTIONS", "not_a_number")
        mgr_fallback = DatabaseManager(sample_db_path)
        assert mgr_fallback.max_instructions == 10_000_000
