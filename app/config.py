import os
import logging
from typing import Optional

logger = logging.getLogger("engagic")


class Config:
    """Configuration management for engagic"""

    def __init__(self):
        # Database configuration - separate databases for better organization
        self.DB_DIR = os.getenv("ENGAGIC_DB_DIR", "/root/engagic/app/data")
        self.LOCATIONS_DB_PATH = os.getenv(
            "ENGAGIC_LOCATIONS_DB", f"{self.DB_DIR}/locations.db"
        )
        self.MEETINGS_DB_PATH = os.getenv(
            "ENGAGIC_MEETINGS_DB", f"{self.DB_DIR}/meetings.db"
        )
        self.ANALYTICS_DB_PATH = os.getenv(
            "ENGAGIC_ANALYTICS_DB", f"{self.DB_DIR}/analytics.db"
        )

        # Legacy support - if old DB_PATH is set, use it for meetings
        legacy_db_path = os.getenv("ENGAGIC_DB_PATH")
        if legacy_db_path:
            self.MEETINGS_DB_PATH = legacy_db_path
            logger.warning("Using legacy ENGAGIC_DB_PATH for meetings database")

        self.LOG_PATH = os.getenv("ENGAGIC_LOG_PATH", "/root/engagic/app/engagic.log")

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
        self.LLM_API_KEY = os.getenv("LLM_API_KEY")  # Fallback

        # CORS settings
        self.ALLOWED_ORIGINS = self._parse_origins(
            os.getenv(
                "ENGAGIC_ALLOWED_ORIGINS",
                "https://engagic.org,https://www.engagic.org,https://api.engagic.org,"
                "https://engagic.pages.dev,http://localhost:3000,http://localhost:5173,"
                "http://localhost:5000,http://127.0.0.1:3000",
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
        if not self.ANTHROPIC_API_KEY and not self.LLM_API_KEY:
            logger.warning("No LLM API key configured - AI features will be disabled")

        # Ensure database directories exist
        for db_path in [
            self.LOCATIONS_DB_PATH,
            self.MEETINGS_DB_PATH,
            self.ANALYTICS_DB_PATH,
        ]:
            db_dir = os.path.dirname(db_path)
            if db_dir and not os.path.exists(db_dir):
                logger.info(f"Creating database directory: {db_dir}")
                os.makedirs(db_dir, exist_ok=True)

        if not os.path.exists(os.path.dirname(self.LOG_PATH)):
            logger.warning(
                f"Log directory does not exist: {os.path.dirname(self.LOG_PATH)}"
            )

    def get_api_key(self) -> Optional[str]:
        """Get the appropriate API key for LLM services"""
        return self.ANTHROPIC_API_KEY or self.LLM_API_KEY

    def is_development(self) -> bool:
        """Check if running in development mode"""
        return self.DEBUG or "localhost" in str(self.ALLOWED_ORIGINS)

    def summary(self) -> dict:
        """Get a summary of current configuration (excluding secrets)"""
        return {
            "db_dir": self.DB_DIR,
            "databases": {
                "locations": os.path.basename(self.LOCATIONS_DB_PATH),
                "meetings": os.path.basename(self.MEETINGS_DB_PATH),
                "analytics": os.path.basename(self.ANALYTICS_DB_PATH),
            },
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


# Global configuration instance
config = Config()
