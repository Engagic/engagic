"""
Engagic API Server

Clean, modular FastAPI application with separation of concerns.
Routes, services, and utilities are organized into focused modules.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import config, get_logger
from database.db_postgres import Database
from server.rate_limiter import SQLiteRateLimiter
from server.middleware.logging import log_requests
from server.middleware.metrics import metrics_middleware
from server.middleware.request_id import RequestIDMiddleware
from server.routes import search, meetings, topics, admin, monitoring, flyer, matters, donate, auth, dashboard
from userland.auth import init_jwt
from userland.database.db import UserlandDB

logger = get_logger(__name__)

# Configure structured logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(config.LOG_PATH, mode="a")],
)


# Lifespan context manager for database initialization
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup async database connection pool"""
    # Startup: Create PostgreSQL connection pool
    db = await Database.create()
    logger.info("initialized PostgreSQL database with async connection pool")

    # Store in app state
    app.state.db = db

    yield

    # Shutdown: Close connection pool
    try:
        # Log connection count before closing
        active_connections = db.pool.get_size()
        logger.info(
            "closing connection pool",
            active_connections=active_connections,
            min_size=db.pool.get_min_size(),
            max_size=db.pool.get_max_size(),
        )

        await db.close()
        logger.info("closed PostgreSQL connection pool")

        # Warn if connections were active during shutdown (potential leaks)
        if active_connections > 0:
            logger.warning(
                "connection pool had active connections on shutdown",
                count=active_connections,
            )

    except Exception as e:
        # Don't crash on shutdown - log and continue
        logger.error("error closing connection pool", error=str(e), exc_info=True)
        # Don't re-raise - allow shutdown to proceed gracefully


# Initialize FastAPI app with lifespan
app = FastAPI(title="engagic API", description="EGMI", lifespan=lifespan)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# Request ID middleware (must be early in stack for tracing)
app.add_middleware(RequestIDMiddleware)

# Initialize global instances (non-async)
rate_limiter = SQLiteRateLimiter(
    db_path=str(config.UNIFIED_DB_PATH).replace("engagic.db", "rate_limits.db"),
    requests_limit=config.RATE_LIMIT_REQUESTS,
    window_seconds=config.RATE_LIMIT_WINDOW,
)

# Initialize userland database for auth and user features (SQLite, sync)
userland_db_path = os.getenv('USERLAND_DB', str(config.DB_DIR) + '/userland.db')
userland_db = UserlandDB(userland_db_path, silent=False)
logger.info("initialized userland database", db_path=userland_db_path)

# Initialize JWT for authentication
jwt_secret = os.getenv('USERLAND_JWT_SECRET')
if not jwt_secret:
    logger.warning("WARNING: USERLAND_JWT_SECRET not set. Auth features will not work.")
    logger.warning("Generate with: python3 -c 'import secrets; print(secrets.token_urlsafe(32))'")
else:
    init_jwt(jwt_secret)
    logger.info("JWT authentication initialized")

# Store userland_db in app state (main db initialized in lifespan)
app.state.userland_db = userland_db


# Register middleware (execution order: metrics -> rate limiting -> logging)
# FastAPI middleware stack: last registered runs first, so register in reverse order
@app.middleware("http")
async def log_requests_middleware(request, call_next):
    return await log_requests(request, call_next)


@app.middleware("http")
async def rate_limit_middleware_wrapper(request, call_next):
    from server.middleware.rate_limiting import rate_limit_middleware
    return await rate_limit_middleware(request, call_next, rate_limiter)


@app.middleware("http")
async def metrics_middleware_wrapper(request, call_next):
    return await metrics_middleware(request, call_next)


# Mount routers
app.include_router(monitoring.router)  # Root and monitoring endpoints
app.include_router(search.router)      # Search endpoints
app.include_router(meetings.router)    # Meeting endpoints
app.include_router(topics.router)      # Topic endpoints
app.include_router(admin.router)       # Admin endpoints
app.include_router(flyer.router)       # Flyer generation endpoints
app.include_router(matters.router)     # Matter timeline and tracking endpoints
app.include_router(donate.router)      # Donation and payment endpoints
app.include_router(auth.router)        # Authentication endpoints (userland)
app.include_router(dashboard.router)   # User dashboard and alerts (userland)


if __name__ == "__main__":
    import uvicorn
    import sys

    # Validate critical environment variables on startup
    if not config.get_api_key():
        logger.warning(
            "WARNING: No LLM API key configured. AI features will be disabled."
        )
        logger.warning("Set ANTHROPIC_API_KEY or LLM_API_KEY to enable AI summaries.")

    if not config.ADMIN_TOKEN:
        logger.warning(
            "WARNING: No admin token configured. Admin endpoints will not work."
        )
        logger.warning("Set ENGAGIC_ADMIN_TOKEN to enable admin functionality.")

    logger.info("Starting engagic API server...")
    logger.info("configuration", config_summary=config.summary())

    # Handle command line arguments
    if len(sys.argv) > 1 and sys.argv[1] == "--init-db":
        logger.info("Initializing databases...")
        import asyncio
        from database.db_postgres import Database

        async def init_db():
            db = await Database.create()
            try:
                _ = await db.get_stats()
                logger.info("Database initialized successfully")
            finally:
                await db.close()

        asyncio.run(init_db())
        sys.exit(0)

    uvicorn.run(
        app,
        host=config.API_HOST,
        port=config.API_PORT,
        access_log=False,  # Disable default uvicorn logs (we have custom middleware logging)
    )
