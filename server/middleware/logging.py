"""
Request/response logging middleware
"""

import logging
import time
import uuid
from fastapi import Request

logger = logging.getLogger("engagic")


async def log_requests(request: Request, call_next):
    """Log incoming requests and responses"""
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    # Log incoming request
    logger.info(
        f"[{request_id}] {request.method} {request.url.path} - Client: {request.client.host if request.client else 'unknown'}"
    )

    # Process request
    try:
        response = await call_next(request)
        duration = time.time() - start_time

        # Log response
        logger.info(
            f"[{request_id}] Response: {response.status_code} - Duration: {duration:.3f}s"
        )
        return response

    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"[{request_id}] Error: {str(e)} - Duration: {duration:.3f}s")
        raise
