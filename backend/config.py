import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Canteen Management System API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api"

    CORS_ORIGINS: list[str] = [
        "http://localhost:8443", "http://127.0.0.1:8443",
        "http://localhost:5173", "http://127.0.0.1:5173",
    ]

    # PostgreSQL Database URL (AsyncPG driver)
    DATABASE_URL: str

    # Redis URL for High-Performance Caching
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # JWT Authentication Security Settings
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # Redis Cache TTL (in seconds)
    CACHE_TTL_SECONDS: int = 300  # 5 minutes

    # Default Admin Credentials for initial setup
    DEFAULT_ADMIN_USERNAME: str = os.getenv("DEFAULT_ADMIN_USERNAME", "admin")
    DEFAULT_ADMIN_PASSWORD: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
