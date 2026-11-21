"""Initial verification test for sample SQLite test fixture."""

from __future__ import annotations

from pathlib import Path
import sqlite3


def test_sample_database_generation(sample_db_path: Path) -> None:
    """Verifies that the sample database is created with expected schema and records."""
    assert sample_db_path.exists()

    conn = sqlite3.connect(str(sample_db_path))
    cursor = conn.cursor()

    try:
        # Check tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
        tables = [row[0] for row in cursor.fetchall() if not row[0].startswith("sqlite_")]
        assert tables == ["orders", "products", "users"]

        # Check view
        cursor.execute("SELECT name FROM sqlite_master WHERE type='view';")
        views = [row[0] for row in cursor.fetchall()]
        assert "order_summary" in views

        # Check indexes
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%';")
        indexes = [row[0] for row in cursor.fetchall()]
        assert "idx_users_email" in indexes
        assert "idx_orders_user_id" in indexes
        assert "idx_orders_product_id" in indexes

        # Check data & BLOB column
        cursor.execute("SELECT name, avatar, bio FROM users WHERE id = 1;")
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "Alice Smith"
        assert isinstance(row[1], bytes)
        assert len(row[1]) > 0
        assert len(row[2]) > 500

        # Check row counts
        cursor.execute("SELECT COUNT(*) FROM orders;")
        assert cursor.fetchone()[0] == 3
    finally:
        conn.close()
