"""LLM provider factory.

Builds a LangChain chat model based on the configured provider. Switching
between OpenAI and Gemini is purely an environment-variable change.
"""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel

from app.core.config import LLMProvider, Settings
from app.core.logging_config import get_logger
from app.utils.exceptions import MissingAPIKeyError

logger = get_logger(__name__)


def build_llm(settings: Settings) -> BaseChatModel:
    """Construct a chat LLM for the configured provider.

    Args:
        settings: Application settings.

    Returns:
        A LangChain ``BaseChatModel`` instance.

    Raises:
        MissingAPIKeyError: If the provider's API key is missing.
    """
    provider = settings.llm_provider

    if provider == LLMProvider.OPENAI:
        if not settings.openai_api_key:
            raise MissingAPIKeyError("OPENAI_API_KEY is required for OpenAI LLM.")
        from langchain_openai import ChatOpenAI

        logger.info("Using OpenAI chat model: %s", settings.llm_model)
        return ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.openai_api_key,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )

    if provider == LLMProvider.GEMINI:
        if not settings.google_api_key:
            raise MissingAPIKeyError(
                "GOOGLE_API_KEY is required for the Gemini LLM."
            )
        from langchain_google_genai import ChatGoogleGenerativeAI

        logger.info("Using Gemini chat model: %s", settings.llm_model)
        return ChatGoogleGenerativeAI(
            model=settings.llm_model,
            google_api_key=settings.google_api_key,
            temperature=settings.llm_temperature,
            max_output_tokens=settings.llm_max_tokens,
        )

    if provider == LLMProvider.OLLAMA:
        from langchain_ollama import ChatOllama

        logger.info(
            "Using Ollama chat model: %s (%s)",
            settings.llm_model,
            settings.ollama_base_url,
        )
        # Served locally by a running Ollama instance — no API key needed.
        return ChatOllama(
            model=settings.llm_model,
            base_url=settings.ollama_base_url,
            temperature=settings.llm_temperature,
            num_predict=settings.llm_max_tokens,
        )

    raise ValueError(f"Unsupported LLM provider: {provider}")
