import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Canteen Management System API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api"

    # PostgreSQL Database URL (AsyncPG driver)
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/canteen_db",
    )

    # Redis URL for High-Performance Caching
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # JWT Authentication Security Settings
    SECRET_KEY: str = os.getenv(
        "SECRET_KEY", "canteen_super_secure_jwt_secret_key_2026_x9f830a1b2c3d4e5"
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # Redis Cache TTL (in seconds)
    CACHE_TTL_SECONDS: int = 300  # 5 minutes

    # Default Admin Credentials for initial setup
    DEFAULT_ADMIN_USERNAME: str = os.getenv("DEFAULT_ADMIN_USERNAME", "admin")
    DEFAULT_ADMIN_PASSWORD: str = os.getenv("DEFAULT_ADMIN_PASSWORD", "admin123")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
