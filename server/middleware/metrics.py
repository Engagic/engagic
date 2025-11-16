"""
Prometheus metrics middleware for API requests

Instruments all API requests with:
- Request count (by endpoint, method, status_code)
- Request duration (by endpoint, method)

Usage:
    from server.middleware.metrics import metrics_middleware
    app.middleware("http")(metrics_middleware)

Confidence: 9/10 - Standard middleware pattern
"""

import time
from fastapi import Request

from server.metrics import metrics


async def metrics_middleware(request: Request, call_next):
    """Record Prometheus metrics for all API requests"""
    start_time = time.time()

    # Normalize endpoint path (strip query params, collapse IDs to :id)
    endpoint = _normalize_endpoint(request.url.path)
    method = request.method

    try:
        response = await call_next(request)
        duration = time.time() - start_time

        # Record metrics
        metrics.api_requests.labels(
            endpoint=endpoint,
            method=method,
            status_code=response.status_code
        ).inc()

        metrics.api_request_duration.labels(
            endpoint=endpoint,
            method=method
        ).observe(duration)

        return response

    except Exception:
        duration = time.time() - start_time

        # Record error as 500
        metrics.api_requests.labels(
            endpoint=endpoint,
            method=method,
            status_code=500
        ).inc()

        metrics.api_request_duration.labels(
            endpoint=endpoint,
            method=method
        ).observe(duration)

        raise


def _normalize_endpoint(path: str) -> str:
    """Normalize endpoint path for metrics cardinality control

    Converts:
        /api/meeting/12345 -> /api/meeting/:id
        /api/matters/austinTX_abc123/timeline -> /api/matters/:matter_banana/timeline
        /api/city/sfCA/matters -> /api/city/:city_banana/matters

    Args:
        path: Raw URL path

    Returns:
        Normalized path with IDs replaced by :id
    """
    parts = path.split('/')
    normalized_parts = []

    for i, part in enumerate(parts):
        if not part:
            continue

        # Check if this looks like an ID
        if _is_id_like(part, i, parts):
            # Determine the type based on context
            if i > 0 and parts[i-1] == 'meeting':
                normalized_parts.append(':meeting_id')
            elif i > 0 and parts[i-1] == 'matters':
                normalized_parts.append(':matter_banana')
            elif i > 0 and parts[i-1] == 'city':
                normalized_parts.append(':city_banana')
            elif i > 0 and parts[i-1] == 'state':
                normalized_parts.append(':state_code')
            else:
                normalized_parts.append(':id')
        else:
            normalized_parts.append(part)

    return '/' + '/'.join(normalized_parts)


def _is_id_like(part: str, index: int, parts: list) -> bool:
    """Check if a path part looks like an ID

    IDs are typically:
    - All digits (meeting IDs like 12345)
    - Contains underscores (matter_banana like austinTX_abc123)
    - Two letter uppercase (state codes like CA, TX)
    - Lowercase with CA/TX suffix (city_banana like sfCA, austinTX)

    Args:
        part: Path component to check
        index: Index in parts list
        parts: Full path parts for context

    Returns:
        True if this looks like an ID
    """
    if not part:
        return False

    # Check context - what comes before this part?
    prev_part = parts[index - 1] if index > 0 else None

    # Meeting IDs are always numeric
    if prev_part == 'meeting' and part.isdigit():
        return True

    # Matter bananas contain underscores
    if prev_part == 'matters' and '_' in part:
        return True

    # City bananas end with state codes
    if prev_part == 'city' and len(part) > 2 and part[-2:].isupper():
        return True

    # State codes are exactly 2 uppercase letters
    if prev_part == 'state' and len(part) == 2 and part.isupper():
        return True

    # Generic numeric IDs
    if part.isdigit():
        return True

    return False
