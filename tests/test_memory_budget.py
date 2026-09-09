import asyncio
import gc
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from config import config
from parsing import memory_budget
from parsing.memory_budget import MemoryAdmissionTimeout, ReservedBytes, reserve_memory, reserve_memory_async


@pytest.fixture(autouse=True)
def budget(monkeypatch):
    monkeypatch.setattr(config, 'WORK_MEMORY_BUDGET_BYTES', 800)
    monkeypatch.setattr(config, 'EXTRACTION_MIN_AVAILABLE_BYTES', 0)
    monkeypatch.setattr(config, 'EXTRACTION_MEMORY_WAIT_SECONDS', 1)
    monkeypatch.setattr(memory_budget, 'available_bytes', lambda: 800)
    monkeypatch.setattr(memory_budget, '_POLL_SECONDS', 0.005)
    yield
    gc.collect()
    assert memory_budget._reserved_bytes == 0
    assert not memory_budget._waiters


def test_simultaneous_workers_cannot_claim_the_same_capacity():
    barrier = threading.Barrier(8)
    lock = threading.Lock()
    active = peak = 0

    def work(_):
        nonlocal active, peak
        barrier.wait()
        with reserve_memory(700):
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.01)
            with lock:
                active -= 1

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(work, range(8)))
    assert peak == 1


def test_admission_timeout_does_not_grant_capacity(monkeypatch):
    monkeypatch.setattr(memory_budget, 'available_bytes', lambda: 100)
    with pytest.raises(MemoryAdmissionTimeout):
        reserve_memory(700, deadline=time.monotonic() + 0.02)


def test_fixed_budget_still_applies_without_proc(monkeypatch):
    monkeypatch.setattr(memory_budget, 'available_bytes', lambda: None)
    with reserve_memory(700):
        with pytest.raises(MemoryAdmissionTimeout):
            reserve_memory(700, deadline=time.monotonic() + 0.02)


def test_operation_larger_than_pool_is_rejected():
    with pytest.raises(MemoryAdmissionTimeout, match='exceeds'):
        reserve_memory(900)


def test_pressure_must_leave_configured_headroom(monkeypatch):
    monkeypatch.setattr(config, 'EXTRACTION_MIN_AVAILABLE_BYTES', 200)
    with pytest.raises(MemoryAdmissionTimeout):
        reserve_memory(700, deadline=time.monotonic() + 0.02)


def test_sync_and_async_share_fifo_capacity():
    async def check():
        order = []
        first = reserve_memory(700)

        async def work(name, size):
            with await reserve_memory_async(size):
                order.append(name)
                await asyncio.sleep(0.01)

        big = asyncio.create_task(work('big', 700))
        await asyncio.sleep(0)
        small = asyncio.create_task(work('small', 100))
        await asyncio.sleep(0.02)
        assert order == []  # A small newcomer cannot bypass the queued job.
        first.release()
        await asyncio.gather(big, small)
        assert order == ['big', 'small']

    asyncio.run(check())


def test_cancelled_waiter_does_not_block_the_next_job():
    async def check():
        with reserve_memory(700):
            task = asyncio.create_task(reserve_memory_async(700))
            await asyncio.sleep(0.01)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            with await reserve_memory_async(100):
                assert memory_budget._reserved_bytes == 800

    asyncio.run(check())


def test_exception_releases_capacity():
    with pytest.raises(ValueError):
        with reserve_memory(700):
            raise ValueError('failed work')
    with reserve_memory(700):
        assert memory_budget._reserved_bytes == 700


def test_download_capacity_follows_retained_bytes():
    reservation = reserve_memory(700)
    data = ReservedBytes(b'packet', reservation)
    del reservation
    another_reference = data
    del data
    gc.collect()
    assert memory_budget._reserved_bytes == 700
    assert another_reference == b'packet'
    del another_reference
    gc.collect()
    assert memory_budget._reserved_bytes == 0
