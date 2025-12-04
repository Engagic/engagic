"""Metrics Protocol - Interface for metrics collection without concrete dependency"""

from typing import Protocol, Any, ContextManager
from contextlib import contextmanager


class LabeledCounter(Protocol):
    def labels(self, **kwargs: Any) -> "LabeledCounter": ...
    def inc(self, amount: float = 1) -> None: ...


class LabeledHistogram(Protocol):
    def labels(self, **kwargs: Any) -> "LabeledHistogram": ...
    def observe(self, value: float) -> None: ...
    def time(self) -> ContextManager: ...


class MetricsCollector(Protocol):
    """Minimal metrics interface for pipeline operations"""
    queue_jobs_processed: LabeledCounter
    processing_duration: LabeledHistogram
    vendor_requests: LabeledCounter
    meetings_synced: LabeledCounter
    items_extracted: LabeledCounter
    matters_tracked: LabeledCounter

    def record_error(self, component: str, error: Exception) -> None: ...


class _NullCounter:
    def labels(self, **kwargs: Any) -> "_NullCounter":
        return self

    def inc(self, amount: float = 1) -> None:
        pass


class _NullHistogram:
    def labels(self, **kwargs: Any) -> "_NullHistogram":
        return self

    def observe(self, value: float) -> None:
        pass

    @contextmanager
    def time(self):
        yield


class NullMetrics:
    """No-op metrics for testing or standalone use"""

    def __init__(self):
        self.queue_jobs_processed = _NullCounter()
        self.processing_duration = _NullHistogram()
        self.vendor_requests = _NullCounter()
        self.meetings_synced = _NullCounter()
        self.items_extracted = _NullCounter()
        self.matters_tracked = _NullCounter()

    def record_error(self, component: str, error: Exception) -> None:
        pass
