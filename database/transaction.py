"""
Database transaction management

Provides context managers for explicit transaction control.
Replaces the defer_commit anti-pattern with clean transaction boundaries.
"""

from contextlib import contextmanager
from typing import Optional
import sqlite3

from config import get_logger

logger = get_logger(__name__).bind(component="transaction")


@contextmanager
def transaction(conn: sqlite3.Connection, rollback_on_exception: bool = True):
    """Context manager for database transactions

    Provides explicit transaction boundaries with automatic commit/rollback.
    Replaces defer_commit flag pattern with clear transaction scope.

    Args:
        conn: SQLite connection object
        rollback_on_exception: If True, rollback on any exception (default: True)

    Yields:
        The connection object (for convenience)

    Example:
        with transaction(db.conn):
            db.items.store_agenda_items(meeting_id, items)
            db.matters.store_matter(matter)
            # Automatic commit on success, rollback on exception

    Confidence: 9/10 - Standard transaction pattern
    """
    try:
        yield conn
        conn.commit()
        logger.debug("transaction committed")
    except Exception as e:
        if rollback_on_exception:
            conn.rollback()
            logger.warning("transaction rolled back", error=str(e), error_type=type(e).__name__)
        raise


@contextmanager
def savepoint(conn: sqlite3.Connection, name: Optional[str] = None):
    """Context manager for nested transactions using savepoints

    Allows nested transaction-like behavior within a larger transaction.
    Useful for partial rollbacks without aborting entire transaction.

    Args:
        conn: SQLite connection object
        name: Optional savepoint name (auto-generated if not provided)

    Yields:
        The savepoint name

    Example:
        with transaction(db.conn):
            db.meetings.store_meeting(meeting)

            with savepoint(db.conn, "items"):
                try:
                    db.items.store_agenda_items(meeting_id, items)
                except Exception:
                    # Items rollback, meeting preserved
                    pass

    Confidence: 8/10 - SQLite savepoint support
    """
    import time

    savepoint_name = name or f"sp_{int(time.time() * 1000000)}"

    try:
        conn.execute(f"SAVEPOINT {savepoint_name}")
        logger.debug("savepoint created", name=savepoint_name)
        yield savepoint_name
        conn.execute(f"RELEASE SAVEPOINT {savepoint_name}")
        logger.debug("savepoint released", name=savepoint_name)
    except Exception as e:
        conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
        logger.warning("savepoint rolled back", name=savepoint_name, error=str(e))
        raise
