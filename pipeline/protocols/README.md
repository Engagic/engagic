# pipeline/protocols/

Type interfaces for dependency injection. Breaks compile-time coupling.

## Files

- `metrics.py` - `MetricsCollector` Protocol + `NullMetrics` implementation

## Usage

```python
from pipeline.protocols import MetricsCollector, NullMetrics

class Processor:
    def __init__(self, db, metrics: MetricsCollector = None):
        self.metrics = metrics or NullMetrics()
```

## Why

Pipeline can now run without server module. Tests use `NullMetrics`.
