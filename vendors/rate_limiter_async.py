"""Async vendor-aware rate limiter to be respectful to city websites"""

import asyncio
import time
import random
from collections import defaultdict
from typing import Optional

from config import get_logger

logger = get_logger(__name__).bind(component="vendor")


class AsyncRateLimiter:
    """Async vendor-aware rate limiter to be respectful to city websites

    Uses asyncio.Lock for async-safe locking and asyncio.sleep for non-blocking delays.
    """

    def __init__(self):
        self.last_request = defaultdict(float)
        self.lock = asyncio.Lock()

    async def wait_if_needed(self, vendor: str):
        """Enforce minimum delay between requests to same vendor (async)"""
        delays = {
            "primegov": 2.7,  # PrimeGov cities
            "granicus": 3.6,  # Granicus/Legistar cities
            "civicclerk": 2.7,  # CivicClerk cities
            "legistar": 2.7,  # Direct Legistar
            "civicplus": 7.2,  # CivicPlus cities - aggressive blocking, need longer delays
            "civicengage": 4.5,  # CivicEngage Archive Center (.gov sites)
            "novusagenda": 3.6,  # NovusAgenda cities
            "iqm2": 2.7,  # IQM2 cities
            "escribe": 2.7,  # eScribe cities
            "municode": 2.7,  # Municode cities
            "onbase": 2.7,  # OnBase cities
            "civicweb": 2.7,  # CivicWeb cities
            "visioninternet": 2.7,  # VisionInternet cities
            "agendaonline": 2.7,  # AgendaOnline cities
            "proudcity": 2.7,  # ProudCity cities
            "wp_events": 2.7,  # WordPress Events cities
            "berkeley": 2.7,  # Custom: Berkeley
            "menlopark": 2.7,  # Custom: Menlo Park
            "chicago": 2.7,  # Custom: Chicago
            "ross": 2.7,  # Custom: Ross
            "destiny": 2.7,  # Destiny/AgendaQuick
            "unknown": 4.5,  # Unknown vendors get longest delay
        }

        min_delay = delays.get(vendor, 5.0)

        # CivicPlus gets extra random jitter to avoid pattern detection
        jitter = random.uniform(0, 2) if vendor == "civicplus" else random.uniform(0, 1)

        async with self.lock:
            now = time.time()
            last = self.last_request[vendor]

            if last > 0:
                elapsed = now - last
                if elapsed < min_delay:
                    sleep_time = min_delay - elapsed + jitter
                    logger.info("vendor rate limit", vendor=vendor, sleep_seconds=round(sleep_time, 1))
                    await asyncio.sleep(sleep_time)

            self.last_request[vendor] = time.time()

    async def respect_retry_after(self, vendor: str, seconds: float):
        """Honor a Retry-After header by deferring the next request to this vendor.

        Caps the deferral so a misbehaving server can't park the sync forever.
        """
        seconds = max(0.0, min(seconds, 120.0))
        async with self.lock:
            self.last_request[vendor] = time.time() + seconds
        logger.info("honoring retry-after", vendor=vendor, defer_seconds=round(seconds, 1))


# Process-wide singleton: every adapter and the fetcher share one limiter so
# per-request gating, per-city gating, and Retry-After deferrals all serialize
# against the same per-vendor delay tracking.
_GLOBAL_RATE_LIMITER: Optional[AsyncRateLimiter] = None


def get_rate_limiter() -> AsyncRateLimiter:
    global _GLOBAL_RATE_LIMITER
    if _GLOBAL_RATE_LIMITER is None:
        _GLOBAL_RATE_LIMITER = AsyncRateLimiter()
    return _GLOBAL_RATE_LIMITER
