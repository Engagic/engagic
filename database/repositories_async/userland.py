"""
Userland Repository - User authentication and alert management

Handles user accounts, alert configurations, alert matches, and magic link security.
Pure async PostgreSQL implementation using 'userland' schema namespace.
"""

from typing import Optional, List
from datetime import datetime
import json

from database.repositories_async.base import BaseRepository
from userland.database.models import User, Alert, AlertMatch


class UserlandRepository(BaseRepository):
    """Async repository for userland tables (users, alerts, matches, magic links)"""

    # ========== User Operations ==========

    async def create_user(self, user: User) -> User:
        """Create a new user account

        Args:
            user: User dataclass with id, name, email

        Returns:
            Created user object

        Raises:
            DataIntegrityError: If email already exists (UNIQUE constraint)
        """
        async with self.transaction() as conn:
            await conn.execute(
                """
                INSERT INTO userland.users (id, name, email, created_at, last_login)
                VALUES ($1, $2, $3, $4, $5)
                """,
                user.id,
                user.name,
                user.email,
                user.created_at,
                user.last_login
            )
        return user

    async def get_user(self, user_id: str) -> Optional[User]:
        """Get user by ID

        Args:
            user_id: User identifier

        Returns:
            User object or None if not found
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM userland.users WHERE id = $1",
                user_id
            )

        if not row:
            return None

        return User(
            id=row["id"],
            name=row["name"],
            email=row["email"],
            created_at=row["created_at"],
            last_login=row["last_login"]
        )

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email address (case-insensitive lookup)

        Args:
            email: User email address

        Returns:
            User object or None if not found
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM userland.users WHERE LOWER(email) = LOWER($1)",
                email
            )

        if not row:
            return None

        return User(
            id=row["id"],
            name=row["name"],
            email=row["email"],
            created_at=row["created_at"],
            last_login=row["last_login"]
        )

    async def update_last_login(self, user_id: str) -> None:
        """Update user's last login timestamp to current time

        Args:
            user_id: User identifier
        """
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE userland.users SET last_login = $1 WHERE id = $2",
                datetime.now(),
                user_id
            )

    async def get_user_count(self) -> int:
        """Get total count of registered users

        Returns:
            Total number of users
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT COUNT(*) as count FROM userland.users")
        return row["count"]

    # ========== Alert Operations ==========

    async def create_alert(self, alert: Alert) -> Alert:
        """Create a new alert configuration

        Args:
            alert: Alert dataclass with configuration

        Returns:
            Created alert object
        """
        async with self.transaction() as conn:
            await conn.execute(
                """
                INSERT INTO userland.alerts
                (id, user_id, name, cities, criteria, frequency, active, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                alert.id,
                alert.user_id,
                alert.name,
                json.dumps(alert.cities),  # List → JSONB
                json.dumps(alert.criteria),  # Dict → JSONB
                alert.frequency,
                alert.active,
                alert.created_at
            )
        return alert

    async def get_alert(self, alert_id: str) -> Optional[Alert]:
        """Get alert by ID

        Args:
            alert_id: Alert identifier

        Returns:
            Alert object or None if not found
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM userland.alerts WHERE id = $1",
                alert_id
            )

        if not row:
            return None

        return Alert(
            id=row["id"],
            user_id=row["user_id"],
            name=row["name"],
            cities=row["cities"],  # JSONB → Python list automatically
            criteria=row["criteria"],  # JSONB → Python dict automatically
            frequency=row["frequency"],
            active=row["active"],
            created_at=row["created_at"]
        )

    async def get_alerts(
        self,
        user_id: Optional[str] = None,
        active_only: bool = False
    ) -> List[Alert]:
        """Get alerts with optional filtering

        Args:
            user_id: Filter by user ID (None = all users)
            active_only: Only return active alerts

        Returns:
            List of Alert objects
        """
        query = "SELECT * FROM userland.alerts WHERE 1=1"
        params = []

        if user_id:
            params.append(user_id)
            query += f" AND user_id = ${len(params)}"

        if active_only:
            query += " AND active = TRUE"

        query += " ORDER BY created_at DESC"

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        return [
            Alert(
                id=row["id"],
                user_id=row["user_id"],
                name=row["name"],
                cities=row["cities"],
                criteria=row["criteria"],
                frequency=row["frequency"],
                active=row["active"],
                created_at=row["created_at"]
            )
            for row in rows
        ]

    async def get_active_alerts(self) -> List[Alert]:
        """Get all active alerts (convenience method for weekly digest)

        Returns:
            List of active Alert objects
        """
        return await self.get_alerts(active_only=True)

    async def update_alert(
        self,
        alert_id: str,
        cities: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        frequency: Optional[str] = None,
        active: Optional[bool] = None
    ) -> Optional[Alert]:
        """Update alert configuration

        Args:
            alert_id: Alert ID to update
            cities: New list of city bananas (None = no change)
            keywords: New list of keywords (None = no change)
            frequency: New frequency (weekly/daily, None = no change)
            active: New active status (None = no change)

        Returns:
            Updated Alert object or None if not found
        """
        # Get current alert to merge updates
        alert = await self.get_alert(alert_id)
        if not alert:
            return None

        # Build dynamic update query
        updates = []
        params = []

        if cities is not None:
            params.append(json.dumps(cities))
            updates.append(f"cities = ${len(params)}")

        if keywords is not None:
            # Update keywords in criteria JSON
            alert.criteria["keywords"] = keywords
            params.append(json.dumps(alert.criteria))
            updates.append(f"criteria = ${len(params)}")

        if frequency is not None:
            params.append(frequency)
            updates.append(f"frequency = ${len(params)}")

        if active is not None:
            params.append(active)
            updates.append(f"active = ${len(params)}")

        if not updates:
            # No changes requested
            return alert

        # Add alert_id as final parameter
        params.append(alert_id)
        query = f"UPDATE userland.alerts SET {', '.join(updates)} WHERE id = ${len(params)}"

        async with self.pool.acquire() as conn:
            await conn.execute(query, *params)

        # Return updated alert
        return await self.get_alert(alert_id)

    async def delete_alert(self, alert_id: str) -> bool:
        """Delete an alert and all its matches (CASCADE)

        Args:
            alert_id: Alert ID to delete

        Returns:
            True if deleted, False if not found
        """
        async with self.transaction() as conn:
            result = await conn.execute(
                "DELETE FROM userland.alerts WHERE id = $1",
                alert_id
            )

        # Parse result like "DELETE 1" to get row count
        deleted_count = int(result.split()[-1]) if result else 0
        return deleted_count > 0

    # ========== Alert Match Operations ==========

    async def create_match(self, match: AlertMatch) -> AlertMatch:
        """Create an alert match record

        Args:
            match: AlertMatch dataclass

        Returns:
            Created match object
        """
        async with self.transaction() as conn:
            await conn.execute(
                """
                INSERT INTO userland.alert_matches
                (id, alert_id, meeting_id, item_id, match_type, confidence,
                 matched_criteria, notified, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
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
        return match

    async def get_matches(
        self,
        alert_id: Optional[str] = None,
        user_id: Optional[str] = None,
        notified: Optional[bool] = None,
        limit: int = 100
    ) -> List[AlertMatch]:
        """Get alert matches with filtering

        Args:
            alert_id: Filter by alert ID
            user_id: Filter by user ID (joins through alerts table)
            notified: Filter by notification status
            limit: Maximum number of results

        Returns:
            List of AlertMatch objects
        """
        query = "SELECT am.* FROM userland.alert_matches am"
        params = []

        # Join with alerts table if filtering by user_id
        if user_id:
            query += " JOIN userland.alerts a ON am.alert_id = a.id WHERE a.user_id = $1"
            params.append(user_id)
        else:
            query += " WHERE 1=1"

        if alert_id:
            params.append(alert_id)
            query += f" AND am.alert_id = ${len(params)}"

        if notified is not None:
            params.append(notified)
            query += f" AND am.notified = ${len(params)}"

        params.append(limit)
        query += f" ORDER BY am.created_at DESC LIMIT ${len(params)}"

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        return [
            AlertMatch(
                id=row["id"],
                alert_id=row["alert_id"],
                meeting_id=row["meeting_id"],
                item_id=row["item_id"],
                match_type=row["match_type"],
                confidence=row["confidence"],
                matched_criteria=row["matched_criteria"],
                notified=row["notified"],
                created_at=row["created_at"]
            )
            for row in rows
        ]

    async def mark_notified(self, match_id: str) -> None:
        """Mark a match as notified (email sent)

        Args:
            match_id: Match identifier
        """
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE userland.alert_matches SET notified = TRUE WHERE id = $1",
                match_id
            )

    async def get_match_count(
        self,
        user_id: Optional[str] = None,
        since_days: Optional[int] = None
    ) -> int:
        """Get count of matches with optional filtering

        Args:
            user_id: Filter by user ID
            since_days: Only count matches from last N days

        Returns:
            Match count
        """
        query = "SELECT COUNT(*) as count FROM userland.alert_matches am"
        params = []

        if user_id:
            query += " JOIN userland.alerts a ON am.alert_id = a.id WHERE a.user_id = $1"
            params.append(user_id)
        else:
            query += " WHERE 1=1"

        if since_days:
            params.append(since_days)
            query += f" AND am.created_at >= NOW() - INTERVAL '{since_days} days'"

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, *params)

        return row["count"]

    # ========== Magic Link Token Operations ==========

    async def is_magic_link_used(self, token_hash: str) -> bool:
        """Check if magic link token has already been used (replay attack prevention)

        Args:
            token_hash: SHA256 hash of the magic link token

        Returns:
            True if token has been used, False otherwise
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT 1 FROM userland.used_magic_links WHERE token_hash = $1",
                token_hash
            )
        return row is not None

    async def mark_magic_link_used(
        self,
        token_hash: str,
        user_id: str,
        expires_at: datetime
    ) -> None:
        """Mark magic link token as used (single-use enforcement)

        Args:
            token_hash: SHA256 hash of the token
            user_id: User who used the token
            expires_at: Token expiry timestamp
        """
        async with self.transaction() as conn:
            await conn.execute(
                """
                INSERT INTO userland.used_magic_links (token_hash, user_id, expires_at)
                VALUES ($1, $2, $3)
                """,
                token_hash,
                user_id,
                expires_at
            )

    async def cleanup_expired_magic_links(self) -> int:
        """Remove expired magic link tokens (cleanup maintenance)

        Returns:
            Number of tokens deleted
        """
        async with self.transaction() as conn:
            result = await conn.execute(
                "DELETE FROM userland.used_magic_links WHERE expires_at < NOW()"
            )

        # Parse "DELETE N" result
        deleted_count = int(result.split()[-1]) if result else 0
        return deleted_count
