from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "LEGAL MASTER"
    app_version: str = "0.1.0"
    environment: str = "development"
    log_level: str = "INFO"

    database_url: str = Field(min_length=1)
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: SecretStr | None = None

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    embedding_provider: Literal["local"] = "local"
    embedding_model: str = "jinaai/jina-embeddings-v2-small-en"
    embedding_dimension: int = Field(default=512, ge=1, le=65_536)
    embedding_cache_path: Path = Path("./data/models")
    embedding_batch_size: int = Field(default=32, ge=1, le=256)
    embedding_max_concurrency: int = Field(default=1, ge=1, le=4)
    chunk_size: int = Field(default=800, ge=50, le=8_192)
    chunk_overlap: int = Field(default=120, ge=0, le=4_096)
    chunk_min_size: int = Field(default=100, ge=1, le=4_096)
    qdrant_collection_name: str = Field(
        default="legal_master_document_chunks",
        pattern=r"^[A-Za-z0-9_-]{1,255}$",
    )
    qdrant_timeout_seconds: int = Field(default=30, ge=1, le=300)
    qdrant_upsert_batch_size: int = Field(default=64, ge=1, le=1_000)

    jwt_secret: SecretStr = Field(min_length=32)
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    jwt_access_token_expire_minutes: int = Field(default=30, gt=0)
    jwt_refresh_token_expire_days: int = Field(default=7, gt=0)
    auth_refresh_cookie_name: str = "legal_master_refresh"

    document_storage_path: Path = Path("./data/documents")
    document_max_size_bytes: int = Field(default=50 * 1024 * 1024, gt=0)
    ocr_enabled: bool = True
    ocr_lang: str = Field(default="eng", pattern=r"^[A-Za-z0-9_+-]+$")
    ocr_dpi: int = Field(default=200, ge=100, le=400)
    ocr_max_pages: int = Field(default=100, ge=1, le=1000)
    ocr_timeout_seconds: int = Field(default=120, ge=1, le=3600)
    ocr_max_image_pixels: int = Field(
        default=25_000_000,
        ge=1_000_000,
        le=100_000_000,
    )
    ocr_max_concurrency: int = Field(default=1, ge=1, le=4)
    frontend_origin: str = "http://localhost:5173"

    @model_validator(mode="after")
    def validate_chunking(self) -> "Settings":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
        if self.chunk_min_size > self.chunk_size:
            raise ValueError("CHUNK_MIN_SIZE must not exceed CHUNK_SIZE")
        return self

    @property
    def auth_cookie_secure(self) -> bool:
        return self.environment.casefold() not in {"development", "local", "test"}

    @property
    def cors_allowed_origins(self) -> list[str]:
        configured = self.frontend_origin.rstrip("/")
        origins = {configured}
        parsed = urlsplit(configured)
        if (
            self.environment.casefold() in {"development", "local", "test"}
            and parsed.scheme in {"http", "https"}
            and parsed.hostname in {"localhost", "127.0.0.1"}
        ):
            port = f":{parsed.port}" if parsed.port is not None else ""
            origins.update({f"{parsed.scheme}://localhost{port}", f"{parsed.scheme}://127.0.0.1{port}"})
        return sorted(origins)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
