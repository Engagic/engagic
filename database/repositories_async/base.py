"""Base repository with async PostgreSQL connection pooling

All repositories inherit from BaseRepository and share:
- Connection pool (no connection per-instance)
- Transaction context managers
- Query execution helpers with proper error handling
- Logging infrastructure
"""

import asyncpg
import json
from typing import Any, List, Optional
from contextlib import asynccontextmanager

from config import get_logger

logger = get_logger(__name__).bind(component="repository")


class BaseRepository:
    """Base class for async PostgreSQL repositories

    Provides connection pool management and query execution helpers.
    All subclasses share the same connection pool for efficiency.

    Design Principles:
    - Pool is passed in, not created (singleton pattern)
    - Transactions are explicit (async with self.transaction())
    - Queries use $1, $2 placeholders (PostgreSQL parameterization)
    - All methods are async (no sync fallbacks)
    """

    def __init__(self, pool: asyncpg.Pool):
        """Initialize repository with shared connection pool

        Args:
            pool: asyncpg connection pool (shared across all repositories)
        """
        self.pool = pool

    async def _fetchrow(self, query: str, *args: Any) -> Optional[asyncpg.Record]:
        """Execute query and fetch single row"""
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def _fetch(self, query: str, *args: Any) -> List[asyncpg.Record]:
        """Execute query and fetch all rows"""
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def _execute(self, query: str, *args: Any) -> str:
        """Execute query without returning rows (INSERT, UPDATE, DELETE)"""
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def _executemany(self, query: str, args: List[tuple]) -> None:
        """Execute query multiple times with different parameters

        More efficient than looping _execute() for bulk operations.

        Args:
            query: SQL query with $1, $2, etc. placeholders
            args: List of parameter tuples
        """
        async with self.pool.acquire() as conn:
            await conn.executemany(query, args)

    @asynccontextmanager
    async def transaction(self):
        """Context manager for explicit transactions

        Usage:
            async with self.transaction() as conn:
                await conn.execute("INSERT ...")
                await conn.execute("UPDATE ...")
                # Auto-commits on successful exit
                # Auto-rolls back on exception

        Yields:
            Connection with active transaction
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                yield conn

    @staticmethod
    def _deserialize_jsonb(value: Any, default: Any = None) -> Any:
        """JSONB deserialization with error raising (not defensive)

        asyncpg automatically deserializes JSONB columns to dict/list.
        If value is a string, that indicates a data integrity issue - raise error.

        Args:
            value: JSONB field value from database (should be dict/list or None)
            default: Default value if None

        Returns:
            Deserialized value or default

        Raises:
            ValueError: If value is a string (indicates data corruption)
            json.JSONDecodeError: If string parsing attempted and fails
        """
        if value is None:
            return default

        # asyncpg auto-deserializes JSONB to dict/list
        # If we get a string, data is corrupted or schema mismatch
        if isinstance(value, str):
            logger.error(
                "jsonb field returned string (expected dict/list)",
                value_preview=value[:100],
                value_type=type(value).__name__
            )
            # Attempt parse with error raised on failure
            return json.loads(value)

        return value
