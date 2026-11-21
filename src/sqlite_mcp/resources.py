"""FastMCP resource definitions for SQLite database schema."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from sqlite_mcp.db import DatabaseManager


def register_resources(mcp: FastMCP, db_manager: DatabaseManager) -> None:
    """Registers dynamic database schema resources on the FastMCP instance."""

    @mcp.resource(
        "sqlite://schema",
        name="database_schema",
        description="Complete database schema formatted in Markdown, including tables, columns, constraints, foreign keys, and DDL.",
        mime_type="text/markdown",
    )
    def get_database_schema() -> str:
        """Generates a comprehensive Markdown summary of the entire database schema."""
        return db_manager.get_database_schema_markdown()
