"""Configuration management - load settings from environment variables."""

from typing import List
import os
from functools import lru_cache


class Settings:
    """Application settings loaded from environment variables."""

    def __init__(self):
        # Load from .env file if it exists, otherwise use environment variables
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass

        self.environment: str = os.getenv("ENVIRONMENT", "development")
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO")
        self.database_path: str = os.getenv("DATABASE_PATH", "products.db")

        # Parse comma-separated CORS origins
        origins_str = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
        self.allowed_origins: List[str] = [
            origin.strip() for origin in origins_str.split(",") if origin.strip()
        ]

    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.environment.lower() == "development"

    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.environment.lower() == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get settings singleton. Cached for performance."""
    return Settings()


# Export a default instance
settings = get_settings()
