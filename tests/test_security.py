"""Unit tests for SQLite read-only security authorizer and statement validator."""

from __future__ import annotations

from pathlib import Path
import sqlite3
import pytest

from sqlite_mcp.security import (
    FORBIDDEN_ACTIONS,
    SecurityError,
    has_stacked_statements,
    read_only_authorizer,
    validate_sql_statement,
)


@pytest.fixture
def authorizer_connection(sample_db_path: Path) -> sqlite3.Connection:
    """Connection with read_only_authorizer attached (without mode=ro for testing authorizer in isolation)."""
    conn = sqlite3.connect(str(sample_db_path))
    conn.set_authorizer(read_only_authorizer)
    yield conn
    conn.close()


class TestStatementValidator:
    """Validates Layer 4 syntax and statement-level inspection."""

    @pytest.mark.parametrize(
        "query",
        [
            "SELECT * FROM users",
            "SELECT id, name FROM users WHERE id = 1;",
            "WITH summary AS (SELECT * FROM orders) SELECT * FROM summary;",
            "EXPLAIN QUERY PLAN SELECT * FROM users",
            "-- comment before select\nSELECT * FROM products;",
            "/* block comment */ SELECT count(*) FROM orders;",
            "SELECT * FROM users WHERE name = 'user;with;semicolons';",
            "SELECT * FROM users WHERE bio = \"semicolon;in;double;quotes\";",
            "SELECT * FROM [users;table];",
            "SELECT * FROM `orders;table`;",
            "SELECT [col;1], `col;2` FROM users;",
        ],
    )
    def test_allowed_statements(self, query: str) -> None:
        # Should not raise any error
        validate_sql_statement(query)

    @pytest.mark.parametrize(
        "query,expected_err",
        [
            ("INSERT INTO users (name) VALUES ('hacked')", "forbidden"),
            ("UPDATE users SET name = 'hacked'", "forbidden"),
            ("DELETE FROM users WHERE id = 1", "forbidden"),
            ("DROP TABLE users", "forbidden"),
            ("ALTER TABLE users ADD COLUMN age INT", "forbidden"),
            ("CREATE TABLE evil (id INT)", "forbidden"),
            ("ATTACH DATABASE 'other.db' AS other", "forbidden"),
            ("PRAGMA writable_schema = ON", "forbidden"),
            ("", "empty"),
            ("   ", "empty"),
            ("-- only a comment\n", "only comments"),
        ],
    )
    def test_forbidden_statement_types(self, query: str, expected_err: str) -> None:
        with pytest.raises(SecurityError) as exc_info:
            validate_sql_statement(query)
        assert expected_err.lower() in str(exc_info.value).lower()

    @pytest.mark.parametrize(
        "query",
        [
            "SELECT * FROM users; DROP TABLE orders;",
            "SELECT 1; SELECT 2;",
            "SELECT * FROM users; DELETE FROM orders WHERE id = 1;",
            "WITH cte AS (SELECT 1) SELECT * FROM cte; DROP TABLE users;",
        ],
    )
    def test_stacked_statements_rejected(self, query: str) -> None:
        assert has_stacked_statements(query) is True
        with pytest.raises(SecurityError) as exc_info:
            validate_sql_statement(query)
        assert "multi-statement deny" in str(exc_info.value).lower()


class TestNativeEngineAuthorizer:
    """Validates Layer 2 native SQLite engine authorizer callback."""

    def test_allowed_select_and_cte(self, authorizer_connection: sqlite3.Connection) -> None:
        cursor = authorizer_connection.cursor()
        cursor.execute("SELECT * FROM users")
        assert len(cursor.fetchall()) > 0

        cursor.execute("WITH summary AS (SELECT * FROM orders) SELECT * FROM summary")
        assert len(cursor.fetchall()) > 0

        cursor.execute("EXPLAIN QUERY PLAN SELECT * FROM users")
        assert len(cursor.fetchall()) > 0

    def test_allowed_safe_pragmas(self, authorizer_connection: sqlite3.Connection) -> None:
        cursor = authorizer_connection.cursor()
        cursor.execute("PRAGMA table_info(users);")
        columns = cursor.fetchall()
        assert len(columns) > 0

        cursor.execute("PRAGMA foreign_key_list(orders);")
        fks = cursor.fetchall()
        assert len(fks) > 0

        cursor.execute("PRAGMA query_only;")
        cursor.fetchall()

    @pytest.mark.parametrize(
        "mutation_sql",
        [
            "DELETE FROM users WHERE id = 1",
            "DROP TABLE users",
            "INSERT INTO users (name, email) VALUES ('evil', 'evil@example.com')",
            "UPDATE users SET name = 'evil' WHERE id = 1",
            "ALTER TABLE users ADD COLUMN age INT",
            "CREATE TABLE evil (id INT)",
            "CREATE INDEX idx_evil ON users(name)",
            "CREATE VIEW evil_view AS SELECT * FROM users",
            "ATTACH DATABASE 'evil.db' AS evil",
            "PRAGMA writable_schema = ON",
            "PRAGMA foreign_keys = OFF",
        ],
    )
    def test_mutations_blocked_by_engine_authorizer(
        self, authorizer_connection: sqlite3.Connection, mutation_sql: str
    ) -> None:
        cursor = authorizer_connection.cursor()
        with pytest.raises(sqlite3.DatabaseError) as exc_info:
            cursor.execute(mutation_sql)
        assert "not authorized" in str(exc_info.value).lower()
