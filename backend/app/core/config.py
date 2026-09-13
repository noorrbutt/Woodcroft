"""Application settings, loaded from environment / .env.

Everything the app can be tuned with lives here. Runtime-mutable store settings
(tax mode, COD surcharge, free-shipping threshold) are seeded from these values
into the ``store_setting`` table and are subsequently edited in Admin -> Settings;
the values here are only the bootstrap defaults.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR / ".env", BACKEND_DIR.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── Application ──────────────────────────────────────────────────────────
    APP_NAME: str = "Woodcroft"
    APP_ENV: Literal["development", "test", "production"] = "development"
    DEBUG: bool = True
    SECRET_KEY: str = "dev-only-insecure-key-change-in-production"
    API_V1_PREFIX: str = "/api/v1"

    # ── Database ─────────────────────────────────────────────────────────────
    # Must use the psycopg3 driver. A bare postgresql:// URL resolves to psycopg2.
    DATABASE_URL: str = (
        "postgresql+psycopg://woodcroft:woodcroft@localhost:5432/woodcroft_dev"
    )
    TEST_DATABASE_URL: str = (
        "postgresql+psycopg://woodcroft:woodcroft@localhost:5432/woodcroft_test"
    )
    DB_ECHO: bool = False
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # ── Auth ─────────────────────────────────────────────────────────────────
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    REFRESH_TOKEN_REMEMBER_ME_DAYS: int = 90
    JWT_ALGORITHM: str = "HS256"
    MAX_FAILED_LOGINS: int = 5
    ACCOUNT_LOCKOUT_MINUTES: int = 15
    EMAIL_VERIFICATION_EXPIRE_HOURS: int = 48
    PASSWORD_RESET_EXPIRE_HOURS: int = 2

    # ── Store defaults ───────────────────────────────────────────────────────
    STORE_CURRENCY: str = "PKR"
    STORE_TIMEZONE: str = "Asia/Karachi"
    TAX_MODE: Literal["inclusive", "exclusive"] = "inclusive"
    #: Basis points so the rate stays an exact integer. 1800 bp == 18.00%.
    DEFAULT_TAX_RATE_BP: int = 1800
    COD_SURCHARGE_PAISA: int = 20_000
    FREE_SHIPPING_THRESHOLD_PAISA: int = 2_000_000

    # ── Notifications ────────────────────────────────────────────────────────
    EMAIL_DRIVER: Literal["outbox", "smtp"] = "outbox"
    SMS_DRIVER: Literal["outbox", "sms_gateway"] = "outbox"
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "noreply@woodcroft.pk"
    SMS_GATEWAY_URL: str = ""
    SMS_GATEWAY_KEY: str = ""

    # ── Payments ─────────────────────────────────────────────────────────────
    PAYMENT_COD_ENABLED: bool = True
    JAZZCASH_ENABLED: bool = False
    JAZZCASH_MERCHANT_ID: str = ""
    JAZZCASH_PASSWORD: str = ""
    JAZZCASH_INTEGRITY_SALT: str = ""
    EASYPAISA_ENABLED: bool = False
    EASYPAISA_STORE_ID: str = ""
    EASYPAISA_HASH_KEY: str = ""

    # ── Media ────────────────────────────────────────────────────────────────
    MEDIA_ROOT: str = "media"
    MEDIA_URL: str = "/media"
    SEED_IMAGE_MODE: Literal["generated", "curated"] = "generated"
    UNSPLASH_ACCESS_KEY: str = ""

    # ── CORS ─────────────────────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    # ── Workers ──────────────────────────────────────────────────────────────
    ENABLE_BACKGROUND_WORKER: bool = True
    WORKER_POLL_SECONDS: int = 10
    STOCK_RESERVATION_TTL_MINUTES: int = 20

    # ── Rate limits (slowapi syntax) ─────────────────────────────────────────
    RATE_LIMIT_LOGIN: str = "10/minute"
    RATE_LIMIT_REGISTER: str = "5/minute"
    RATE_LIMIT_PASSWORD_RESET: str = "3/minute"
    RATE_LIMIT_CHECKOUT: str = "20/minute"

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        """Accept a comma-separated string from .env as well as a real list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @property
    def media_path(self) -> Path:
        """Absolute path to the media directory, created on first access."""
        path = Path(self.MEDIA_ROOT)
        if not path.is_absolute():
            path = BACKEND_DIR / path
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
