import sqlite3
import logging
import os
import re
import threading
import queue
from contextlib import contextmanager
from typing import Dict, Any

logger = logging.getLogger("engagic")


class ConnectionPool:
    """Thread-safe SQLite connection pool for better performance"""
    
    def __init__(self, db_path: str, max_connections: int = 5):
        self.db_path = db_path
        self.max_connections = max_connections
        self._pool = queue.Queue(maxsize=max_connections)
        self._lock = threading.Lock()
        self._created_connections = 0
        
        # Pre-create initial connections
        for _ in range(min(2, max_connections)):
            self._create_connection()
    
    def _create_connection(self):
        """Create a new database connection with optimizations"""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # Enable WAL mode for better concurrency
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")  # Faster writes
        conn.execute("PRAGMA cache_size=10000")  # Larger cache
        conn.execute("PRAGMA temp_store=MEMORY")  # Use memory for temp tables
        conn.execute("PRAGMA foreign_keys = ON")  # Enable foreign keys
        self._pool.put(conn)
        self._created_connections += 1
    
    def get_connection(self, timeout: float = 5.0):
        """Get a connection from the pool"""
        try:
            # Try to get existing connection
            conn = self._pool.get(block=False)
            # Test if connection is still alive
            conn.execute("SELECT 1")
            return conn
        except queue.Empty:
            # Create new connection if under limit
            with self._lock:
                if self._created_connections < self.max_connections:
                    self._create_connection()
                    return self._pool.get(block=False)
            # Wait for a connection to become available
            return self._pool.get(block=True, timeout=timeout)
        except sqlite3.Error:
            # Connection is dead, create a new one
            with self._lock:
                if self._created_connections < self.max_connections:
                    self._create_connection()
                    return self._pool.get(block=False)
            raise
    
    def return_connection(self, conn):
        """Return a connection to the pool"""
        if conn:
            try:
                # Test connection is still good
                conn.execute("SELECT 1")
                conn.rollback()  # Clear any uncommitted transactions
                self._pool.put(conn)
            except:
                # Connection is bad, decrease count so a new one can be created
                with self._lock:
                    self._created_connections -= 1


class BaseDatabase:
    """Base class for all database connections with connection pooling"""
    
    # Class-level connection pools (shared across instances)
    _pools = {}
    _pool_lock = threading.Lock()

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_directory()
        
        # Get or create connection pool for this database
        with self._pool_lock:
            if db_path not in self._pools:
                self._pools[db_path] = ConnectionPool(db_path, max_connections=10)
            self._pool = self._pools[db_path]
        
        self._init_database()
        logger.info(f"Initialized database with connection pool: {os.path.basename(db_path)}")

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
        """Context manager for pooled database connections"""
        conn = None
        try:
            conn = self._pool.get_connection()
            yield conn
        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                self._pool.return_connection(conn)

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
                # Validate table name to prevent injection (even though these come from sqlite_master)
                if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table):
                    logger.warning(f"Skipping table with invalid name: {table}")
                    continue
                # Use identifier quoting for table names
                cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
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
