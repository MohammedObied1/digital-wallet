from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "Digital Wallet API"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: Literal["development", "testing", "production"] = "development"
    DEBUG: bool = False

    API_V1_PREFIX: str = "/api/v1"

    # Security
    SECRET_KEY: str = "change-me-in-production-use-a-long-random-string"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Database
    DATABASE_URL: str = "sqlite:///./wallet.db"

    # Redis (rate limiting, idempotency cache). Optional in local dev without Docker.
    REDIS_URL: str | None = None

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # Pagination
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    # Rate limiting (requests per window per client)
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    # Financial defaults — overridable per-role/per-user via transfer_limit_policies at runtime.
    # Decimal, not float: these are compared and added directly against Decimal transaction
    # amounts (see limits_service), and Python raises TypeError mixing Decimal with float in
    # arithmetic — so this type is load-bearing, not cosmetic.
    DEFAULT_MAX_TRANSACTION_AMOUNT: Decimal = Decimal("10000")
    DEFAULT_DAILY_TRANSFER_LIMIT: Decimal = Decimal("20000")
    DEFAULT_DAILY_WITHDRAWAL_LIMIT: Decimal = Decimal("10000")

    # Outbox worker
    OUTBOX_POLL_INTERVAL_SECONDS: float = 2.0
    OUTBOX_MAX_ATTEMPTS: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
