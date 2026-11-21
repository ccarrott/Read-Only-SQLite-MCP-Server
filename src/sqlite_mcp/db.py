"""SQLite connection manager, execution engine, and data serializer."""

from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import time
from typing import Any, Dict, List, Optional, Sequence, Union

from sqlite_mcp.security import (
    SecurityError,
    read_only_authorizer,
    validate_sql_statement,
)

MAX_CELL_CHARS = 500
DEFAULT_ROW_LIMIT = 100
MAX_ROW_LIMIT = 1000
FALLBACK_MAX_INSTRUCTIONS = 10_000_000
PROGRESS_STEP_SIZE = 10_000


def get_default_max_instructions() -> int:
    """Dynamically resolves default instruction limit from environment, falling back safely on invalid values."""
    raw = os.environ.get("SQLITE_MAX_INSTRUCTIONS")
    if raw:
        try:
            val = int(raw.strip())
            if val > 0:
                return val
        except ValueError:
            pass
    return FALLBACK_MAX_INSTRUCTIONS


class QueryInstructionLimiter:
    """Monitors virtual VM instruction count to abort runaway queries."""

    def __init__(self, max_instructions: Optional[int] = None, step: int = PROGRESS_STEP_SIZE):
        self.max_instructions = max_instructions if max_instructions is not None else get_default_max_instructions()
        self.step = step
        self.count = 0

    def reset(self) -> None:
        """Resets the VM instruction step counter."""
        self.count = 0

    def __call__(self) -> int:
        self.count += self.step
        if self.count > self.max_instructions:
            return 1  # Non-zero return instructs SQLite to interrupt execution
        return 0


def sanitize_cell(value: Any) -> Any:
    """Converts raw SQLite cell values into safe, JSON-serializable formats."""
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"<BLOB {len(value)} bytes>"
    if isinstance(value, str):
        if len(value) > MAX_CELL_CHARS:
            return value[:MAX_CELL_CHARS] + "... [truncated]"
        return value
    if isinstance(value, (int, float, bool)):
        return value
    return str(value)


def sanitize_row(row: Sequence[Any]) -> List[Any]:
    """Sanitizes each cell in a returned database row."""
    return [sanitize_cell(cell) for cell in row]


class DatabaseManager:
    """Manages read-only connections and safe query execution against SQLite databases."""

    def __init__(self, db_path: Union[str, Path], max_instructions: Optional[int] = None):
        self.db_path = Path(db_path).resolve()
        self.max_instructions = max_instructions if max_instructions is not None else get_default_max_instructions()
        self.step_size = min(PROGRESS_STEP_SIZE, max(1, self.max_instructions // 10))

    def get_connection(self, limiter: Optional[QueryInstructionLimiter] = None) -> sqlite3.Connection:
        """Opens a protected, read-only connection adhering to 4-layer defense."""
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database file not found: {self.db_path}")

        # Layer 1: OS/Driver URI read-only mode with RFC 3986 percent-encoding
        uri = f"{self.db_path.resolve().as_uri()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=10.0)

        # Layer 3: Engine Pragma query_only enforcement (enabled before registering authorizer)
        conn.execute("PRAGMA query_only = ON;")

        # Layer 2: Native SQLite C-level authorizer
        conn.set_authorizer(read_only_authorizer)

        # Progress handler for query instruction limit
        if limiter is not None:
            conn.set_progress_handler(limiter, limiter.step)
        else:
            conn.set_progress_handler(None, 0)

        return conn

    def execute_query(
        self,
        sql: str,
        params: Sequence[Any] = (),
        max_rows: int = DEFAULT_ROW_LIMIT,
    ) -> Dict[str, Any]:
        """Safely executes a read-only query and returns formatted, sanitized results."""
        # Layer 4: Statement syntax & multi-query inspection
        validate_sql_statement(sql)

        clamped_limit = min(max(1, max_rows), MAX_ROW_LIMIT)
        query_limiter = QueryInstructionLimiter(max_instructions=self.max_instructions, step=self.step_size)

        conn = self.get_connection(limiter=query_limiter)
        try:
            start_time = time.perf_counter()
            cursor = conn.cursor()
            cursor.execute(sql, params)

            columns = [desc[0] for desc in cursor.description] if cursor.description else []

            # Fetch clamped_limit + 1 to detect whether results were truncated
            fetched = cursor.fetchmany(clamped_limit + 1)
            duration_ms = round((time.perf_counter() - start_time) * 1000, 3)

            is_truncated = len(fetched) > clamped_limit
            rows_to_format = fetched[:clamped_limit] if is_truncated else fetched
            sanitized_rows = [sanitize_row(row) for row in rows_to_format]

            return {
                "columns": columns,
                "rows": sanitized_rows,
                "row_count": len(sanitized_rows),
                "is_truncated": is_truncated,
                "limit_applied": clamped_limit,
                "execution_time_ms": duration_ms,
            }
        finally:
            conn.close()

    def list_tables(self, include_internal: bool = False) -> List[Dict[str, Any]]:
        """Lists user tables, views, and index counts."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT type, name, tbl_name
                FROM sqlite_master
                WHERE type IN ('table', 'view')
                ORDER BY type, name;
                """
            )
            raw_objects = cursor.fetchall()

            result = []
            for obj_type, name, tbl_name in raw_objects:
                if not include_internal and name.startswith("sqlite_"):
                    continue

                # Query index count for this table
                cursor.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND tbl_name = ?;",
                    (tbl_name,),
                )
                index_count = cursor.fetchone()[0]

                result.append(
                    {
                        "name": name,
                        "type": obj_type,
                        "index_count": index_count,
                    }
                )
            return result
        finally:
            conn.close()

    def describe_table(self, table_name: str) -> Dict[str, Any]:
        """Provides in-depth column definitions, constraints, foreign keys, and DDL for a table."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT type, sql FROM sqlite_master WHERE name = ? AND type IN ('table', 'view');",
                (table_name,),
            )
            obj = cursor.fetchone()
            if not obj:
                raise ValueError(f"Table or view '{table_name}' does not exist.")

            obj_type, ddl = obj[0], obj[1]

            # 1. Column details: cid, name, type, notnull, dflt_value, pk
            cursor.execute(
                'SELECT cid, name, type, "notnull", dflt_value, pk FROM pragma_table_info(?);',
                (table_name,),
            )
            raw_cols = cursor.fetchall()
            columns = [
                {
                    "cid": col[0],
                    "name": col[1],
                    "type": col[2],
                    "not_null": bool(col[3]),
                    "default_value": col[4],
                    "is_primary_key": bool(col[5]),
                }
                for col in raw_cols
            ]

            # 2. Foreign keys: id, seq, table, from, to, on_update, on_delete, match
            cursor.execute(
                'SELECT id, seq, "table", "from", "to", on_update, on_delete FROM pragma_foreign_key_list(?);',
                (table_name,),
            )
            raw_fks = cursor.fetchall()
            foreign_keys = [
                {
                    "id": fk[0],
                    "table": fk[2],
                    "from_column": fk[3],
                    "to_column": fk[4],
                    "on_update": fk[5],
                    "on_delete": fk[6],
                }
                for fk in raw_fks
            ]

            # 3. Indexes
            cursor.execute(
                'SELECT seq, name, "unique", origin, partial FROM pragma_index_list(?);',
                (table_name,),
            )
            raw_indexes = cursor.fetchall()
            indexes = []
            for idx in raw_indexes:
                idx_name = idx[1]
                is_unique = bool(idx[2])
                cursor.execute(
                    'SELECT seqno, cid, name FROM pragma_index_info(?);',
                    (idx_name,),
                )
                idx_cols = [row[2] for row in cursor.fetchall()]
                indexes.append(
                    {
                        "name": idx_name,
                        "unique": is_unique,
                        "columns": idx_cols,
                    }
                )

            return {
                "table_name": table_name,
                "type": obj_type,
                "ddl": ddl,
                "columns": columns,
                "foreign_keys": foreign_keys,
                "indexes": indexes,
            }
        finally:
            conn.close()

    def get_database_schema_markdown(self) -> str:
        """Returns the full database schema formatted as a clean Markdown document."""
        tables = self.list_tables(include_internal=False)
        lines = ["# Database Schema\n"]

        for item in tables:
            t_name = item["name"]
            desc = self.describe_table(t_name)
            lines.append(f"## {desc['type'].capitalize()}: `{t_name}`\n")

            if desc["columns"]:
                lines.append("### Columns")
                lines.append("| Name | Type | Not Null | Default | PK |")
                lines.append("| --- | --- | --- | --- | --- |")
                for c in desc["columns"]:
                    dflt = c["default_value"] if c["default_value"] is not None else "-"
                    lines.append(
                        f"| {c['name']} | {c['type'] or 'ANY'} | {c['not_null']} | {dflt} | {c['is_primary_key']} |"
                    )
                lines.append("")

            if desc["foreign_keys"]:
                lines.append("### Foreign Keys")
                for fk in desc["foreign_keys"]:
                    lines.append(
                        f"- `{fk['from_column']}` -> `{fk['table']}({fk['to_column']})` (ON DELETE {fk['on_delete']})"
                    )
                lines.append("")

            if desc["indexes"]:
                lines.append("### Indexes")
                for idx in desc["indexes"]:
                    uniq = "UNIQUE " if idx["unique"] else ""
                    cols = ", ".join(f"`{c}`" for c in idx["columns"])
                    lines.append(f"- {uniq}Index `{idx['name']}` on ({cols})")
                lines.append("")

            if desc["ddl"]:
                lines.append("### DDL")
                lines.append("```sql")
                lines.append(desc["ddl"].strip())
                lines.append("```\n")

        return "\n".join(lines)
