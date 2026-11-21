"""Sample SQLite database generator for tests and E2E verification."""

from __future__ import annotations

import argparse
from pathlib import Path
import sqlite3
import sys


def create_sample_database(db_path: str | Path) -> Path:
    """Creates a sample SQLite database populated with schema fixtures."""
    target_path = Path(db_path).resolve()
    target_path.parent.mkdir(parents=True, exist_ok=True)

    if target_path.exists():
        target_path.unlink()

    conn = sqlite3.connect(str(target_path))
    cursor = conn.cursor()

    try:
        cursor.execute("PRAGMA foreign_keys = ON;")

        # 1. Users table
        cursor.execute(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                avatar BLOB,
                bio TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

        # 2. Products table
        cursor.execute(
            """
            CREATE TABLE products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                sku TEXT UNIQUE NOT NULL,
                price REAL NOT NULL,
                stock INTEGER DEFAULT 0,
                specifications BLOB
            );
            """
        )

        # 3. Orders table with foreign keys
        cursor.execute(
            """
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                product_id INTEGER NOT NULL REFERENCES products(id),
                quantity INTEGER NOT NULL CHECK (quantity > 0),
                total_price REAL NOT NULL,
                order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

        # 4. Audit logs table with implicit foreign key (no column named in REFERENCES users)
        cursor.execute(
            """
            CREATE TABLE audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_ref INTEGER REFERENCES users ON DELETE SET NULL,
                action TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

        # 5. Indexes (including expression index)
        cursor.execute("CREATE INDEX idx_users_email ON users(email);")
        cursor.execute("CREATE INDEX idx_orders_user_id ON orders(user_id);")
        cursor.execute("CREATE INDEX idx_orders_product_id ON orders(product_id);")
        cursor.execute("CREATE INDEX idx_products_lower_title ON products(lower(title));")

        # 6. View
        cursor.execute(
            """
            CREATE VIEW order_summary AS
            SELECT
                o.id AS order_id,
                u.name AS customer_name,
                u.email AS customer_email,
                p.title AS product_name,
                o.quantity,
                o.total_price,
                o.order_date
            FROM orders o
            JOIN users u ON o.user_id = u.id
            JOIN products p ON o.product_id = p.id;
            """
        )

        # Sample data
        dummy_avatar = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]) + b"\x00" * 64
        long_bio = (
            "Senior systems engineer with extensive background in distributed systems, "
            "database internals, and protocol engineering. " * 10
        )

        users_data = [
            ("Alice Smith", "alice@example.com", dummy_avatar, long_bio),
            ("Bob Jones", "bob@example.com", None, "Frontend architect and open-source enthusiast."),
            ("Charlie Brown", "charlie@example.com", b"\x00\x01\x02\x03\x04", None),
        ]
        cursor.executemany(
            "INSERT INTO users (name, email, avatar, bio) VALUES (?, ?, ?, ?);",
            users_data,
        )

        products_data = [
            ("Mechanical Keyboard", "KEY-MECH-01", 129.99, 50, b"RAW_SPEC_BYTES_123"),
            ("Ergonomic Mouse", "MOU-ERGO-02", 79.50, 120, None),
            ("4K Ultra HD Monitor", "MON-4K-03", 399.00, 25, b"RAW_SPEC_BYTES_456"),
        ]
        cursor.executemany(
            "INSERT INTO products (title, sku, price, stock, specifications) VALUES (?, ?, ?, ?, ?);",
            products_data,
        )

        orders_data = [
            (1, 1, 1, 129.99),
            (1, 2, 2, 159.00),
            (2, 3, 1, 399.00),
        ]
        cursor.executemany(
            "INSERT INTO orders (user_id, product_id, quantity, total_price) VALUES (?, ?, ?, ?);",
            orders_data,
        )

        audit_data = [
            (1, "LOGIN_SUCCESS"),
            (2, "PROFILE_UPDATE"),
            (None, "SYSTEM_STARTUP"),
        ]
        cursor.executemany(
            "INSERT INTO audit_logs (user_ref, action) VALUES (?, ?);",
            audit_data,
        )

        conn.commit()
    finally:
        conn.close()

    return target_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate sample SQLite database.")
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="sample.db",
        help="Path for generated SQLite database file",
    )
    args = parser.parse_args()
    path = create_sample_database(args.output)
    sys.stderr.write(f"Sample database created successfully at: {path}\n")


if __name__ == "__main__":
    main()
