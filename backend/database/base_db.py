import sqlite3
import logging
import os
from contextlib import contextmanager
from typing import Dict, Any

logger = logging.getLogger("engagic")


class BaseDatabase:
    """Base class for all database connections"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_directory()
        self._init_database()
        logger.info(f"Initialized database: {os.path.basename(db_path)}")

    def _ensure_directory(self):
        """Ensure the database directory exists"""
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

    def _init_database(self):
        """Initialize database schema - override in subclasses"""
        pass

    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        # Enable foreign key constraints
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
        finally:
            conn.close()

    def execute_script(self, script: str):
        """Execute a SQL script"""
        with self.get_connection() as conn:
            conn.executescript(script)
            conn.commit()

    def get_db_stats(self) -> Dict[str, Any]:
        """Get basic database statistics"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Get table list
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]

            # Get counts for each table
            table_counts = {}
            for table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                table_counts[table] = cursor.fetchone()[0]

            # Get database file size
            file_size = (
                os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
            )

            return {
                "db_file": os.path.basename(self.db_path),
                "file_size_kb": round(file_size / 1024, 2),
                "tables": table_counts,
            }
