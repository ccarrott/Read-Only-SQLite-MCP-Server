"""Security module implementing native SQLite authorizers and query validation."""

from __future__ import annotations

import re
import sqlite3
from typing import Any, Optional


class SecurityError(sqlite3.DatabaseError):
    """Raised when a query violates read-only security constraints."""
    pass


# Native SQLite Action Codes strictly denied in read-only mode
FORBIDDEN_ACTIONS = {
    sqlite3.SQLITE_INSERT,
    sqlite3.SQLITE_UPDATE,
    sqlite3.SQLITE_DELETE,
    sqlite3.SQLITE_DROP_TABLE,
    sqlite3.SQLITE_DROP_INDEX,
    sqlite3.SQLITE_DROP_VIEW,
    sqlite3.SQLITE_DROP_TRIGGER,
    sqlite3.SQLITE_DROP_TEMP_INDEX,
    sqlite3.SQLITE_DROP_TEMP_TABLE,
    sqlite3.SQLITE_DROP_TEMP_TRIGGER,
    sqlite3.SQLITE_DROP_TEMP_VIEW,
    sqlite3.SQLITE_CREATE_TABLE,
    sqlite3.SQLITE_CREATE_INDEX,
    sqlite3.SQLITE_CREATE_VIEW,
    sqlite3.SQLITE_CREATE_VTABLE,
    sqlite3.SQLITE_DROP_VTABLE,
    sqlite3.SQLITE_CREATE_TRIGGER,
    sqlite3.SQLITE_CREATE_TEMP_INDEX,
    sqlite3.SQLITE_CREATE_TEMP_TABLE,
    sqlite3.SQLITE_CREATE_TEMP_TRIGGER,
    sqlite3.SQLITE_CREATE_TEMP_VIEW,
    sqlite3.SQLITE_ALTER_TABLE,
    sqlite3.SQLITE_ATTACH,
    sqlite3.SQLITE_DETACH,
    sqlite3.SQLITE_REINDEX,
    sqlite3.SQLITE_ANALYZE,
    sqlite3.SQLITE_TRANSACTION,
    sqlite3.SQLITE_SAVEPOINT,
}

# Safe introspection pragmas required for inspecting schema details
SAFE_READ_TABLE_PRAGMAS = {
    "table_info",
    "table_xinfo",
    "foreign_key_list",
    "index_list",
    "index_info",
    "index_xinfo",
}

SAFE_READ_GLOBAL_PRAGMAS = {
    "database_list",
    "collation_list",
    "query_only",
    "user_version",
    "schema_version",
    "data_version",
    "encoding",
    "compile_options",
}

ALLOWED_STATEMENT_TYPES = frozenset({"SELECT", "EXPLAIN", "WITH"})


INTERNAL_SCHEMA_TABLES = frozenset(
    {"sqlite_master", "sqlite_schema", "sqlite_temp_master", "sqlite_temp_schema"}
)


def read_only_authorizer(
    action_code: int,
    arg1: Optional[str],
    arg2: Optional[str],
    db_name: Optional[str],
    trigger_name: Optional[str],
) -> int:
    """Strict native C-level authorizer callback for user query execution.

    Denies all mutation actions unconditionally without exception.

    Returns:
        sqlite3.SQLITE_OK to allow, sqlite3.SQLITE_DENY to block.
    """
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


def introspection_authorizer(
    action_code: int,
    arg1: Optional[str],
    arg2: Optional[str],
    db_name: Optional[str],
    trigger_name: Optional[str],
) -> int:
    """Native C-level authorizer callback used strictly for schema introspection queries.

    Accommodates an internal SQLite engine behavior observed on SQLite 3.40.1
    (bundled with Windows Python 3.10), where compiling table-valued pragma queries
    (pragma_table_info, pragma_foreign_key_list, etc.) triggers an internal SQLITE_UPDATE
    callback on internal schema tables ('sqlite_master' / 'sqlite_schema').
    """
    if action_code == sqlite3.SQLITE_UPDATE and arg1 in INTERNAL_SCHEMA_TABLES:
        return sqlite3.SQLITE_OK

    return read_only_authorizer(action_code, arg1, arg2, db_name, trigger_name)


def _strip_sql_comments_and_whitespace(sql: str) -> str:
    """Removes leading SQL comments (-- and /* */) and whitespace."""
    s = sql.strip()
    while s:
        if s.startswith("--"):
            newline_idx = s.find("\n")
            if newline_idx == -1:
                return ""
            s = s[newline_idx + 1:].strip()
        elif s.startswith("/*"):
            end_idx = s.find("*/")
            if end_idx == -1:
                return ""
            s = s[end_idx + 2:].strip()
        else:
            break
    return s


def has_stacked_statements(sql: str) -> bool:
    """Detects if SQL contains multiple distinct statements separated by semicolons."""
    in_single_quote = False
    in_double_quote = False
    in_brackets = False
    in_backticks = False
    in_line_comment = False
    in_block_comment = False
    semicolon_seen = False

    i = 0
    n = len(sql)

    while i < n:
        c = sql[i]
        next_c = sql[i + 1] if i + 1 < n else ""

        if in_line_comment:
            if c == "\n":
                in_line_comment = False
        elif in_block_comment:
            if c == "*" and next_c == "/":
                in_block_comment = False
                i += 1
        elif in_single_quote:
            if c == "'":
                if next_c == "'":
                    i += 1  # Escaped single quote
                else:
                    in_single_quote = False
        elif in_double_quote:
            if c == '"':
                if next_c == '"':
                    i += 1  # Escaped double quote
                else:
                    in_double_quote = False
        elif in_brackets:
            if c == "]":
                in_brackets = False
        elif in_backticks:
            if c == "`":
                if next_c == "`":
                    i += 1  # Escaped backtick
                else:
                    in_backticks = False
        else:
            if c == "-" and next_c == "-":
                in_line_comment = True
                i += 1
            elif c == "/" and next_c == "*":
                in_block_comment = True
                i += 1
            elif c == "'":
                if semicolon_seen:
                    return True
                in_single_quote = True
            elif c == '"':
                if semicolon_seen:
                    return True
                in_double_quote = True
            elif c == "[":
                if semicolon_seen:
                    return True
                in_brackets = True
            elif c == "`":
                if semicolon_seen:
                    return True
                in_backticks = True
            elif c == ";":
                semicolon_seen = True
            elif not c.isspace():
                if semicolon_seen:
                    return True

        i += 1

    return False


def validate_sql_statement(sql: str) -> None:
    """Inspects SQL statement syntax and rejects non-read-only or stacked queries."""
    if not sql or not sql.strip():
        raise SecurityError("SQL statement cannot be empty.")

    cleaned = _strip_sql_comments_and_whitespace(sql)
    if not cleaned:
        raise SecurityError("SQL statement contains only comments or whitespace.")

    match = re.match(r"^([a-zA-Z]+)", cleaned)
    if not match:
        raise SecurityError("Unable to identify SQL statement keyword.")

    first_keyword = match.group(1).upper()
    if first_keyword not in ALLOWED_STATEMENT_TYPES:
        raise SecurityError(
            f"Statement type '{first_keyword}' is forbidden. Only SELECT, EXPLAIN, and WITH queries are permitted."
        )

    if has_stacked_statements(sql):
        raise SecurityError("Multi-Statement Deny: Stacked or multiple queries are not allowed.")
