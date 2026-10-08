from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application runtime settings loaded from environment or .env file."""

    APP_NAME: str = "CertFlow"
    ENV: str = "development"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/certflow"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800

    # Storage
    STORAGE_DIR: str = "./storage/certificates"

    # Batch & Queue Configuration
    MAX_RECIPIENTS_PER_JOB: int = 10000
    WORKER_BATCH_SIZE: int = 50
    WORKER_LOCK_TIMEOUT_SECONDS: int = 120  # 2 minutes lease
    WORKER_POLL_INTERVAL_SECONDS: float = 1.0
    MAX_ATTEMPTS: int = 3

    # Verification URL base for QR code embedding
    VERIFICATION_BASE_URL: str = "http://localhost:8000/verify"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()
