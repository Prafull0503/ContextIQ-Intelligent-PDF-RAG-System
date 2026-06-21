"""FastAPI application factory.

Builds and configures the ASGI app: logging, lifespan warm-up, routers and a
single exception handler that maps domain errors to HTTP responses.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api.routes import router
from app.core.config import get_settings
from app.core.logging_config import configure_logging, get_logger
from app.services.rag_service import get_rag_service
from app.utils.exceptions import RAGError

settings = get_settings()
configure_logging(settings.log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Warm up heavy resources at startup so the first request is fast."""
    logger.info("Starting ContextIQ v%s", __version__)
    logger.info(
        "Providers -> LLM: %s | Embeddings: %s",
        settings.llm_provider.value,
        settings.embedding_provider.value,
    )
    # Eagerly initialise embeddings + vector store (downloads local model once).
    get_rag_service()
    logger.info("Startup complete.")
    yield
    logger.info("Shutting down ContextIQ.")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="ContextIQ",
        description=(
            "Upload PDFs, embed them into ChromaDB, and ask questions answered "
            "strictly from the uploaded content."
        ),
        version=__version__,
        lifespan=lifespan,
    )

    # Permissive CORS for local development / demo front-ends.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Single handler converts any domain error into a proper HTTP response.
    @app.exception_handler(RAGError)
    async def _rag_error_handler(_: Request, exc: RAGError) -> JSONResponse:
        logger.warning("%s -> %d: %s", type(exc).__name__, exc.status_code, exc.message)
        return JSONResponse(
            status_code=exc.status_code, content={"detail": exc.message}
        )

    app.include_router(router)
    return app
