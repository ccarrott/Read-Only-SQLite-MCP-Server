"""Pytest fixtures for SQLite MCP Server tests."""

from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Generator
import pytest

from tests.fixtures.create_sample_db import create_sample_database


@pytest.fixture
def sample_db_path(tmp_path: Path) -> Generator[Path, None, None]:
    """Generates a populated sample SQLite database in a temp directory."""
    db_file = tmp_path / "test_sample.db"
    create_sample_database(db_file)
    yield db_file
