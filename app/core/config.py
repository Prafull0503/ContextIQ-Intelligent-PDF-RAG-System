"""Application configuration.

All settings are loaded from environment variables (via a `.env` file) using
``pydantic-settings``. This is the single source of truth for runtime config,
which keeps provider selection, model names and tuning knobs out of the code.
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProvider(str, Enum):
    """Supported LLM providers."""

    OPENAI = "openai"
    GEMINI = "gemini"
    OLLAMA = "ollama"


class EmbeddingProvider(str, Enum):
    """Supported embedding providers."""

    OPENAI = "openai"
    GEMINI = "gemini"
    HUGGINGFACE = "huggingface"
    OLLAMA = "ollama"


_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


class Settings(BaseSettings):
    """Strongly-typed application settings.

    Field names map (case-insensitively) to the environment variables defined
    in ``.env`` / ``.env.example``.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Provider selection ----
    llm_provider: LLMProvider = LLMProvider.OPENAI
    embedding_provider: EmbeddingProvider = EmbeddingProvider.HUGGINGFACE

    # ---- API keys ----
    openai_api_key: str | None = None
    google_api_key: str | None = None

    # ---- Ollama (local, no API key required) ----
    ollama_base_url: str = "http://localhost:11434"

    # ---- Models ----
    llm_model: str = "gpt-4o-mini"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # ---- Vector store ----
    chroma_db_path: str = "./data/chroma_db"
    chroma_collection_name: str = "rag_documents"

    # ---- Ingestion / chunking ----
    chunk_size: int = Field(default=1000, gt=0)
    chunk_overlap: int = Field(default=150, ge=0)
    pdf_upload_dir: str = "./data/pdfs"

    # ---- Retrieval ----
    retrieval_top_k: int = Field(default=5, gt=0)

    # ---- LLM generation ----
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    llm_max_tokens: int = Field(default=1024, gt=0)

    # ---- App ----
    log_level: str = "INFO"

    # ---- Database & Auth ----
    database_url: str = "sqlite:///./data/sqlite.db"
    jwt_secret_key: str = Field(..., min_length=32)
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 1440

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("chunk_overlap")
    @classmethod
    def _overlap_must_be_smaller_than_size(cls, v: int, info) -> int:
        chunk_size = info.data.get("chunk_size", 1000)
        if v >= chunk_size:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
        return v

    @field_validator("log_level")
    @classmethod
    def _log_level_must_be_valid(cls, v: str) -> str:
        upper = v.upper()
        if upper not in _VALID_LOG_LEVELS:
            raise ValueError(
                f"LOG_LEVEL must be one of {sorted(_VALID_LOG_LEVELS)}, got '{v}'"
            )
        return upper

    @model_validator(mode="after")
    def _api_key_required_for_selected_provider(self) -> "Settings":
        """Fail fast at startup if the chosen provider has no matching key.

        Ollama needs no key (it's local). OpenAI/Gemini providers for either
        the LLM or the embedder require their respective key to be set.
        """
        needs_openai = self.llm_provider == LLMProvider.OPENAI or (
            self.embedding_provider == EmbeddingProvider.OPENAI
        )
        needs_google = self.llm_provider == LLMProvider.GEMINI or (
            self.embedding_provider == EmbeddingProvider.GEMINI
        )

        if needs_openai and not self.openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY is required when llm_provider or "
                "embedding_provider is set to 'openai'."
            )
        if needs_google and not self.google_api_key:
            raise ValueError(
                "GOOGLE_API_KEY is required when llm_provider or "
                "embedding_provider is set to 'gemini'."
            )
        return self

    # ------------------------------------------------------------------
    # Derived paths
    # ------------------------------------------------------------------

    @property
    def chroma_db_path_resolved(self) -> Path:
        """Absolute path to the persistent ChromaDB directory."""
        return Path(self.chroma_db_path).expanduser().resolve()

    @property
    def pdf_upload_dir_resolved(self) -> Path:
        """Absolute path to the directory where uploaded PDFs are stored."""
        return Path(self.pdf_upload_dir).expanduser().resolve()

    def ensure_directories(self) -> None:
        """Create the data directories if they don't already exist."""
        self.chroma_db_path_resolved.mkdir(parents=True, exist_ok=True)
        self.pdf_upload_dir_resolved.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance (singleton for the process)."""
    return Settings()
    