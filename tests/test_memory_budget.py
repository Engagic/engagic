import asyncio

from parsing import memory_budget


def test_admits_immediately_when_headroom_exists(monkeypatch):
    monkeypatch.setattr(memory_budget, "available_bytes", lambda: 4 * 1024 ** 3)
    assert memory_budget.wait_for_memory(min_available=1024 ** 3, max_wait_seconds=1) is True


def test_admits_when_proc_meminfo_is_unavailable(monkeypatch):
    monkeypatch.setattr(memory_budget, "available_bytes", lambda: None)
    assert memory_budget.wait_for_memory(min_available=1024 ** 3, max_wait_seconds=1) is True


def test_waits_then_proceeds_anyway_after_deadline(monkeypatch):
    monkeypatch.setattr(memory_budget, "available_bytes", lambda: 100 * 1024 ** 2)
    monkeypatch.setattr(memory_budget, "_POLL_SECONDS", 0.01)
    assert memory_budget.wait_for_memory(min_available=1024 ** 3, max_wait_seconds=0.05) is False


def test_admits_once_memory_frees(monkeypatch):
    readings = iter([100 * 1024 ** 2, 100 * 1024 ** 2, 2 * 1024 ** 3])
    monkeypatch.setattr(memory_budget, "available_bytes", lambda: next(readings))
    monkeypatch.setattr(memory_budget, "_POLL_SECONDS", 0.01)
    assert memory_budget.wait_for_memory(min_available=1024 ** 3, max_wait_seconds=5) is True


def test_async_twin_matches(monkeypatch):
    readings = iter([100 * 1024 ** 2, 2 * 1024 ** 3])
    monkeypatch.setattr(memory_budget, "available_bytes", lambda: next(readings))
    monkeypatch.setattr(memory_budget, "_POLL_SECONDS", 0.01)
    assert asyncio.run(
        memory_budget.wait_for_memory_async(min_available=1024 ** 3, max_wait_seconds=5)
    ) is True


def test_live_meminfo_is_readable():
    available = memory_budget.available_bytes()
    assert available is None or available > 0
