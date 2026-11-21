"""FastMCP prompt templates for schema analysis and optimization."""

from __future__ import annotations

import re

from mcp.server.fastmcp import FastMCP
from sqlite_mcp.db import DatabaseManager


def register_prompts(mcp: FastMCP, db_manager: DatabaseManager) -> None:
    """Registers pre-engineered analysis prompts on the FastMCP instance."""

    @mcp.prompt(
        name="analyze_schema",
        description="Generates an expert analysis prompt instructing the agent to audit schema design, indexing, and normalization.",
    )
    def analyze_schema(focus: str = "general") -> str:
        """Constructs a prompt containing current schema details and analysis instructions.

        Args:
            focus: Specific area of attention (e.g., 'indexes', 'performance', 'normalization', 'general').
        """
        schema_markdown = db_manager.get_database_schema_markdown()
        # Collapse whitespace to prevent formatting breakouts
        sanitized_focus = " ".join(focus.split()) if focus else "general"

        # Compute dynamic fence length: at least 4 backticks and longer than any backtick run in the schema
        runs = re.findall(r"`+", schema_markdown)
        max_run = max((len(r) for r in runs), default=0)
        fence = "`" * max(4, max_run + 1)

        return (
            "You are an expert SQLite database administrator.\n"
            f"Please conduct an in-depth audit of the database schema below, focusing on '{sanitized_focus}'.\n\n"
            "### Target Database Schema (Untrusted Database Content):\n"
            f"{fence}markdown\n"
            f"{schema_markdown}\n"
            f"{fence}\n\n"
            "### Review Guidelines:\n"
            "1. Examine table normalization, data types, and nullability constraints.\n"
            "2. Audit index coverage, specifically checking foreign keys and join candidates for missing indexes.\n"
            "3. Check for potential query performance bottlenecks.\n"
            "4. Propose safe, non-destructive migration suggestions if improvements are needed."
        )
