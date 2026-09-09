"""Process-wide reservations shared by download tasks and extraction threads.

The fixed budget bounds admitted work even before allocations become visible
to the kernel. MemAvailable supplies an additional, conservative pressure
check; it never replaces accounting for outstanding reservations.
"""

import asyncio
from collections import deque
import threading
import time
from typing import Optional

from config import config

_MEMINFO = "/proc/meminfo"
_POLL_SECONDS = 0.1
_lock = threading.Lock()
_reserved_bytes = 0
_waiters: deque[object] = deque()


class MemoryAdmissionTimeout(TimeoutError):
    """No capacity became available; the expensive operation must not start."""


class MemoryAdmissionCancelled(Exception):
    """The owning async task cancelled while its thread was waiting."""


def available_bytes() -> Optional[int]:
    """MemAvailable from the kernel, or None where /proc is unavailable."""
    try:
        with open(_MEMINFO) as handle:
            for line in handle:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


class MemoryReservation:
    """Capacity held until the operation (or its retained bytes) is released."""

    def __init__(self, size: int):
        self.size = size

    def release(self) -> None:
        global _reserved_bytes
        with _lock:
            _reserved_bytes -= self.size
            self.size = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.release()

    def __del__(self):
        self.release()


class ReservedBytes(bytes):
    """Keep a download's reservation while any consumer retains its bytes.

    Copying into this bytes subclass temporarily doubles the buffer; download
    reservations account for that copy. Existing bytes consumers work
    unchanged, including the compatibility byte-download API.
    """

    reservation: MemoryReservation

    def __new__(cls, data: bytes, reservation: MemoryReservation):
        value = super().__new__(cls, data)
        value.reservation = reservation
        return value


def _enqueue(size: int) -> object:
    if size <= 0:
        raise ValueError("Memory reservation must be positive")
    if size > config.WORK_MEMORY_BUDGET_BYTES:
        raise MemoryAdmissionTimeout("Operation exceeds the shared memory budget")
    ticket = object()
    with _lock:
        _waiters.append(ticket)
    return ticket


def _leave_queue(ticket: object) -> None:
    with _lock:
        if ticket in _waiters:
            _waiters.remove(ticket)


def _try_reserve(size: int, ticket: object) -> Optional[MemoryReservation]:
    global _reserved_bytes
    with _lock:
        # FIFO prevents a stream of small downloads starving an extraction.
        if _waiters[0] is not ticket:
            return None
        available = available_bytes()
        required = _reserved_bytes + size
        if required > config.WORK_MEMORY_BUDGET_BYTES:
            return None
        if available is not None and available < required + config.EXTRACTION_MIN_AVAILABLE_BYTES:
            return None
        reservation = MemoryReservation(size)
        _reserved_bytes += size
        _waiters.popleft()
        return reservation


def reserve_memory(
    size: int,
    *,
    deadline: Optional[float] = None,
    cancel_event: Optional[threading.Event] = None,
) -> MemoryReservation:
    """Reserve atomically, or fail closed at the admission/operation deadline."""
    admission_deadline = time.monotonic() + config.EXTRACTION_MEMORY_WAIT_SECONDS
    if deadline is not None:
        admission_deadline = min(deadline, admission_deadline)
    ticket = _enqueue(size)
    try:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                raise MemoryAdmissionCancelled("Memory admission cancelled")
            if time.monotonic() >= admission_deadline:
                raise MemoryAdmissionTimeout("Timed out waiting for shared memory capacity")
            reservation = _try_reserve(size, ticket)
            if reservation is not None:
                return reservation
            delay = min(_POLL_SECONDS, max(0, admission_deadline - time.monotonic()))
            if cancel_event is not None:
                cancel_event.wait(delay)
            else:
                time.sleep(delay)
    finally:
        _leave_queue(ticket)


async def reserve_memory_async(size: int) -> MemoryReservation:
    """Use the same accounting without occupying an executor thread."""
    deadline = time.monotonic() + config.EXTRACTION_MEMORY_WAIT_SECONDS
    ticket = _enqueue(size)
    try:
        while True:
            if time.monotonic() >= deadline:
                raise MemoryAdmissionTimeout("Timed out waiting for shared memory capacity")
            reservation = _try_reserve(size, ticket)
            if reservation is not None:
                return reservation
            await asyncio.sleep(min(_POLL_SECONDS, max(0, deadline - time.monotonic())))
    finally:
        _leave_queue(ticket)
