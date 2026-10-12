from functools import lru_cache
from typing import Literal

from pydantic import Field, HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FEEDBACK_HUB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["local", "test", "staging", "production"] = "local"
    service_name: str = "feedback-hub-api"

    database_url: SecretStr | None = None
    database_pool_size: int = Field(default=5, gt=0)

    supabase_url: HttpUrl | None = None
    jwt_audience: str = "authenticated"
    jwks_cache_seconds: int = Field(default=600, gt=0)

    github_api_base_url: str = "https://api.github.com"
    github_api_version: str = "2026-03-10"
    github_token: SecretStr | None = None
    github_timeout_seconds: float = Field(default=10.0, gt=0)
    github_import_limit: int = Field(default=100, ge=1, le=500)

    allowed_licenses: frozenset[str] = frozenset(
        {
            "Apache-2.0",
            "BSD-2-Clause",
            "BSD-3-Clause",
            "MIT",
            "MPL-2.0",
            "ISC",
            "LGPL-2.1",
            "LGPL-3.0",
            "GPL-2.0",
            "GPL-3.0",
            "AGPL-3.0",
            "EPL-2.0",
            "Unlicense",
        }
    )

    gemini_api_key: SecretStr | None = None
    gemini_api_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_embedding_model: str = "gemini-embedding-001"
    gemini_embedding_dimensions: Literal[768] = 768
    gemini_embedding_version: str = "1"
    gemini_timeout_seconds: float = Field(default=30.0, gt=0)
    gemini_embedding_batch_size: int = Field(default=16, ge=1, le=100)

    csv_max_bytes: int = Field(default=1_000_000, gt=0)
    csv_max_rows: int = Field(default=10_000, gt=0)
    csv_max_feedback_chars: int = Field(default=10_000, gt=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
