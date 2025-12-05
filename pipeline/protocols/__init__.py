"""Pipeline Protocols - Type interfaces for dependency injection"""

from pipeline.protocols.metrics import MetricsCollector, NullMetrics

__all__ = ["MetricsCollector", "NullMetrics"]
