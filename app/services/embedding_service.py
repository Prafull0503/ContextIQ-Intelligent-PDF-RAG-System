"""Embedding provider factory.

Builds a LangChain ``Embeddings`` object based on the configured provider.
This isolates provider-specific construction in one place (Open/Closed
principle: add a provider here, not throughout the codebase).
"""

from __future__ import annotations

from langchain_core.embeddings import Embeddings

from app.core.config import EmbeddingProvider, Settings
from app.core.logging_config import get_logger
from app.utils.exceptions import MissingAPIKeyError

logger = get_logger(__name__)


def build_embeddings(settings: Settings) -> Embeddings:
    """Construct an embeddings client for the configured provider.

    Args:
        settings: Application settings.

    Returns:
        A LangChain ``Embeddings`` instance.

    Raises:
        MissingAPIKeyError: If an OpenAI key is required but missing.
    """
    provider = settings.embedding_provider

    if provider == EmbeddingProvider.OPENAI:
        if not settings.openai_api_key:
            raise MissingAPIKeyError(
                "OPENAI_API_KEY is required for OpenAI embeddings."
            )
        # Imported lazily so the package is only needed when actually used.
        from langchain_openai import OpenAIEmbeddings

        logger.info("Using OpenAI embeddings: %s", settings.embedding_model)
        return OpenAIEmbeddings(
            model=settings.embedding_model,
            api_key=settings.openai_api_key,
        )

    if provider == EmbeddingProvider.GEMINI:
        if not settings.google_api_key:
            raise MissingAPIKeyError(
                "GOOGLE_API_KEY is required for Gemini embeddings."
            )
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        logger.info("Using Gemini embeddings: %s", settings.embedding_model)
        return GoogleGenerativeAIEmbeddings(
            model=settings.embedding_model,
            google_api_key=settings.google_api_key,
        )

    if provider == EmbeddingProvider.HUGGINGFACE:
        from langchain_huggingface import HuggingFaceEmbeddings

        logger.info("Using HuggingFace embeddings: %s", settings.embedding_model)
        # Local model; downloaded on first use and cached thereafter.
        return HuggingFaceEmbeddings(
            model_name=settings.embedding_model,
            encode_kwargs={"normalize_embeddings": True},
        )

    if provider == EmbeddingProvider.OLLAMA:
        from langchain_ollama import OllamaEmbeddings

        logger.info(
            "Using Ollama embeddings: %s (%s)",
            settings.embedding_model,
            settings.ollama_base_url,
        )
        # Served locally by a running Ollama instance — no API key needed.
        return OllamaEmbeddings(
            model=settings.embedding_model,
            base_url=settings.ollama_base_url,
        )

    # Defensive: enum guarantees this is unreachable.
    raise ValueError(f"Unsupported embedding provider: {provider}")
