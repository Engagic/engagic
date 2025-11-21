"""
Request/response logging middleware
"""


import time
import uuid
from fastapi import Request

from config import get_logger

logger = get_logger(__name__)


async def log_requests(request: Request, call_next):
    """Log incoming requests and responses"""
    # Skip logging for metrics endpoint (Prometheus scraping noise)
    if request.url.path == "/metrics":
        return await call_next(request)

    start_time = time.time()

    # Process request
    try:
        response = await call_next(request)
        duration = time.time() - start_time

        # Build clean one-line log
        user_hash = getattr(request.state, "client_ip_hash", "unknown")[:7]
        path_info = f"{request.method} {request.url.path}"

        # Include search query if available (set by search route)
        search_query = getattr(request.state, "search_query", None)
        if search_query:
            path_info += f' "{search_query}"'

        logger.info(
            f"{path_info} user:{user_hash} → {response.status_code} ({duration:.3f}s)"
        )
        return response

    except Exception as e:
        duration = time.time() - start_time
        user_hash = getattr(request.state, "client_ip_hash", "unknown")[:7]
        logger.error(
            f"{request.method} {request.url.path} user:{user_hash} → ERROR ({duration:.3f}s): {str(e)}"
        )
        raise
