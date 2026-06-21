"""Persistent ChromaDB vector store wrapper.

Encapsulates all interaction with ChromaDB behind a small, intention-revealing
API. The rest of the application never imports Chroma directly — it depends on
this service, which keeps the storage backend swappable.
"""

from __future__ import annotations

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from app.core.config import Settings
from app.core.logging_config import get_logger
from app.utils.exceptions import VectorStoreError

logger = get_logger(__name__)


class VectorStoreService:
    """Thin, persistent wrapper around a LangChain Chroma collection."""

    def __init__(self, settings: Settings, embeddings: Embeddings) -> None:
        self._settings = settings
        self._embeddings = embeddings
        try:
            settings.ensure_directories()
            # ``persist_directory`` makes the collection durable on disk so the
            # index survives restarts (no re-ingestion needed).
            self._store = Chroma(
                collection_name=settings.chroma_collection_name,
                embedding_function=embeddings,
                persist_directory=str(settings.chroma_db_path_resolved),
            )
            logger.info(
                "ChromaDB ready (collection=%s, path=%s)",
                settings.chroma_collection_name,
                settings.chroma_db_path_resolved,
            )
        except Exception as exc:  # pragma: no cover - init failure is rare
            raise VectorStoreError(
                f"Failed to initialise ChromaDB: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------
    def add_documents(self, documents: list[Document]) -> int:
        """Embed and persist a batch of documents.

        Args:
            documents: Chunked, metadata-tagged documents.

        Returns:
            The number of documents stored.
        """
        if not documents:
            return 0
        try:
            self._store.add_documents(documents)
            logger.info("Stored %d chunks in ChromaDB", len(documents))
            return len(documents)
        except Exception as exc:
            raise VectorStoreError(f"Failed to store documents: {exc}") from exc

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    def similarity_search(
        self, query: str, k: int
    ) -> list[tuple[Document, float]]:
        """Return the top-``k`` chunks with similarity scores in [0, 1].

        Chroma returns a *distance* (lower = closer). We convert it to a
        bounded similarity score so callers get an intuitive, comparable value.

        Args:
            query: The user question.
            k: Number of chunks to retrieve.

        Returns:
            List of ``(Document, similarity_score)`` tuples, best first.
        """
        try:
            results = self._store.similarity_search_with_score(query, k=k)
        except Exception as exc:
            raise VectorStoreError(f"Similarity search failed: {exc}") from exc

        scored: list[tuple[Document, float]] = []
        for doc, distance in results:
            # Map a (potentially unbounded, non-negative) distance to (0, 1].
            similarity = 1.0 / (1.0 + max(distance, 0.0))
            scored.append((doc, round(similarity, 4)))
        logger.info("Retrieved %d chunks for query", len(scored))
        return scored

    def count(self) -> int:
        """Return the number of chunks currently stored."""
        try:
            return self._store._collection.count()
        except Exception as exc:  # pragma: no cover - defensive
            raise VectorStoreError(f"Failed to count documents: {exc}") from exc
