"""FastAPI dependencies."""
from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import aiosqlite

from mri.db.repository import default_db_path, get_connection


async def db_conn() -> AsyncIterator[aiosqlite.Connection]:
    async with get_connection() as conn:
        yield conn


def get_db_path() -> Path:
    return default_db_path()