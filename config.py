import os
import logging
import sys
from typing import Optional

import structlog

logger = logging.getLogger("engagic")


def get_logger(name: str = "engagic"):
    """Get a structured logger instance

    Usage:
        logger = get_logger(__name__)
        logger = logger.bind(component="vendor", vendor="legistar")
        logger.info("fetching meetings", days_back=7, mode="api")

    Args:
        name: Logger name (typically __name__ or module path)

    Returns:
        Structured logger instance with context binding support
    """
    return structlog.get_logger(name)


class Config:
    """Configuration management for engagic"""

    def __init__(self):
        # Database configuration - unified database (Phase 1 refactor)
        self.DB_DIR = os.getenv("ENGAGIC_DB_DIR", "/root/engagic/data")
        self.UNIFIED_DB_PATH = os.getenv(
            "ENGAGIC_UNIFIED_DB", f"{self.DB_DIR}/engagic.db"
        )

        # Legacy paths kept for migration script only
        self.LOCATIONS_DB_PATH = f"{self.DB_DIR}/locations.db"
        self.MEETINGS_DB_PATH = f"{self.DB_DIR}/meetings.db"
        self.ANALYTICS_DB_PATH = f"{self.DB_DIR}/analytics.db"

        self.LOG_PATH = os.getenv("ENGAGIC_LOG_PATH", "/root/engagic/engagic.log")

        # API configuration
        self.API_HOST = os.getenv("ENGAGIC_HOST", "0.0.0.0")
        self.API_PORT = int(os.getenv("ENGAGIC_PORT", "8000"))
        self.DEBUG = os.getenv("ENGAGIC_DEBUG", "false").lower() == "true"

        # Rate limiting
        self.RATE_LIMIT_REQUESTS = int(os.getenv("ENGAGIC_RATE_LIMIT_REQUESTS", "30"))
        self.RATE_LIMIT_WINDOW = int(os.getenv("ENGAGIC_RATE_LIMIT_WINDOW", "60"))
        self.MAX_QUERY_LENGTH = int(os.getenv("ENGAGIC_MAX_QUERY_LENGTH", "200"))

        # External APIs
        self.ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
        self.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")  # Google Gemini API
        self.LLM_API_KEY = os.getenv("LLM_API_KEY")  # Fallback

        # CORS settings
        self.ALLOWED_ORIGINS = self._parse_origins(
            os.getenv(
                "ENGAGIC_ALLOWED_ORIGINS",
                "https://engagic.org,https://www.engagic.org,https://api.engagic.org,"
                "https://engagic.pages.dev,http://localhost:3000,http://localhost:5173,"
                "http://localhost:5000,http://127.0.0.1:3000,http://192.168.12.190:3000,"
                "https://motioncount.com,https://www.motioncount.com,https://api.motioncount.com",
            )
        )

        # Background processing
        self.BACKGROUND_PROCESSING = (
            os.getenv("ENGAGIC_BACKGROUND_PROCESSING", "true").lower() == "true"
        )
        self.SYNC_INTERVAL_HOURS = int(
            os.getenv("ENGAGIC_SYNC_INTERVAL_HOURS", "72")
        )  # 3 days
        self.PROCESSING_INTERVAL_HOURS = int(
            os.getenv("ENGAGIC_PROCESSING_INTERVAL_HOURS", "2")
        )

        # Logging
        self.LOG_LEVEL = os.getenv("ENGAGIC_LOG_LEVEL", "INFO").upper()

        # Admin authentication
        self.ADMIN_TOKEN = os.getenv("ENGAGIC_ADMIN_TOKEN", "")

        # Vendor API tokens
        self.NYC_LEGISTAR_TOKEN = os.getenv("NYC_LEGISTAR_TOKEN", "")

        # Validate configuration
        self._validate()

    def _parse_origins(self, origins_str: str) -> list:
        """Parse comma-separated origins string"""
        if not origins_str:
            return []
        return [origin.strip() for origin in origins_str.split(",") if origin.strip()]

    def _validate(self):
        """Validate configuration values"""
        if self.RATE_LIMIT_REQUESTS <= 0:
            raise ValueError("ENGAGIC_RATE_LIMIT_REQUESTS must be positive")

        if self.RATE_LIMIT_WINDOW <= 0:
            raise ValueError("ENGAGIC_RATE_LIMIT_WINDOW must be positive")

        if self.MAX_QUERY_LENGTH <= 0:
            raise ValueError("ENGAGIC_MAX_QUERY_LENGTH must be positive")

        if self.API_PORT <= 0 or self.API_PORT > 65535:
            raise ValueError("ENGAGIC_PORT must be between 1 and 65535")

        # Log configuration warnings
        if (
            not self.ANTHROPIC_API_KEY
            and not self.GEMINI_API_KEY
            and not self.LLM_API_KEY
        ):
            logger.warning("No LLM API key configured - AI features will be disabled")

        # Ensure database directory exists
        db_dir = os.path.dirname(self.UNIFIED_DB_PATH)
        if db_dir and not os.path.exists(db_dir):
            logger.info(f"Creating database directory: {db_dir}")
            os.makedirs(db_dir, exist_ok=True)

        if not os.path.exists(os.path.dirname(self.LOG_PATH)):
            logger.warning(
                f"Log directory does not exist: {os.path.dirname(self.LOG_PATH)}"
            )

    def get_api_key(self) -> Optional[str]:
        """Get the appropriate API key for LLM services - prioritize Gemini"""
        return self.GEMINI_API_KEY or self.LLM_API_KEY or self.ANTHROPIC_API_KEY

    def is_development(self) -> bool:
        """Check if running in development mode"""
        return self.DEBUG or "localhost" in str(self.ALLOWED_ORIGINS)

    def summary(self) -> dict:
        """Get a summary of current configuration (excluding secrets)"""
        return {
            "db_dir": self.DB_DIR,
            "database": os.path.basename(self.UNIFIED_DB_PATH),
            "api_host": self.API_HOST,
            "api_port": self.API_PORT,
            "debug": self.DEBUG,
            "rate_limit_requests": self.RATE_LIMIT_REQUESTS,
            "rate_limit_window": self.RATE_LIMIT_WINDOW,
            "max_query_length": self.MAX_QUERY_LENGTH,
            "allowed_origins_count": len(self.ALLOWED_ORIGINS),
            "background_processing": self.BACKGROUND_PROCESSING,
            "sync_interval_hours": self.SYNC_INTERVAL_HOURS,
            "processing_interval_hours": self.PROCESSING_INTERVAL_HOURS,
            "log_level": self.LOG_LEVEL,
            "has_api_key": bool(self.get_api_key()),
            "is_development": self.is_development(),
        }


def configure_structlog(is_development: bool = False, log_level: str = "INFO"):
    """Configure structlog for structured logging

    Args:
        is_development: If True, use human-readable console output. If False, use JSON.
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)

    Confidence: 8/10 - Standard structlog setup with dev/prod modes
    """
    # Convert log level string to logging constant
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Shared processors for all modes
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
    ]

    if is_development:
        # Development: Human-readable colored output
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(
                colors=True,
                exception_formatter=structlog.dev.plain_traceback,
            )
        ]
    else:
        # Production: JSON output for log aggregation
        processors = shared_processors + [
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard logging (for backward compatibility during migration)
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=numeric_level,
    )


# Global configuration instance
config = Config()

# Configure structured logging
# Use development mode if DEBUG=true or localhost in origins
configure_structlog(
    is_development=config.is_development(),
    log_level=config.LOG_LEVEL
)
