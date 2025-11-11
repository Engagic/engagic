"""
Base Repository for database operations

Provides shared connection and common utilities for all repositories.
"""

import sqlite3
from typing import Optional

from exceptions import DatabaseConnectionError, DatabaseError


class BaseRepository:
    """Base class for all repositories with shared connection"""

    def __init__(self, conn: Optional[sqlite3.Connection] = None):
        """
        Initialize repository with database connection

        Args:
            conn: SQLite connection (shared across all repositories)
        """
        self.conn = conn

    def _execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """
        Execute SQL query with parameters

        Args:
            query: SQL query string
            params: Query parameters

        Returns:
            Cursor with results

        Raises:
            DatabaseConnectionError: If connection not established
            DatabaseError: If query execution fails
        """
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        try:
            cursor = self.conn.cursor()
            cursor.execute(query, params)
            return cursor
        except sqlite3.Error as e:
            raise DatabaseError(f"Query execution failed: {e}", context={'query': query[:100]})

    def _fetch_one(self, query: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        """
        Execute query and fetch one result

        Args:
            query: SQL query string
            params: Query parameters

        Returns:
            Single row or None
        """
        cursor = self._execute(query, params)
        return cursor.fetchone()

    def _fetch_all(self, query: str, params: tuple = ()) -> list[sqlite3.Row]:
        """
        Execute query and fetch all results

        Args:
            query: SQL query string
            params: Query parameters

        Returns:
            List of rows
        """
        cursor = self._execute(query, params)
        return cursor.fetchall()

    def _commit(self):
        """Commit current transaction

        Raises:
            DatabaseConnectionError: If connection not established
            DatabaseError: If commit fails
        """
        if self.conn is None:
            raise DatabaseConnectionError("Database connection not established")

        try:
            self.conn.commit()
        except sqlite3.Error as e:
            raise DatabaseError(f"Transaction commit failed: {e}")
