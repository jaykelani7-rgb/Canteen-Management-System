from typing import Literal
from urllib.parse import urlparse
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Canteen Management System API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api"
    ENVIRONMENT: Literal["development", "test", "production"] = "development"
    DATABASE_URL: str
    DATABASE_POOL_SIZE: int = Field(default=5, ge=1, le=50)
    DATABASE_MAX_OVERFLOW: int = Field(default=5, ge=0, le=50)
    REDIS_URL: str = "redis://localhost:6379/0"
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60, ge=5, le=1440)
    CACHE_TTL_SECONDS: int = Field(default=300, ge=1, le=86400)
    DEFAULT_ADMIN_USERNAME: str = "admin"
    DEFAULT_ADMIN_PASSWORD: str | None = None
    CORS_ORIGINS: list[str] = [
        "http://localhost:8443", "http://127.0.0.1:8443",
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:5174", "http://127.0.0.1:5174",
    ]
    STUDENT_CORS_ORIGINS: list[str] = [
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:5174", "http://127.0.0.1:5174",
    ]
    ADMIN_CORS_ORIGINS: list[str] = ["http://localhost:8443", "http://127.0.0.1:8443"]
    TRUSTED_HOSTS: list[str] = ["localhost", "127.0.0.1", "test", "testserver"]
    AUTO_CREATE_SCHEMA: bool = False
    ENABLE_DEMO_DATA: bool = False
    SESSION_COOKIE_MODE_ENABLED: bool = True
    RATE_LIMIT_ENABLED: bool = True
    AUTH_RATE_LIMIT: int = Field(default=10, ge=1, le=100)
    AUTH_RATE_WINDOW_SECONDS: int = Field(default=60, ge=1, le=3600)
    PAYMENT_PROVIDER: Literal["disabled", "razorpay"] = "disabled"
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""
    PAYMENT_ORDER_EXPIRY_MINUTES: int = Field(default=15, ge=1, le=60)
    PASSCODE_RECOVERY_ENABLED: bool = False
    SMTP_HOST: str = ""
    SMTP_PORT: int = Field(default=587, ge=1, le=65535)
    SMTP_SECURITY: Literal["starttls", "ssl"] = "starttls"
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    SMTP_TIMEOUT_SECONDS: int = Field(default=10, ge=1, le=30)
    RECOVERY_CODE_TTL_SECONDS: int = Field(default=300, ge=60, le=900)
    RECOVERY_MAX_ATTEMPTS: int = Field(default=5, ge=1, le=10)
    RECOVERY_REQUEST_LIMIT: int = Field(default=3, ge=1, le=10)
    RECOVERY_RESET_LIMIT: int = Field(default=10, ge=1, le=30)
    RECOVERY_RATE_WINDOW_SECONDS: int = Field(default=900, ge=60, le=3600)
    RECOVERY_RESEND_COOLDOWN_SECONDS: int = Field(default=60, ge=30, le=300)
    PAYMENT_HTTP_TIMEOUT_SECONDS: int = Field(default=10, ge=1, le=60)
    PACKAGING_FEE_PAISE: int = Field(default=0, ge=0, le=100000)
    ORDER_GST_BASIS_POINTS: int = Field(default=0, ge=0, le=10000)
    PUBLIC_API_ORIGIN: str = ""
    FOOD_IMAGE_LIBRARY_MAX_BYTES: int = Field(default=67108864, ge=1048576, le=268435456)
    DEPLOYMENT_TIER: Literal["development", "staging", "production"] = "development"
    STAGING_QA_WALLET_ENABLED: bool = False
    STAGING_QA_STUDENT_ID: str = ""
    STAGING_QA_STUDENT_ROLL: str = ""
    GEMINI_API_KEY: str = ""
    OCR_MODEL: str = "gemini-3.5-flash-lite"
    OCR_TIMEOUT_SECONDS: int = Field(default=30, ge=5, le=60)

    @model_validator(mode="after")
    def validate_public_api_origin(self):
        if self.PUBLIC_API_ORIGIN:
            origin = urlparse(self.PUBLIC_API_ORIGIN)
            if (origin.scheme not in ("https", "http") or not origin.hostname
                    or origin.username or origin.password or origin.path not in ("", "/")
                    or origin.query or origin.fragment
                    or (self.ENVIRONMENT == "production" and origin.scheme != "https")):
                raise ValueError("Public API origin must be an explicit origin; production requires HTTPS")
            self.PUBLIC_API_ORIGIN = self.PUBLIC_API_ORIGIN.rstrip("/")
        return self

    @model_validator(mode="after")
    def validate_recovery(self):
        if self.PASSCODE_RECOVERY_ENABLED:
            from email.utils import parseaddr
            address = parseaddr(self.SMTP_FROM_EMAIL)[1]
            if (not self.SMTP_HOST or any(c in self.SMTP_HOST for c in "\r\n")
                    or address != self.SMTP_FROM_EMAIL or address.count("@") != 1
                    or "." not in address.split("@")[-1] or any(c in address for c in "\r\n")
                    or bool(self.SMTP_USERNAME) != bool(self.SMTP_PASSWORD)):
                raise ValueError("Enabled recovery requires a valid SMTP host, sender and paired authentication settings")
        return self

    @model_validator(mode="after")
    def validate_production(self):
        if self.ENVIRONMENT != "production":
            return self
        if len(self.SECRET_KEY.encode()) < 32 or self.SECRET_KEY.startswith("canteen_super_secure_"):
            raise ValueError("Production requires a fresh random signing secret of at least 32 bytes")
        if self.ENABLE_DEMO_DATA:
            raise ValueError("Production cannot enable demo data")
        if self.AUTO_CREATE_SCHEMA:
            raise ValueError("Production schema changes must use reviewed migrations")
        if not self.CORS_ORIGINS or any(
            value == "*" or urlparse(value).scheme != "https" or not urlparse(value).netloc
            or urlparse(value).path not in ("", "/")
            or urlparse(value).username or urlparse(value).password
            or urlparse(value).query or urlparse(value).fragment
            for value in self.CORS_ORIGINS
        ):
            raise ValueError("Production CORS requires explicit HTTPS frontend origins")
        if self.SESSION_COOKIE_MODE_ENABLED:
            all_origins = {value.rstrip("/") for value in self.CORS_ORIGINS}
            role_origins = []
            for values in (self.STUDENT_CORS_ORIGINS, self.ADMIN_CORS_ORIGINS):
                if not values or any(
                    urlparse(value).scheme != "https" or not urlparse(value).netloc
                    or "*" in value or urlparse(value).path not in ("", "/")
                    or urlparse(value).username or urlparse(value).password
                    or urlparse(value).query or urlparse(value).fragment
                    for value in values
                ):
                    raise ValueError("Production cookie sessions require explicit HTTPS origins for each role")
                normalized = {value.rstrip("/") for value in values}
                if not normalized.issubset(all_origins):
                    raise ValueError("Role origins must also be included in CORS_ORIGINS")
                role_origins.append(normalized)
            if role_origins[0] & role_origins[1]:
                raise ValueError("Student and administrator cookie origins must be separate")
        if not self.TRUSTED_HOSTS or any(
            "*" in value or "://" in value or "/" in value for value in self.TRUSTED_HOSTS
        ) or all(value in {"localhost", "127.0.0.1", "test", "testserver"} for value in self.TRUSTED_HOSTS):
            raise ValueError("Production requires explicit deployment hostnames")
        if self.PAYMENT_PROVIDER == "razorpay" and not all(
            (self.RAZORPAY_KEY_ID, self.RAZORPAY_KEY_SECRET, self.RAZORPAY_WEBHOOK_SECRET)
        ):
            raise ValueError("Payment provider credentials and webhook signing secret are required")
        return self

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore",
        hide_input_in_errors=True,
    )


settings = Settings()
