"""Async vendor-aware rate limiter to be respectful to city websites"""

import asyncio
import time
import random
from collections import defaultdict
from typing import Dict, List, Optional

from config import get_logger

logger = get_logger(__name__).bind(component="vendor")


# Per-vendor minimum interval between requests on a single slot.
DELAYS: Dict[str, float] = {
    "primegov": 2.7,
    "granicus": 3.6,
    "civicclerk": 2.7,
    "legistar": 2.7,
    "civicplus": 7.2,  # aggressive blocking, longer per-slot delay
    "civicengage": 4.5,
    "novusagenda": 3.6,
    "iqm2": 2.7,
    "escribe": 2.7,
    "municode": 2.7,
    "onbase": 2.7,
    "civicweb": 2.7,
    "visioninternet": 2.7,
    "agendaonline": 2.7,
    "proudcity": 2.7,
    "wp_events": 2.7,
    "berkeley": 2.7,
    "menlopark": 2.7,
    "chicago": 2.7,
    "ross": 2.7,
    "destiny": 2.7,
    "boardbook": 1.5,  # Sparq BoardBook -- SaaS serving hundreds of districts
    "unknown": 4.5,
}

# Per-vendor concurrent slots. Each slot is paced independently at DELAYS[vendor],
# so aggregate throughput is approximately SLOTS / DELAYS req/sec.
#
# Default is 1 (strict serialization, the historical behavior). Bump up for
# multi-tenant SaaS vendors where many cities live behind one domain and the
# vendor is sized for high concurrent traffic from real district staff. Keep
# at 1 for vendors that have shown signs of aggressive bot blocking.
SLOTS: Dict[str, int] = {
    "boardbook": 3,   # Sparq SaaS, ~hundreds of districts -- 2 req/sec aggregate
    "legistar": 2,    # Many cities on legistar.com subdomains
    "granicus": 2,    # Many cities on granicus.com subdomains
    "primegov": 2,    # Multi-tenant SaaS
    "civicclerk": 2,  # Multi-tenant SaaS
    # Everyone else stays at 1 (default below)
}


class AsyncRateLimiter:
    """Multi-slot async rate limiter.

    Each vendor gets a pool of slots; each slot enforces its own per-request
    minimum interval. A request reserves the earliest-available slot, computes
    when it can fire, and sleeps outside the lock so other coroutines can
    reserve their own slots in parallel.

    For SLOTS[vendor]=N and DELAYS[vendor]=D, sustained throughput is roughly
    N/D requests per second; bursts of N requests can land back-to-back.
    """

    def __init__(self):
        self._slot_times: Dict[str, List[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def wait_if_needed(self, vendor: str):
        min_delay = DELAYS.get(vendor, DELAYS["unknown"])
        n_slots = SLOTS.get(vendor, 1)
        jitter = random.uniform(0, 2) if vendor == "civicplus" else random.uniform(0, 1)

        # Reserve a slot inside the lock; sleep outside so concurrent callers
        # can serialize their reservations without serializing their waits.
        async with self._lock:
            now = time.time()
            slots = self._slot_times[vendor]
            while len(slots) < n_slots:
                slots.append(0.0)

            earliest_idx = min(range(n_slots), key=lambda i: slots[i])
            earliest_time = slots[earliest_idx]

            fire_at = max(now, earliest_time + min_delay) + jitter
            slots[earliest_idx] = fire_at
            sleep_time = fire_at - now

        if sleep_time > 0.05:
            logger.info(
                "vendor rate limit",
                vendor=vendor,
                sleep_seconds=round(sleep_time, 1),
                slots=n_slots,
            )
            await asyncio.sleep(sleep_time)

    async def respect_retry_after(self, vendor: str, seconds: float):
        """Honor a Retry-After header by deferring all of the vendor's slots.

        Caps the deferral so a misbehaving server can't park the sync forever.
        """
        seconds = max(0.0, min(seconds, 120.0))
        async with self._lock:
            n_slots = SLOTS.get(vendor, 1)
            slots = self._slot_times[vendor]
            while len(slots) < n_slots:
                slots.append(0.0)
            target = time.time() + seconds
            for i in range(n_slots):
                if slots[i] < target:
                    slots[i] = target
        logger.info("honoring retry-after", vendor=vendor, defer_seconds=round(seconds, 1))


# Process-wide singleton: every adapter and the fetcher share one limiter so
# per-request gating, per-city gating, and Retry-After deferrals all serialize
# against the same per-vendor slot tracking.
_GLOBAL_RATE_LIMITER: Optional[AsyncRateLimiter] = None


def get_rate_limiter() -> AsyncRateLimiter:
    global _GLOBAL_RATE_LIMITER
    if _GLOBAL_RATE_LIMITER is None:
        _GLOBAL_RATE_LIMITER = AsyncRateLimiter()
    return _GLOBAL_RATE_LIMITER
