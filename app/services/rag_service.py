"""Application service container.

Wires the individual services and pipelines together into a single, lazily
constructed object. This is the composition root of the application — the one
place where concrete implementations are assembled — which keeps every other
module dependency-injected and unit-testable.

Heavy resources (embedding model, vector store, LLM) are built once and reused
for the lifetime of the process.
"""

from __future__ import annotations

from pathlib import Path

from app.core.config import Settings, get_settings
from app.core.logging_config import get_logger
from app.rag.ingestion import IngestionPipeline, IngestionResult
from app.rag.pipeline import RAGAnswer, RAGPipeline
from app.services.embedding_service import build_embeddings
from app.services.llm_service import build_llm
from app.services.vectorstore_service import VectorStoreService

logger = get_logger(__name__)


class RAGService:
    """Facade exposing the two operations the API needs: ingest and ask."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._settings.ensure_directories()

        # ---- Build shared resources once ----
        self._embeddings = build_embeddings(self._settings)
        self._vector_store = VectorStoreService(self._settings, self._embeddings)

        # The LLM is built lazily so that PDF ingestion works even before an
        # LLM API key is configured.
        self._llm = None
        self._rag_pipeline: RAGPipeline | None = None

        self._ingestion = IngestionPipeline(self._settings, self._vector_store)
        logger.info("RAGService initialised.")

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def settings(self) -> Settings:
        return self._settings

    def document_count(self) -> int:
        """Number of chunks currently stored in the vector DB."""
        return self._vector_store.count()

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------
    def ingest_pdf(self, pdf_path: Path, original_filename: str) -> IngestionResult:
        """Ingest a PDF into the vector store."""
        return self._ingestion.ingest(pdf_path, original_filename)

    def ask(
        self,
        question: str,
        history: list[dict] | None = None,
        top_k: int | None = None,
        selected_document: str | None = None,
    ) -> RAGAnswer:
        """Answer a question using the RAG pipeline (building the LLM lazily)."""
        if self._rag_pipeline is None:
            self._llm = build_llm(self._settings)
            self._rag_pipeline = RAGPipeline(
                self._settings, self._vector_store, self._llm
            )
        return self._rag_pipeline.answer(
            question, history=history, top_k=top_k, selected_document=selected_document
        )

    def list_documents(self, user_id: int) -> list[str]:
        """List unique source filenames currently stored in ChromaDB for a specific user."""
        return self._vector_store.list_documents(user_id)

    def delete_document(self, filename: str, user_id: int) -> None:
        """Delete all chunks for a document from vector store and remove physical file from disk."""
        # Delete from ChromaDB (returns the unique stored filenames uploaded by this user)
        stored_files = self._vector_store.delete_document(filename, user_id)

        # Delete physical file(s)
        upload_dir = self._settings.pdf_upload_dir_resolved
        if upload_dir.exists():
            for path in upload_dir.iterdir():
                if path.is_file() and path.name in stored_files:
                    try:
                        path.unlink()
                        logger.info("Deleted physical file: %s", path)
                    except Exception as exc:
                        logger.warning("Could not delete physical file '%s': %s", path, exc)


# ---------------------------------------------------------------------------
# Process-wide singleton accessor (used by FastAPI dependency injection).
# ---------------------------------------------------------------------------
_service: RAGService | None = None


def get_rag_service() -> RAGService:
    """Return the process-wide :class:`RAGService` singleton."""
    global _service
    if _service is None:
        _service = RAGService()
    return _service
