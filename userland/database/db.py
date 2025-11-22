"""
Userland Database

Manages user accounts, alerts, and alert matches.
Simplified from motioncount - free tier only, no billing.
"""

import sqlite3
import json
import logging
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from userland.database.models import User, Alert, AlertMatch

logger = logging.getLogger("engagic")


class UserlandDB:
    """Userland database for free tier civic alerts"""

    def __init__(self, db_path: str, silent: bool = False):
        self.db_path = db_path
        self.conn: sqlite3.Connection
        self._connect()
        self._init_schema()
        if not silent:
            logger.info(f"Initialized userland database at {db_path}")

    def _connect(self):
        """Create database connection"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")

    def _init_schema(self):
        """Initialize database schema"""
        schema = """
        -- Users (simplified from customers)
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        );

        -- Alerts
        CREATE TABLE IF NOT EXISTS alerts (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            cities TEXT NOT NULL,  -- JSON array of city bananas
            criteria TEXT NOT NULL,  -- JSON object {"keywords": [...]}
            frequency TEXT DEFAULT 'weekly',  -- weekly, daily
            active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        -- Alert matches
        CREATE TABLE IF NOT EXISTS alert_matches (
            id TEXT PRIMARY KEY,
            alert_id TEXT NOT NULL,
            meeting_id TEXT NOT NULL,
            item_id TEXT,
            match_type TEXT NOT NULL,  -- keyword, matter
            confidence REAL NOT NULL,
            matched_criteria TEXT NOT NULL,  -- JSON object
            notified BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (alert_id) REFERENCES alerts(id) ON DELETE CASCADE
        );

        -- Used magic link tokens (security: prevent replay attacks)
        CREATE TABLE IF NOT EXISTS used_magic_links (
            token_hash TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL
        );

        -- Indexes
        CREATE INDEX IF NOT EXISTS idx_alerts_user ON alerts(user_id);
        CREATE INDEX IF NOT EXISTS idx_alerts_active ON alerts(active);
        CREATE INDEX IF NOT EXISTS idx_matches_alert ON alert_matches(alert_id);
        CREATE INDEX IF NOT EXISTS idx_matches_meeting ON alert_matches(meeting_id);
        CREATE INDEX IF NOT EXISTS idx_matches_notified ON alert_matches(notified);
        CREATE INDEX IF NOT EXISTS idx_used_magic_links_expires ON used_magic_links(expires_at);
        """
        self.conn.executescript(schema)
        self.conn.commit()

    # ========== User Operations ==========

    def create_user(self, user: User) -> User:
        """Create a new user"""
        self.conn.execute(
            """
            INSERT INTO users (id, name, email, created_at, last_login)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user.id, user.name, user.email, user.created_at, user.last_login)
        )
        self.conn.commit()
        logger.info(f"Created user: {user.email}")
        return user

    def get_user(self, user_id: str) -> Optional[User]:
        """Get user by ID"""
        row = self.conn.execute(
            "SELECT * FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()

        if not row:
            return None

        return User(
            id=row["id"],
            name=row["name"],
            email=row["email"],
            created_at=datetime.fromisoformat(row["created_at"]),
            last_login=datetime.fromisoformat(row["last_login"]) if row["last_login"] else None
        )

    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email"""
        row = self.conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        ).fetchone()

        if not row:
            return None

        return User(
            id=row["id"],
            name=row["name"],
            email=row["email"],
            created_at=datetime.fromisoformat(row["created_at"]),
            last_login=datetime.fromisoformat(row["last_login"]) if row["last_login"] else None
        )

    def update_last_login(self, user_id: str):
        """Update user's last login timestamp"""
        self.conn.execute(
            "UPDATE users SET last_login = ? WHERE id = ?",
            (datetime.now(), user_id)
        )
        self.conn.commit()

    def get_user_count(self) -> int:
        """Get total user count"""
        row = self.conn.execute("SELECT COUNT(*) as count FROM users").fetchone()
        return row["count"]

    # ========== Alert Operations ==========

    def create_alert(self, alert: Alert) -> Alert:
        """Create a new alert"""
        self.conn.execute(
            """
            INSERT INTO alerts (id, user_id, name, cities, criteria, frequency, active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                alert.id,
                alert.user_id,
                alert.name,
                json.dumps(alert.cities),
                json.dumps(alert.criteria),
                alert.frequency,
                alert.active,
                alert.created_at
            )
        )
        self.conn.commit()
        logger.info(f"Created alert: {alert.name} for user {alert.user_id}")
        return alert

    def get_alert(self, alert_id: str) -> Optional[Alert]:
        """Get alert by ID"""
        row = self.conn.execute(
            "SELECT * FROM alerts WHERE id = ?",
            (alert_id,)
        ).fetchone()

        if not row:
            return None

        return Alert(
            id=row["id"],
            user_id=row["user_id"],
            name=row["name"],
            cities=json.loads(row["cities"]),
            criteria=json.loads(row["criteria"]),
            frequency=row["frequency"],
            active=bool(row["active"]),
            created_at=datetime.fromisoformat(row["created_at"])
        )

    def get_alerts(self, user_id: Optional[str] = None, active_only: bool = False) -> List[Alert]:
        """
        Get alerts, optionally filtered by user_id and/or active status.

        Args:
            user_id: Filter by user ID (None = all users)
            active_only: Only return active alerts
        """
        query = "SELECT * FROM alerts WHERE 1=1"
        params = []

        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)

        if active_only:
            query += " AND active = TRUE"

        query += " ORDER BY created_at DESC"

        rows = self.conn.execute(query, params).fetchall()

        return [
            Alert(
                id=row["id"],
                user_id=row["user_id"],
                name=row["name"],
                cities=json.loads(row["cities"]),
                criteria=json.loads(row["criteria"]),
                frequency=row["frequency"],
                active=bool(row["active"]),
                created_at=datetime.fromisoformat(row["created_at"])
            )
            for row in rows
        ]

    def get_active_alerts(self) -> List[Alert]:
        """Get all active alerts (convenience method)"""
        return self.get_alerts(active_only=True)

    def update_alert(
        self,
        alert_id: str,
        cities: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        frequency: Optional[str] = None,
        active: Optional[bool] = None
    ) -> Optional[Alert]:
        """
        Update alert configuration.

        Args:
            alert_id: Alert ID to update
            cities: New list of city bananas (None = no change)
            keywords: New list of keywords (None = no change)
            frequency: New frequency (weekly/daily, None = no change)
            active: New active status (None = no change)

        Returns:
            Updated Alert object or None if not found
        """
        alert = self.get_alert(alert_id)
        if not alert:
            return None

        # Build update query dynamically based on what's being updated
        updates = []
        params = []

        if cities is not None:
            updates.append("cities = ?")
            params.append(json.dumps(cities))

        if keywords is not None:
            # Update keywords in criteria JSON
            alert.criteria["keywords"] = keywords
            updates.append("criteria = ?")
            params.append(json.dumps(alert.criteria))

        if frequency is not None:
            updates.append("frequency = ?")
            params.append(frequency)

        if active is not None:
            updates.append("active = ?")
            params.append(active)

        if not updates:
            # No changes requested
            return alert

        query = f"UPDATE alerts SET {', '.join(updates)} WHERE id = ?"
        params.append(alert_id)

        self.conn.execute(query, params)
        self.conn.commit()

        logger.info(f"Updated alert {alert_id}: {', '.join(updates)}")

        # Return updated alert
        return self.get_alert(alert_id)

    def delete_alert(self, alert_id: str) -> bool:
        """
        Delete an alert and all its matches.

        Args:
            alert_id: Alert ID to delete

        Returns:
            True if deleted, False if not found
        """
        alert = self.get_alert(alert_id)
        if not alert:
            return False

        # Delete matches first (foreign key constraint)
        self.conn.execute("DELETE FROM alert_matches WHERE alert_id = ?", (alert_id,))

        # Delete alert
        self.conn.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))
        self.conn.commit()

        logger.info(f"Deleted alert {alert_id} and its matches")
        return True

    # ========== Alert Match Operations ==========

    def create_match(self, match: AlertMatch) -> AlertMatch:
        """Create an alert match"""
        self.conn.execute(
            """
            INSERT INTO alert_matches (id, alert_id, meeting_id, item_id, match_type,
                                     confidence, matched_criteria, notified, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                match.id,
                match.alert_id,
                match.meeting_id,
                match.item_id,
                match.match_type,
                match.confidence,
                json.dumps(match.matched_criteria),
                match.notified,
                match.created_at
            )
        )
        self.conn.commit()
        return match

    def get_matches(
        self,
        alert_id: Optional[str] = None,
        user_id: Optional[str] = None,
        notified: Optional[bool] = None,
        limit: int = 100
    ) -> List[AlertMatch]:
        """Get alert matches with filters"""
        query = "SELECT am.* FROM alert_matches am"
        params = []

        # Join with alerts if filtering by user_id
        if user_id:
            query += " JOIN alerts a ON am.alert_id = a.id WHERE a.user_id = ?"
            params.append(user_id)
        else:
            query += " WHERE 1=1"

        if alert_id:
            query += " AND am.alert_id = ?"
            params.append(alert_id)

        if notified is not None:
            query += " AND am.notified = ?"
            params.append(notified)

        query += " ORDER BY am.created_at DESC LIMIT ?"
        params.append(limit)

        rows = self.conn.execute(query, params).fetchall()

        return [
            AlertMatch(
                id=row["id"],
                alert_id=row["alert_id"],
                meeting_id=row["meeting_id"],
                item_id=row["item_id"],
                match_type=row["match_type"],
                confidence=row["confidence"],
                matched_criteria=json.loads(row["matched_criteria"]),
                notified=bool(row["notified"]),
                created_at=datetime.fromisoformat(row["created_at"])
            )
            for row in rows
        ]

    def mark_notified(self, match_id: str):
        """Mark a match as notified"""
        self.conn.execute(
            "UPDATE alert_matches SET notified = TRUE WHERE id = ?",
            (match_id,)
        )
        self.conn.commit()

    def get_match_count(self, user_id: Optional[str] = None, since_days: Optional[int] = None) -> int:
        """Get count of matches, optionally filtered"""
        query = "SELECT COUNT(*) as count FROM alert_matches am"
        params = []

        if user_id:
            query += " JOIN alerts a ON am.alert_id = a.id WHERE a.user_id = ?"
            params.append(user_id)
        else:
            query += " WHERE 1=1"

        if since_days:
            query += " AND am.created_at >= datetime('now', ?)"
            params.append(f"-{since_days} days")

        row = self.conn.execute(query, params).fetchone()
        return row["count"]

    # ========== Magic Link Token Operations ==========

    def is_magic_link_used(self, token_hash: str) -> bool:
        """Check if magic link token has already been used"""
        row = self.conn.execute(
            "SELECT 1 FROM used_magic_links WHERE token_hash = ?",
            (token_hash,)
        ).fetchone()
        return row is not None

    def mark_magic_link_used(self, token_hash: str, user_id: str, expires_at: datetime):
        """Mark magic link token as used (single-use enforcement)"""
        self.conn.execute(
            "INSERT INTO used_magic_links (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
            (token_hash, user_id, expires_at)
        )
        self.conn.commit()

    def cleanup_expired_magic_links(self):
        """Remove expired magic link tokens (cleanup maintenance)"""
        self.conn.execute(
            "DELETE FROM used_magic_links WHERE expires_at < ?",
            (datetime.now(),)
        )
        self.conn.commit()

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
