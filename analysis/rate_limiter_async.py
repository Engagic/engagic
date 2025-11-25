import asyncio
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Dict

from config import get_logger

logger = get_logger(__name__).bind(component="analysis")


@dataclass
class TokenBucket:
    """Token bucket for rate limiting with refill"""
    capacity: int
    tokens: float
    last_refill: float
    refill_rate: float  # tokens per second

    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity
        self.tokens = float(capacity)
        self.last_refill = time.time()
        self.refill_rate = refill_rate

    def refill(self) -> None:
        """Refill tokens based on time elapsed"""
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

    def has_tokens(self, tokens: int) -> bool:
        """Check if bucket has enough tokens"""
        self.refill()
        return self.tokens >= tokens

    def consume(self, tokens: int) -> None:
        """Consume tokens from bucket"""
        self.refill()
        self.tokens -= tokens

    def time_until_available(self, tokens: int) -> float:
        """Calculate time until tokens available (seconds)"""
        self.refill()
        if self.tokens >= tokens:
            return 0.0
        needed = tokens - self.tokens
        return needed / self.refill_rate


class AsyncRateLimiter:
    """
    Async rate limiter for Gemini API with token-based throttling.

    Respects three Gemini API limits:
    - Tokens per minute (default: 1,000,000)
    - Tokens per hour (default: 30,000,000)
    - Tokens per day (default: 500,000,000)

    Usage:
        rate_limiter = AsyncRateLimiter()
        async with rate_limiter.acquire(tokens=15000):
            result = await call_gemini_api(...)
    """

    def __init__(
        self,
        tokens_per_minute: int = 1_000_000,
        tokens_per_hour: int = 30_000_000,
        tokens_per_day: int = 500_000_000
    ):
        self.limits: Dict[str, TokenBucket] = {
            "minute": TokenBucket(
                capacity=tokens_per_minute,
                refill_rate=tokens_per_minute / 60.0  # tokens per second
            ),
            "hour": TokenBucket(
                capacity=tokens_per_hour,
                refill_rate=tokens_per_hour / 3600.0
            ),
            "day": TokenBucket(
                capacity=tokens_per_day,
                refill_rate=tokens_per_day / 86400.0
            )
        }
        self._lock = asyncio.Lock()
        self._total_consumed = 0

    @asynccontextmanager
    async def acquire(self, tokens: int):
        """
        Acquire tokens from rate limiter (async, non-blocking).

        Waits asynchronously if rate limits would be exceeded.
        Ensures all time-based limits (minute, hour, day) respected.
        """
        async with self._lock:
            # Check all buckets for availability
            wait_times = []
            for name, bucket in self.limits.items():
                if not bucket.has_tokens(tokens):
                    wait_time = bucket.time_until_available(tokens)
                    wait_times.append((name, wait_time))

            # Wait for longest required time (non-blocking)
            if wait_times:
                max_wait_name, max_wait_time = max(wait_times, key=lambda x: x[1])
                logger.info(
                    "rate_limit_wait",
                    limit=max_wait_name,
                    wait_seconds=round(max_wait_time, 2),
                    tokens_requested=tokens
                )
                await asyncio.sleep(max_wait_time)

            # Consume tokens from all buckets
            for bucket in self.limits.values():
                bucket.consume(tokens)

            self._total_consumed += tokens

        yield

    def get_stats(self) -> Dict[str, Any]:
        """Get current rate limiter statistics"""
        return {
            "total_consumed": self._total_consumed,
            "minute": {
                "capacity": self.limits["minute"].capacity,
                "available": int(self.limits["minute"].tokens),
                "used_pct": round((1 - self.limits["minute"].tokens / self.limits["minute"].capacity) * 100, 1)
            },
            "hour": {
                "capacity": self.limits["hour"].capacity,
                "available": int(self.limits["hour"].tokens),
                "used_pct": round((1 - self.limits["hour"].tokens / self.limits["hour"].capacity) * 100, 1)
            },
            "day": {
                "capacity": self.limits["day"].capacity,
                "available": int(self.limits["day"].tokens),
                "used_pct": round((1 - self.limits["day"].tokens / self.limits["day"].capacity) * 100, 1)
            }
        }


def estimate_tokens(text: str) -> int:
    """
    Estimate token count for Gemini API.

    Gemini uses approximately 4 characters per token for English text.
    Add 20% buffer for safety (prompts, JSON structure, thinking, etc.)
    """
    char_count = len(text)
    base_tokens = char_count / 4
    buffered_tokens = int(base_tokens * 1.2)
    return max(buffered_tokens, 100)  # Minimum 100 tokens for overhead
