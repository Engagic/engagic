"""Admission control by available memory, not by count.

Per-unit caps (one subprocess at 1.5 GB, one download at a time per slot)
are individually safe and collectively unbounded: eight capped children on a
3.8 GB box can claim 12 GB. This module gates the expensive steps on what the
kernel says is actually available, so pressure serializes work instead of
failing it. Imports stay cheap on purpose: the subprocess guard uses this in
the parent before every spawn.
"""

import asyncio
import time
from typing import Optional

from config import config, get_logger

logger = get_logger(__name__).bind(component="memory_budget")

_MEMINFO = "/proc/meminfo"
_POLL_SECONDS = 0.5


def available_bytes() -> Optional[int]:
    """MemAvailable from the kernel, or None where /proc is unavailable."""
    try:
        with open(_MEMINFO) as handle:
            for line in handle:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def _log_wait(min_available: int, waited: float, available: Optional[int], granted: bool) -> None:
    logger.warning(
        "memory admission gate",
        granted=granted,
        waited_seconds=round(waited, 1),
        available_mb=None if available is None else available // (1024 * 1024),
        required_mb=min_available // (1024 * 1024),
    )


def wait_for_memory(
    min_available: Optional[int] = None,
    max_wait_seconds: Optional[float] = None,
) -> bool:
    """Block until MemAvailable >= min_available, or until max_wait elapses.

    Returns True when admitted with headroom, False when the wait expired and
    the caller proceeds anyway (starving forever would be worse than one
    risky spawn; the per-unit cap still applies).
    """
    min_available = min_available if min_available is not None else config.EXTRACTION_MIN_AVAILABLE_BYTES
    max_wait = max_wait_seconds if max_wait_seconds is not None else config.EXTRACTION_MEMORY_WAIT_SECONDS
    started = time.monotonic()
    while True:
        available = available_bytes()
        if available is None or available >= min_available:
            waited = time.monotonic() - started
            if waited >= _POLL_SECONDS:
                _log_wait(min_available, waited, available, True)
            return True
        if time.monotonic() - started >= max_wait:
            _log_wait(min_available, time.monotonic() - started, available, False)
            return False
        time.sleep(_POLL_SECONDS)


async def wait_for_memory_async(
    min_available: Optional[int] = None,
    max_wait_seconds: Optional[float] = None,
) -> bool:
    """Event-loop-friendly twin of wait_for_memory."""
    min_available = min_available if min_available is not None else config.EXTRACTION_MIN_AVAILABLE_BYTES
    max_wait = max_wait_seconds if max_wait_seconds is not None else config.EXTRACTION_MEMORY_WAIT_SECONDS
    started = time.monotonic()
    while True:
        available = available_bytes()
        if available is None or available >= min_available:
            waited = time.monotonic() - started
            if waited >= _POLL_SECONDS:
                _log_wait(min_available, waited, available, True)
            return True
        if time.monotonic() - started >= max_wait:
            _log_wait(min_available, time.monotonic() - started, available, False)
            return False
        await asyncio.sleep(_POLL_SECONDS)
