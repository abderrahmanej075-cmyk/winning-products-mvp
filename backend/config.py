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

        # eBay Browse API (Phase 2C)
        self.ebay_client_id: str = os.getenv("EBAY_CLIENT_ID", "")
        self.ebay_client_secret: str = os.getenv("EBAY_CLIENT_SECRET", "")
        self.ebay_env: str = os.getenv("EBAY_ENV", "sandbox").lower()
        self.ebay_fallback_to_stub: bool = (
            os.getenv("EBAY_FALLBACK_TO_STUB", "true").lower() in ("true", "1", "yes")
        )

        # Official Google Trends API (Phase 2G-E) — alpha/access-gated, disabled by default
        # GOOGLE_APPLICATION_CREDENTIALS is managed directly by the Google SDK; document here only.
        self.google_trends_official_enabled: bool = (
            os.getenv("GOOGLE_TRENDS_OFFICIAL_ENABLED", "false").lower() in ("true", "1", "yes")
        )
        self.google_trends_official_access_mode: str = os.getenv(
            "GOOGLE_TRENDS_OFFICIAL_ACCESS_MODE", "alpha"
        )
        self.google_trends_official_timeout_seconds: int = int(
            os.getenv("GOOGLE_TRENDS_OFFICIAL_TIMEOUT_SECONDS", "10")
        )
        self.google_trends_official_geo: str = os.getenv("GOOGLE_TRENDS_OFFICIAL_GEO", "US")
        self.google_trends_official_timeframe: str = os.getenv(
            "GOOGLE_TRENDS_OFFICIAL_TIMEFRAME", "today 12-m"
        )
        self.google_cloud_project_id: str = os.getenv("GOOGLE_CLOUD_PROJECT_ID", "")
        # BigQuery public trends dataset — alternative to alpha API, no scraping
        self.google_bigquery_trends_enabled: bool = (
            os.getenv("GOOGLE_BIGQUERY_TRENDS_ENABLED", "false").lower() in ("true", "1", "yes")
        )
        self.google_bigquery_trends_dataset: str = os.getenv(
            "GOOGLE_BIGQUERY_TRENDS_DATASET", "bigquery-public-data.google_trends"
        )

        # Amazon Product Advertising API v5 (Phase 2G-D)
        self.amazon_paapi_access_key: str = os.getenv("AMAZON_PAAPI_ACCESS_KEY", "")
        self.amazon_paapi_secret_key: str = os.getenv("AMAZON_PAAPI_SECRET_KEY", "")
        self.amazon_paapi_partner_tag: str = os.getenv("AMAZON_PAAPI_PARTNER_TAG", "")

        # Keepa API — Amazon BSR alternative (Phase 2G-D)
        self.keepa_api_key: str = os.getenv("KEEPA_API_KEY", "")

        # TikTok Research API (Phase 2G-D)
        self.tiktok_research_api_key: str = os.getenv("TIKTOK_RESEARCH_API_KEY", "")

        # Meta Marketing API (Phase 2G-D)
        self.meta_marketing_access_token: str = os.getenv("META_MARKETING_ACCESS_TOKEN", "")

        # AliExpress Affiliate API (Phase 2G-D)
        self.aliexpress_api_key: str = os.getenv("ALIEXPRESS_API_KEY", "")

        # CJ Dropshipping API (Phase 2G-D)
        self.cj_api_key: str = os.getenv("CJ_API_KEY", "")

        # Reddit API — PRAW (Phase 2G-D)
        self.reddit_client_id: str = os.getenv("REDDIT_CLIENT_ID", "")
        self.reddit_client_secret: str = os.getenv("REDDIT_CLIENT_SECRET", "")

        # YouTube Data API v3 (Phase 2G-D)
        self.youtube_api_key: str = os.getenv("YOUTUBE_API_KEY", "")

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
