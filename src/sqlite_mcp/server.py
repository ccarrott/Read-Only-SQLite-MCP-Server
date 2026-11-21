"""FastMCP server initialization, CLI entry point, and stdio execution."""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
import sys
from typing import Optional, Union

from mcp.server.fastmcp import FastMCP
from sqlite_mcp.db import DatabaseManager
from sqlite_mcp.prompts import register_prompts
from sqlite_mcp.resources import register_resources
from sqlite_mcp.tools import register_tools


def configure_stderr_logging(level: int = logging.INFO) -> logging.Logger:
    """Configures application logger to write exclusively to sys.stderr to protect stdio JSON-RPC stream."""
    logger = logging.getLogger("sqlite_mcp")
    logger.setLevel(level)

    # Avoid adding duplicate handlers if reconfigured
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    logger.propagate = False
    return logger


def create_mcp_server(
    db_path: Union[str, Path],
    server_name: str = "sqlite-explorer",
) -> FastMCP:
    """Creates and configures a FastMCP server instance bound to the target SQLite database."""
    resolved_path = Path(db_path).resolve()
    if not resolved_path.exists():
        raise FileNotFoundError(f"Database file does not exist: {resolved_path}")

    db_manager = DatabaseManager(resolved_path)
    mcp = FastMCP(server_name)

    register_tools(mcp, db_manager)
    register_resources(mcp, db_manager)
    register_prompts(mcp, db_manager)

    return mcp


def parse_arguments(args: Optional[list[str]] = None) -> argparse.Namespace:
    """Parses command-line arguments for the SQLite MCP server."""
    parser = argparse.ArgumentParser(
        prog="sqlite-mcp",
        description="Safe Read-Only SQLite Explorer MCP Server",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=os.environ.get("SQLITE_DB_PATH"),
        help="Absolute or relative path to the SQLite database file (can also be set via SQLITE_DB_PATH env var)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default=os.environ.get("LOG_LEVEL", "INFO").upper(),
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging severity level (outputs to stderr)",
    )

    parsed = parser.parse_args(args)
    if not parsed.db_path:
        parser.error("A database path is required. Specify via '--db-path' or environment variable 'SQLITE_DB_PATH'.")

    return parsed


def main() -> None:
    """Server entry point executing over standard I/O (stdio)."""
    parsed = parse_arguments()
    log_level = getattr(logging, parsed.log_level, logging.INFO)
    logger = configure_stderr_logging(level=log_level)

    logger.info("Initializing SQLite MCP Server...")
    logger.info("Target database: %s", parsed.db_path)

    try:
        mcp_server = create_mcp_server(parsed.db_path)
        logger.info("Starting FastMCP stdio transport listener...")
        mcp_server.run(transport="stdio")
    except Exception as exc:
        logger.critical("Fatal error running SQLite MCP Server: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
