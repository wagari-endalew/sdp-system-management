"""
Application configuration.

All values are loaded from environment variables (see .env.example).
For Supabase, DATABASE_URL should be the Supabase Postgres connection string,
e.g. postgresql+asyncpg://postgres:<password>@<project>.supabase.co:5432/postgres
"""
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- App ---
    APP_NAME: str = "SDP Internal Performance & Workflow Management System"
    ENV: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"

    # --- Security / JWT ---
    SECRET_KEY: str = "CHANGE_ME_IN_PRODUCTION_super_secret_key_please_rotate"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    REMEMBER_ME_REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # --- Database (Supabase Postgres) ---
    DATABASE_URL: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/sdp_system"
    )
    # SQLite is used automatically for the test-suite (see tests/conftest.py)

    # --- Redis (rate limiting / caching) ---
    REDIS_URL: str = "redis://localhost:6379/0"
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_PER_MINUTE: int = 60

    # --- CORS ---
    # Kept as a plain string (not List[str]): pydantic-settings tries to
    # JSON-decode any complex-typed field read from .env, which throws on a
    # normal comma-separated value like "http://a,http://b". Use the
    # `cors_origins` property below to get the parsed list.
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # --- Supabase (optional native auth / storage, we primarily use our own JWT) ---
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_KEY: str = ""

    # --- Pagination ---
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    @property
    def cors_origins(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
