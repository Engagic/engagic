"""Rate limit handling for API requests"""

import time
import random
import sqlite3
from pathlib import Path
from typing import Optional, Callable, Any, Dict, Tuple
from functools import wraps
from enum import Enum

from config import get_logger

logger = get_logger(__name__).bind(component="api")



class RateLimitTier(str, Enum):
    """Rate limit tiers for different user types"""
    BASIC = "basic"
    HACKTIVIST = "hacktivist"
    ENTERPRISE = "enterprise"


class TierLimits:
    """Rate limit configuration for each tier"""
    BASIC = {
        "minute_limit": 30,
        "day_limit": 300,
        "description": "Free tier - reasonable personal use"
    }
    HACKTIVIST = {
        "minute_limit": 100,
        "day_limit": 5000,
        "description": "Nonprofit/journalist tier - requires attribution"
    }
    ENTERPRISE = {
        "minute_limit": 1000,
        "day_limit": 100000,
        "description": "Commercial tier - paid access"
    }

    @classmethod
    def get_limits(cls, tier: RateLimitTier) -> Dict[str, Any]:
        """Get limits for a tier"""
        tier_map = {
            RateLimitTier.BASIC: cls.BASIC,
            RateLimitTier.HACKTIVIST: cls.HACKTIVIST,
            RateLimitTier.ENTERPRISE: cls.ENTERPRISE,
        }
        return tier_map.get(tier, cls.BASIC)


class SQLiteRateLimiter:
    """
    Persistent rate limiter using SQLite with tier support.

    Survives restarts and works across multiple API instances.
    Stores request timestamps in database for accurate rate limiting.
    Supports per-minute and per-day limits across multiple tiers.
    """

    def __init__(
        self, db_path: str, requests_limit: int = 30, window_seconds: int = 60
    ):
        """
        Initialize SQLite rate limiter.

        Args:
            db_path: Path to SQLite database file
            requests_limit: Maximum requests allowed in window (backward compat)
            window_seconds: Time window in seconds (backward compat)
        """
        self.db_path = db_path
        self.requests_limit = requests_limit
        self.window_seconds = window_seconds

        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

        # Cleanup tracker - avoid running cleanup on every request
        self._last_cleanup = time.time()
        self._cleanup_interval = 300  # Run cleanup every 5 minutes

    def _init_db(self):
        """Initialize rate limiting tables"""
        with sqlite3.connect(self.db_path) as conn:
            # Per-minute tracking
            conn.execute("""
                CREATE TABLE IF NOT EXISTS rate_limits (
                    client_ip TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    PRIMARY KEY (client_ip, timestamp)
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_rate_limits_ip ON rate_limits(client_ip)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_rate_limits_time ON rate_limits(timestamp)"
            )

            # Per-day tracking
            conn.execute("""
                CREATE TABLE IF NOT EXISTS daily_rate_limits (
                    client_ip TEXT NOT NULL,
                    date TEXT NOT NULL,
                    request_count INTEGER DEFAULT 0,
                    tier TEXT DEFAULT 'basic',
                    PRIMARY KEY (client_ip, date)
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_daily_rate_limits_ip ON daily_rate_limits(client_ip)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_daily_rate_limits_date ON daily_rate_limits(date)"
            )

            # API keys (for future use)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    api_key TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL,
                    tier TEXT NOT NULL DEFAULT 'basic',
                    created_at REAL NOT NULL,
                    email TEXT,
                    organization TEXT,
                    notes TEXT,
                    is_active INTEGER DEFAULT 1
                )
            """)

            conn.commit()
            logger.info(f"Initialized persistent rate limiter at {self.db_path}")

    def get_client_tier(self, client_ip: str, api_key: Optional[str] = None) -> RateLimitTier:
        """
        Get tier for client (API key lookup or default to basic).

        Args:
            client_ip: Client IP address
            api_key: Optional API key

        Returns:
            RateLimitTier enum
        """
        if api_key:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT tier FROM api_keys WHERE api_key = ? AND is_active = 1",
                    (api_key,)
                )
                result = cursor.fetchone()
                if result:
                    return RateLimitTier(result[0])

        # Default to basic tier for unauthenticated requests
        return RateLimitTier.BASIC

    def check_daily_limit(self, client_ip: str, tier: RateLimitTier) -> Tuple[bool, int]:
        """
        Check if client has exceeded daily limit.

        Args:
            client_ip: Client IP address
            tier: Rate limit tier

        Returns:
            (is_allowed, remaining_requests)
        """
        from datetime import datetime
        today = datetime.utcnow().strftime("%Y-%m-%d")
        limits = TierLimits.get_limits(tier)
        day_limit = limits["day_limit"]

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")

            # Get or create daily counter
            cursor = conn.execute(
                "SELECT request_count FROM daily_rate_limits WHERE client_ip = ? AND date = ?",
                (client_ip, today)
            )
            result = cursor.fetchone()

            if result:
                current_count = result[0]
                if current_count >= day_limit:
                    return False, 0

                # Increment counter
                conn.execute(
                    "UPDATE daily_rate_limits SET request_count = request_count + 1 WHERE client_ip = ? AND date = ?",
                    (client_ip, today)
                )
            else:
                # Create new daily counter
                current_count = 0
                conn.execute(
                    "INSERT INTO daily_rate_limits (client_ip, date, request_count, tier) VALUES (?, ?, 1, ?)",
                    (client_ip, today, tier.value)
                )

            conn.commit()
            remaining = day_limit - current_count - 1
            return True, max(0, remaining)

    def check_rate_limit(self, client_ip: str, api_key: Optional[str] = None) -> Tuple[bool, int, Dict[str, Any]]:
        """
        Check if client has exceeded rate limits (both minute and day).

        Args:
            client_ip: Client IP address
            api_key: Optional API key for tier lookup

        Returns:
            (is_allowed, remaining_minute, limit_info)
        """
        current_time = time.time()
        window_start = current_time - self.window_seconds

        # Get client tier
        tier = self.get_client_tier(client_ip, api_key)
        limits = TierLimits.get_limits(tier)
        minute_limit = limits["minute_limit"]

        # Periodic cleanup to prevent database bloat
        if current_time - self._last_cleanup > self._cleanup_interval:
            self._cleanup_old_entries(window_start)
            self._last_cleanup = current_time

        with sqlite3.connect(self.db_path) as conn:
            # Enable WAL mode for better concurrency
            conn.execute("PRAGMA journal_mode=WAL")

            # Count requests in current window
            cursor = conn.execute(
                "SELECT COUNT(*) FROM rate_limits WHERE client_ip = ? AND timestamp > ?",
                (client_ip, window_start),
            )
            request_count = cursor.fetchone()[0]

            # Check minute limit
            if request_count >= minute_limit:
                return False, 0, {
                    "tier": tier.value,
                    "limit_type": "minute",
                    "minute_limit": minute_limit,
                    "day_limit": limits["day_limit"]
                }

            # Check daily limit
            is_allowed_daily, remaining_daily = self.check_daily_limit(client_ip, tier)
            if not is_allowed_daily:
                return False, 0, {
                    "tier": tier.value,
                    "limit_type": "daily",
                    "minute_limit": minute_limit,
                    "day_limit": limits["day_limit"]
                }

            # Add current request to minute tracker
            try:
                conn.execute(
                    "INSERT INTO rate_limits (client_ip, timestamp) VALUES (?, ?)",
                    (client_ip, current_time),
                )
                conn.commit()
            except sqlite3.IntegrityError:
                # Duplicate timestamp for same IP (extremely rare)
                pass

            remaining_minute = minute_limit - request_count - 1
            return True, max(0, remaining_minute), {
                "tier": tier.value,
                "remaining_minute": remaining_minute,
                "remaining_daily": remaining_daily,
                "minute_limit": minute_limit,
                "day_limit": limits["day_limit"]
            }

    def _cleanup_old_entries(self, cutoff_time: float):
        """Remove entries older than cutoff time"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "DELETE FROM rate_limits WHERE timestamp < ?", (cutoff_time,)
                )
                deleted = conn.total_changes
                conn.commit()
                if deleted > 0:
                    logger.debug(f"Cleaned up {deleted} old rate limit entries")
        except Exception as e:
            logger.error(f"Failed to cleanup rate limit entries: {e}")

    def reset_client(self, client_ip: str):
        """Reset rate limit for specific client"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM rate_limits WHERE client_ip = ?", (client_ip,))
            conn.commit()
            logger.info(f"Reset rate limit for {client_ip}")

    def get_client_status(self, client_ip: str) -> Dict[str, Any]:
        """Get current rate limit status for a client"""
        current_time = time.time()
        window_start = current_time - self.window_seconds

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM rate_limits WHERE client_ip = ? AND timestamp > ?",
                (client_ip, window_start),
            )
            request_count = cursor.fetchone()[0]

            return {
                "requests_made": request_count,
                "requests_limit": self.requests_limit,
                "remaining": max(0, self.requests_limit - request_count),
                "window_seconds": self.window_seconds,
                "reset_time": current_time + self.window_seconds,
            }


class RateLimitHandler:
    """Handle rate limits with exponential backoff and jitter"""

    def __init__(
        self,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        max_retries: int = 5,
        backoff_factor: float = 2.0,
    ):
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.consecutive_rate_limits = 0
        self.last_rate_limit_time = 0

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay with exponential backoff and jitter"""
        # Exponential backoff
        delay = min(self.initial_delay * (self.backoff_factor**attempt), self.max_delay)

        # Add jitter (±25%)
        jitter = delay * 0.25 * (2 * random.random() - 1)
        return max(0.1, delay + jitter)

    def should_retry(self, error: Exception) -> bool:
        """Check if error is retryable"""
        error_str = str(error).lower()

        # Rate limit errors
        if any(
            x in error_str
            for x in ["529", "overloaded", "rate limit", "too many requests"]
        ):
            return True

        # Temporary errors
        if any(x in error_str for x in ["timeout", "connection", "temporary"]):
            return True

        return False

    def handle_rate_limit(self):
        """Track consecutive rate limits"""
        current_time = time.time()

        # Reset counter if it's been more than 5 minutes since last rate limit
        if current_time - self.last_rate_limit_time > 300:
            self.consecutive_rate_limits = 0

        self.consecutive_rate_limits += 1
        self.last_rate_limit_time = current_time

        # If we've hit many rate limits, add extra delay
        if self.consecutive_rate_limits > 3:
            extra_delay = min(300, self.consecutive_rate_limits * 10)  # Max 5 minutes
            logger.warning(
                f"Multiple rate limits detected ({self.consecutive_rate_limits}), adding {extra_delay}s extra delay"
            )
            time.sleep(extra_delay)

        # Emergency brake - if too many consecutive rate limits, pause longer
        if self.consecutive_rate_limits > 20:
            pause_time = 600  # 10 minutes
            logger.error(
                f"SEVERE RATE LIMITING: {self.consecutive_rate_limits} consecutive failures. Pausing {pause_time}s"
            )
            time.sleep(pause_time)
            self.consecutive_rate_limits = 10  # Reset to lower number after pause

    def reset_success(self):
        """Reset rate limit counter on successful request"""
        self.consecutive_rate_limits = 0


def with_rate_limit_retry(handler: Optional[RateLimitHandler] = None):
    """Decorator for functions that need rate limit handling"""
    if handler is None:
        handler = RateLimitHandler()

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_error = None

            for attempt in range(handler.max_retries):
                try:
                    result = func(*args, **kwargs)
                    handler.reset_success()
                    return result

                except Exception as e:
                    last_error = e

                    if not handler.should_retry(e):
                        logger.error(f"Non-retryable error in {func.__name__}: {e}")
                        raise

                    if "529" in str(e) or "overloaded" in str(e).lower():
                        handler.handle_rate_limit()

                    if attempt < handler.max_retries - 1:
                        delay = handler.calculate_delay(attempt)
                        logger.warning(
                            f"Rate limit hit in {func.__name__}, attempt {attempt + 1}/{handler.max_retries}, "
                            f"retrying in {delay:.1f}s: {e}"
                        )
                        time.sleep(delay)
                    else:
                        logger.error(
                            f"Max retries ({handler.max_retries}) exceeded in {func.__name__}"
                        )

            if last_error is not None:
                raise last_error
            else:
                raise RuntimeError(
                    f"Max retries exceeded in {func.__name__} with no error recorded"
                )

        return wrapper

    return decorator


class APIRateLimitManager:
    """Manage rate limits across multiple API endpoints"""

    def __init__(self):
        self.handlers: Dict[str, RateLimitHandler] = {}
        self.global_pause_until = 0

    def get_handler(self, endpoint: str) -> RateLimitHandler:
        """Get or create handler for endpoint"""
        if endpoint not in self.handlers:
            self.handlers[endpoint] = RateLimitHandler()
        return self.handlers[endpoint]

    def pause_all(self, duration: float):
        """Pause all API calls for a duration"""
        self.global_pause_until = time.time() + duration
        logger.warning(f"Pausing all API calls for {duration}s due to rate limits")

    def can_proceed(self) -> bool:
        """Check if we can make API calls"""
        if time.time() < self.global_pause_until:
            remaining = self.global_pause_until - time.time()
            logger.info(f"API calls paused for {remaining:.1f}s more")
            return False
        return True

    def wait_if_needed(self):
        """Wait if global pause is active"""
        if time.time() < self.global_pause_until:
            remaining = self.global_pause_until - time.time()
            logger.info(f"Waiting {remaining:.1f}s for rate limit pause to end")
            time.sleep(remaining)
