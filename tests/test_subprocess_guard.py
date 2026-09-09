"""Guard contract tests: ok/task-error/timeout/crash/rlimit through real children.

Targets are module-level so the forkserver child can import them by
reference. These spawn real subprocesses -- each test costs ~100-300ms.
"""

import os
import subprocess
import sys
import time

import pytest

from parsing import subprocess_guard
from parsing.subprocess_guard import (
    GuardCrashed,
    GuardTaskError,
    GuardTimeout,
    run_guarded,
)

# Not every platform accepts a finite RLIMIT_AS (macOS rejects it with
# EINVAL); where it can't be set the guard deliberately runs uncapped, so
# the containment test below proves nothing there. Probed in a subprocess
# so the test runner itself never gets capped.
_RLIMIT_AS_SETTABLE = (
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import resource; resource.setrlimit(resource.RLIMIT_AS, (1 << 30, 1 << 30))",
        ],
        capture_output=True,
    ).returncode
    == 0
)


def target_ok(a, b, scale=1):
    return {"sum": (a + b) * scale}


def target_big_result(n):
    # Larger than the 64KB pipe buffer: proves the drain-before-join order.
    return "x" * n


def target_raises():
    raise ValueError("boom from child")


def target_sleeps(seconds):
    time.sleep(seconds)
    return "never"


def target_exits():
    os._exit(7)


def target_allocates(n_bytes):
    block = bytearray(n_bytes)
    return len(block)


def test_ok_roundtrip_with_kwargs():
    assert run_guarded(target_ok, (2, 3), {"scale": 10}, timeout=30) == {"sum": 50}


def test_result_bigger_than_pipe_buffer():
    assert len(run_guarded(target_big_result, (1_000_000,), timeout=60)) == 1_000_000


def test_child_exception_surfaces_with_type():
    with pytest.raises(GuardTaskError) as exc:
        run_guarded(target_raises, timeout=30)
    assert "boom from child" in str(exc.value)
    assert exc.value.error_type == "ValueError"


def test_timeout_kills_child():
    start = time.monotonic()
    with pytest.raises(GuardTimeout):
        run_guarded(target_sleeps, (30,), timeout=2)
    assert time.monotonic() - start < 20  # killed, not waited out


def test_silent_death_is_crash():
    with pytest.raises(GuardCrashed) as exc:
        run_guarded(target_exits, timeout=30)
    assert exc.value.exitcode == 7


@pytest.mark.skipif(
    not _RLIMIT_AS_SETTABLE, reason="platform cannot set a finite RLIMIT_AS"
)
def test_rlimit_contains_allocation():
    # 512MB cap, 1GB allocation: the child dies with MemoryError inside the
    # worker (reported as GuardTaskError) or is killed outright (GuardCrashed).
    # Either way the parent survives and gets a typed failure.
    with pytest.raises((GuardTaskError, GuardCrashed)):
        run_guarded(
            target_allocates,
            (1024 * 1024 * 1024,),
            timeout=60,
            rlimit_bytes=512 * 1024 * 1024,
        )


def test_unexpected_exception_in_result_wait_reaps_child(monkeypatch):
    # A KeyboardInterrupt (or any raise) out of the parent's result wait
    # must not orphan a live child holding the address-space cap.
    real_ctx = subprocess_guard._forkserver_ctx
    spawned = {}

    class InterruptingCtx:
        def Queue(self):
            q = real_ctx.Queue()

            def interrupted_get(*args, **kwargs):
                raise KeyboardInterrupt

            q.get = interrupted_get
            return q

        def Process(self, *args, **kwargs):
            proc = real_ctx.Process(*args, **kwargs)
            spawned["proc"] = proc
            return proc

    monkeypatch.setattr(subprocess_guard, "_forkserver_ctx", InterruptingCtx())

    with pytest.raises(KeyboardInterrupt):
        run_guarded(target_sleeps, (30,), timeout=30)

    proc = spawned["proc"]
    assert not proc.is_alive()
    assert proc.exitcode is not None  # joined (reaped), not merely signaled


def test_start_failure_is_not_masked(monkeypatch):
    # A Process whose start() raised was never alive; cleanup must let the
    # original error out instead of raising over it.
    real_ctx = subprocess_guard._forkserver_ctx

    class FailingStartCtx:
        def Queue(self):
            return real_ctx.Queue()

        def Process(self, *args, **kwargs):
            proc = real_ctx.Process(*args, **kwargs)

            def failing_start():
                raise OSError("forkserver refused")

            proc.start = failing_start
            return proc

    monkeypatch.setattr(subprocess_guard, "_forkserver_ctx", FailingStartCtx())

    with pytest.raises(OSError, match="forkserver refused"):
        run_guarded(target_ok, (1, 2), timeout=10)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))


def target_signals_then_sleeps(path):
    from pathlib import Path
    Path(path).touch()
    time.sleep(30)


def test_no_child_starts_after_admission_deadline(monkeypatch):
    from parsing import memory_budget

    monkeypatch.setattr(memory_budget, 'available_bytes', lambda: 0)

    class NoSpawnContext:
        def Queue(self):
            pytest.fail('must not allocate a process queue without admission')

    monkeypatch.setattr(subprocess_guard, '_forkserver_ctx', NoSpawnContext())
    with pytest.raises(GuardTimeout, match='memory capacity'):
        run_guarded(target_ok, (1, 2), timeout=0.03)
    assert memory_budget._reserved_bytes == 0


def test_admission_time_is_part_of_execution_deadline(monkeypatch):
    from contextlib import contextmanager

    now = [100.0]

    @contextmanager
    def slow_admission(*args, **kwargs):
        now[0] += 8
        yield

    class NoSpawnContext:
        def Queue(self):
            pytest.fail('admission consumed the deadline, so no child may start')

    monkeypatch.setattr(subprocess_guard, 'reserve_memory', slow_admission)
    monkeypatch.setattr(subprocess_guard.time, 'monotonic', lambda: now[0])
    monkeypatch.setattr(subprocess_guard, '_forkserver_ctx', NoSpawnContext())
    with pytest.raises(GuardTimeout, match='deadline'):
        run_guarded(target_ok, (1, 2), timeout=5)


def test_async_cancellation_reaps_child_and_returns_capacity(tmp_path, monkeypatch):
    import asyncio
    from parsing import memory_budget

    real_ctx = subprocess_guard._forkserver_ctx
    children = []

    class RecordingContext:
        def Queue(self):
            return real_ctx.Queue()

        def Process(self, **kwargs):
            proc = real_ctx.Process(**kwargs)
            children.append(proc)
            return proc

    monkeypatch.setattr(subprocess_guard, '_forkserver_ctx', RecordingContext())
    ready = tmp_path / 'child-ready'

    async def check():
        task = asyncio.create_task(subprocess_guard.run_guarded_thread(
            run_guarded, target_signals_then_sleeps, (str(ready),), timeout=20,
        ))
        try:
            async with asyncio.timeout(10):
                while not ready.exists():
                    await asyncio.sleep(0.01)
            assert memory_budget._reserved_bytes > 0
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert not children[0].is_alive()
        assert children[0].exitcode is not None
        assert memory_budget._reserved_bytes == 0

    asyncio.run(check())


def test_async_cancellation_during_admission_never_spawns(monkeypatch):
    import asyncio
    from parsing import memory_budget

    monkeypatch.setattr(memory_budget, 'available_bytes', lambda: 0)

    class NoSpawnContext:
        def Queue(self):
            pytest.fail('cancelled admission must not start a child')

    monkeypatch.setattr(subprocess_guard, '_forkserver_ctx', NoSpawnContext())

    async def check():
        task = asyncio.create_task(subprocess_guard.run_guarded_thread(
            run_guarded, target_ok, (1, 2), timeout=20,
        ))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert memory_budget._reserved_bytes == 0
        assert not memory_budget._waiters

    asyncio.run(check())
