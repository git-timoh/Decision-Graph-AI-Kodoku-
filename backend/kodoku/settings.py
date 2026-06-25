"""Application settings loaded from environment variables."""
from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources import NoDecode


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Local-first default: a SQLite file in the working dir. Override DATABASE_URL with a
    # postgresql+asyncpg:// URL to run against Postgres (hosted/multi-user).
    database_url: str = "sqlite+aiosqlite:///./kodoku.db"
    app_env: str = "development"
    log_level: str = "INFO"
    # NoDecode prevents pydantic-settings from JSON-parsing the raw env string before
    # our validator runs — without it, "a,b" would raise a JSONDecodeError.
    allowed_origins: Annotated[list[str], NoDecode] = Field(default=["http://localhost:3000"])

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [o.strip() for o in value.split(",") if o.strip()]
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
