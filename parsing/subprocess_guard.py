"""Subprocess guard for crash-prone, memory-hungry CPU work.

PyMuPDF is a C extension that can segfault on malformed PDFs, and parse/OCR
work on pathological documents can eat unbounded RAM or wedge forever (the
2026-06-29 sync freeze: one unguarded get_text pinned the whole pipeline for
15 minutes -- max_ms=902907 is still visible in the chunk audit telemetry).
Work like that must run where a crash, an OOM, or a hang is contained: an
isolated child process with a hard address-space cap and a kill-on-timeout
parent.

This module is the single implementation of that containment -- the collapse
chokepoint from docs/CORPUS_ARCHITECTURE.md. It was extracted from
analyzer_async's _extract_pdf_in_subprocess, previously the only guarded
site while the sync chunker ran naked in the event loop's thread pool (see
docs/DEBT_CLASS_RADAR.md item 2, "siloed" flavor). Both extraction
(analysis/analyzer_async.py) and the sync chunker
(vendors/adapters/base_adapter_async.py) now dispatch through it.

run_guarded() blocks; async callers use run_guarded_thread for cancellation
that reaps the child before releasing the caller's resources.
"""

import asyncio
import multiprocessing
import resource
import threading
import time
from queue import Empty
from typing import Any, Callable, Dict, Optional, Tuple

from config import config
from parsing.memory_budget import (
    MemoryAdmissionCancelled,
    MemoryAdmissionTimeout,
    reserve_memory,
)

# Forkserver over fork: children must not inherit the parent's event loop,
# sockets, or DB pool fds. Over spawn: repeated launches skip re-running the
# interpreter setup. The forkserver process itself starts lazily on first
# Process(); creating the context at import time costs nothing. Each child
# imports the target's module fresh -- keep targets in modules that import
# cheaply (parsing.pdf, the chunker stack), not in modules dragging in HTTP
# clients and LLM SDKs.
_forkserver_ctx = multiprocessing.get_context("forkserver")

# Default address-space cap, inherited from the original extraction guard.
# Each child also holds this much of the shared work budget for its entire
# lifetime. Lighter work (text-layer chunking, metadata inspection) passes a
# tighter cap and consumes less of that same pool.
DEFAULT_RLIMIT_BYTES = int(1.5 * 1024 * 1024 * 1024)

# Give the parent this long to observe a child's exit after its result (or
# kill signal) lands; anything longer means the child is unkillable-wedged.
_JOIN_TIMEOUT_SECONDS = 30


class GuardError(Exception):
    """Base for guard failures. Catch this to handle any guarded outcome."""


class GuardTimeout(GuardError):
    """The child produced no result within the deadline and was killed."""


class GuardCancelled(GuardError):
    """The caller cancelled; admission stopped or the child was reaped."""


class GuardCrashed(GuardError):
    """The child died without reporting (segfault, OOM kill, os._exit)."""

    def __init__(self, message: str, exitcode: Optional[int] = None):
        super().__init__(message)
        self.exitcode = exitcode


class GuardTaskError(GuardError):
    """The target raised inside the child; message and type survive the hop."""

    def __init__(self, message: str, error_type: Optional[str] = None):
        super().__init__(message)
        self.error_type = error_type


def _apply_address_space_cap(rlimit_bytes: int) -> None:
    """Best-effort RLIMIT_AS: requested cap, else the hard limit, else uncapped.

    A raise here happens before the target runs, so a platform that rejects
    the cap must not turn every guarded call into a startup crash. macOS
    refuses any finite RLIMIT_AS (EINVAL, surfaced as ValueError) while
    reporting an infinite hard limit -- there the guard runs uncapped. On
    Linux the requested cap applies exactly as before.
    """
    try:
        resource.setrlimit(resource.RLIMIT_AS, (rlimit_bytes, rlimit_bytes))
        return
    except (ValueError, OSError):
        pass
    _, hard = resource.getrlimit(resource.RLIMIT_AS)
    if hard != resource.RLIM_INFINITY:
        try:
            resource.setrlimit(resource.RLIMIT_AS, (hard, hard))
        except (ValueError, OSError):
            pass


def _guard_worker(
    result_queue,
    rlimit_bytes: int,
    target: Callable[..., Any],
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
) -> None:
    """Child-process entrypoint: cap resources, run target, report once."""
    _apply_address_space_cap(rlimit_bytes)

    # Mark this child as a preferred OOM victim. The conductor parent sets
    # itself to -500; we override to +500 so under system-wide memory
    # pressure the kernel kills the actual memory hog instead of orphaning
    # the coordinator. Raising your own oom_score_adj toward more-killable
    # never requires capabilities.
    try:
        with open("/proc/self/oom_score_adj", "w") as f:
            f.write("500")
    except OSError:
        pass  # Non-Linux or restricted /proc -- worker still functions

    try:
        result_queue.put(("ok", target(*args, **kwargs)))
    except Exception as e:
        result_queue.put(("error", str(e) or type(e).__name__, type(e).__name__))


def run_guarded(
    target: Callable[..., Any],
    args: Tuple[Any, ...] = (),
    kwargs: Optional[Dict[str, Any]] = None,
    *,
    timeout: float = 600.0,
    rlimit_bytes: int = DEFAULT_RLIMIT_BYTES,
    cancel_event: Optional[threading.Event] = None,
    reservation_bytes: Optional[int] = None,
) -> Any:
    """Run target(*args, **kwargs) in a resource-capped subprocess.

    target must be a module-level callable (pickled by reference; the child
    imports its module) and args/kwargs/return value must pickle. Blocks the
    calling thread for up to `timeout` seconds plus bounded child cleanup.
    Admission, process startup and execution share that single deadline.

    Raises GuardTimeout (child killed after the deadline), GuardCrashed
    (child died silently -- segfault, OOM), or GuardTaskError (target raised;
    original message and type attached). Anything else propagates as-is.
    """
    deadline = time.monotonic() + timeout
    # Admission accounts for the child's expected working set; rlimit_bytes
    # stays the hard address-space cap applied inside the child.
    if reservation_bytes is None:
        reservation_bytes = min(config.EXTRACTION_RESERVATION_BYTES, rlimit_bytes)
    try:
        with reserve_memory(reservation_bytes, deadline=deadline, cancel_event=cancel_event):
            return _run_reserved(target, args, kwargs, deadline, rlimit_bytes, cancel_event)
    except MemoryAdmissionTimeout as exc:
        raise GuardTimeout(str(exc)) from exc
    except MemoryAdmissionCancelled as exc:
        raise GuardCancelled(str(exc)) from exc


def _run_reserved(target, args, kwargs, deadline, rlimit_bytes, cancel_event):
    def check_deadline():
        if cancel_event is not None and cancel_event.is_set():
            raise GuardCancelled("Guarded work cancelled")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise GuardTimeout("Guarded work exhausted its admission/execution deadline")
        return remaining

    check_deadline()
    result_queue = _forkserver_ctx.Queue()
    proc = _forkserver_ctx.Process(
        target=_guard_worker,
        args=(result_queue, rlimit_bytes, target, args, kwargs or {}),
    )
    try:
        check_deadline()
        proc.start()

        # Drain the queue BEFORE join: the queue rides a pipe (64KB buffer on
        # Linux), so a result bigger than the buffer blocks the child's put()
        # until the parent reads. A parent blocked on join() at that moment
        # deadlocks both sides until the timeout.
        #
        # Poll in short slices rather than one long get: a child that dies
        # WITHOUT reporting (segfault, OOM kill) never puts anything, and a
        # single blocking get would sit out the full timeout before anyone
        # noticed -- the predecessor of this module did exactly that, turning
        # every segfault into a silent 600s stall.
        target_name = getattr(target, "__name__", repr(target))
        result_msg = None
        while result_msg is None:
            remaining = check_deadline()
            try:
                result_msg = result_queue.get(timeout=min(0.1, remaining))
            except Empty:
                if not proc.is_alive():
                    # Dead child. Its result may still be in flight through
                    # the feeder thread/pipe -- one final grace read before
                    # declaring a silent crash.
                    try:
                        result_msg = result_queue.get(timeout=min(0.1, check_deadline()))
                    except Empty:
                        proc.join(timeout=10)
                        raise GuardCrashed(
                            f"{target_name} subprocess crashed "
                            f"(exit code {proc.exitcode})",
                            exitcode=proc.exitcode,
                        )

        check_deadline()
        proc.join(timeout=min(_JOIN_TIMEOUT_SECONDS, check_deadline()))
        if proc.is_alive():
            proc.kill()
            proc.join(timeout=_JOIN_TIMEOUT_SECONDS)

        if proc.exitcode != 0 and proc.exitcode is not None:
            raise GuardCrashed(
                f"{target_name} subprocess crashed (exit code {proc.exitcode})",
                exitcode=proc.exitcode,
            )

        status, *data = result_msg
        if status == "error":
            raise GuardTaskError(data[0], error_type=data[1])
        return data[0]
    finally:
        # No escape path may orphan the child: a KeyboardInterrupt (or any
        # unexpected raise) out of the result wait above, or a wedged child
        # surviving the timeout path's kill, leaves a live process holding
        # up to rlimit_bytes of address space. is_alive() is False on a
        # Process whose start() itself raised, and kill()/join() would raise
        # on it -- the gate keeps a failed start from masking the original
        # exception.
        if proc.is_alive():
            proc.kill()
            proc.join(timeout=_JOIN_TIMEOUT_SECONDS)
        # Release the Queue's pipe fds, semaphores, and feeder thread now.
        # Without explicit close each run leaks ~4 fds until non-deterministic
        # GC; over thousands of runs in a long process-cities session that
        # was a significant contributor to the 2026-04-10 parent RSS bloat.
        try:
            result_queue.close()
            result_queue.join_thread()
        except Exception:
            pass


async def run_guarded_thread(target: Callable[..., Any], *args, **kwargs) -> Any:
    """Offload a guard-owning function and reap its child before cancellation.

    target must pass cancel_event through to every run_guarded call. Shielding
    keeps asyncio cancellation from discarding the thread's cleanup; callers
    may safely release temporary files and concurrency slots once this exits.
    """
    cancel_event = threading.Event()
    task = asyncio.create_task(
        asyncio.to_thread(target, *args, cancel_event=cancel_event, **kwargs)
    )
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        cancel_event.set()
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not task.cancelled():
            task.exception()  # Retrieve any guard failure during cleanup.
        raise
