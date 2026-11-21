"""FastMCP tool definitions for safe SQLite inspection."""

from __future__ import annotations

import sqlite3
from typing import Dict, List, Optional, Union
from pydantic import BaseModel, Field

from mcp.server.fastmcp import FastMCP
from sqlite_mcp.db import DatabaseManager, DEFAULT_ROW_LIMIT
from sqlite_mcp.security import SecurityError

# Concrete primitive types permitted in serialized SQLite result sets
CellValue = Union[str, int, float, bool, None]


class TableInfo(BaseModel):
    name: str = Field(description="Name of the table or view")
    type: str = Field(description="Object type ('table' or 'view')")
    index_count: int = Field(description="Number of indexes associated with this table")


class ListTablesResponse(BaseModel):
    success: bool = True
    error: Optional[str] = None
    tables: List[TableInfo] = Field(default_factory=list)
    total_count: int = 0


class ColumnInfo(BaseModel):
    cid: int
    name: str
    type: str
    not_null: bool
    default_value: Optional[Union[str, int, float, bool]] = None
    is_primary_key: bool


class ForeignKeyInfo(BaseModel):
    id: int
    table: str
    from_column: str
    to_column: str
    on_update: str
    on_delete: str


class IndexInfo(BaseModel):
    name: str
    unique: bool
    columns: List[str]


class DescribeTableResponse(BaseModel):
    success: bool = True
    error: Optional[str] = None
    table_name: str
    type: Optional[str] = None
    ddl: Optional[str] = None
    columns: List[ColumnInfo] = Field(default_factory=list)
    foreign_keys: List[ForeignKeyInfo] = Field(default_factory=list)
    indexes: List[IndexInfo] = Field(default_factory=list)


class QueryExecutionResponse(BaseModel):
    success: bool
    error: Optional[str] = None
    columns: List[str] = Field(default_factory=list)
    rows: List[List[CellValue]] = Field(default_factory=list)
    row_count: int = 0
    is_truncated: bool = False
    limit_applied: Optional[int] = None
    execution_time_ms: float = 0.0


def register_tools(mcp: FastMCP, db_manager: DatabaseManager) -> None:
    """Registers list_tables, describe_table, and execute_query tools on the FastMCP instance."""

    @mcp.tool(
        name="list_tables",
        description="Lists all tables and views in the SQLite database, including index counts.",
    )
    def list_tables(include_internal: bool = False) -> ListTablesResponse:
        """List all tables and views in the connected SQLite database.

        Args:
            include_internal: If True, includes internal SQLite tables (e.g. sqlite_sequence). Default is False.
        """
        try:
            raw_tables = db_manager.list_tables(include_internal=include_internal)
            table_models = [
                TableInfo(
                    name=t["name"],
                    type=t["type"],
                    index_count=t["index_count"],
                )
                for t in raw_tables
            ]
            return ListTablesResponse(
                success=True,
                tables=table_models,
                total_count=len(table_models),
            )
        except Exception as e:
            return ListTablesResponse(
                success=False,
                error=str(e),
                tables=[],
                total_count=0,
            )

    @mcp.tool(
        name="describe_table",
        description="Provides column definitions, primary keys, foreign keys, indexes, and raw DDL for a table or view.",
    )
    def describe_table(table_name: str) -> DescribeTableResponse:
        """Inspects table schema details, constraints, indexes, and DDL.

        Args:
            table_name: The name of the table or view to describe.
        """
        try:
            desc = db_manager.describe_table(table_name)
            return DescribeTableResponse(
                success=True,
                table_name=desc["table_name"],
                type=desc["type"],
                ddl=desc["ddl"],
                columns=[ColumnInfo(**col) for col in desc["columns"]],
                foreign_keys=[ForeignKeyInfo(**fk) for fk in desc["foreign_keys"]],
                indexes=[IndexInfo(**idx) for idx in desc["indexes"]],
            )
        except Exception as e:
            return DescribeTableResponse(
                success=False,
                error=str(e),
                table_name=table_name,
            )

    @mcp.tool(
        name="execute_query",
        description="Safely executes a read-only SQL query (SELECT, EXPLAIN, WITH) with automatic row limiting and data sanitization.",
    )
    def execute_query(query: str, max_rows: int = DEFAULT_ROW_LIMIT) -> QueryExecutionResponse:
        """Executes a read-only SQL statement against the SQLite database.

        Args:
            query: SQL query starting with SELECT, EXPLAIN, or WITH.
            max_rows: Maximum number of rows to return (default 100, max 1000).
        """
        try:
            res = db_manager.execute_query(sql=query, max_rows=max_rows)
            return QueryExecutionResponse(
                success=True,
                columns=res["columns"],
                rows=res["rows"],
                row_count=res["row_count"],
                is_truncated=res["is_truncated"],
                limit_applied=res["limit_applied"],
                execution_time_ms=res["execution_time_ms"],
            )
        except (SecurityError, sqlite3.Error, ValueError, FileNotFoundError) as e:
            return QueryExecutionResponse(
                success=False,
                error=str(e),
            )
        except Exception as e:
            return QueryExecutionResponse(
                success=False,
                error=f"Unexpected error: {str(e)}",
            )
