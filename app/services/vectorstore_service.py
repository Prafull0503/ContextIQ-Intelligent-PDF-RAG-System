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

# Reciprocal Rank Fusion constant. 60 is the standard value from the original
# RRF paper (Cormack et al.) -- it dampens the impact of rank 1 vs rank 2
# without needing per-corpus tuning.
_RRF_K = 60.0

# Baseline similarity assigned to chunks that only matched via BM25 keyword
# search (no vector hit). Purely informational for downstream display /
# reranking input -- the actual retrieval order is decided by RRF, not by
# this number.
_BM25_ONLY_BASELINE_SCORE = 0.5


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
    @staticmethod
    def _build_filter(
        filter_source: str | None, filter_user_id: int | None
    ) -> dict | None:
        """Build a Chroma ``where`` filter from the optional constraints."""
        if filter_source and filter_user_id is not None:
            return {"$and": [{"source": filter_source}, {"user_id": filter_user_id}]}
        if filter_user_id is not None:
            return {"user_id": filter_user_id}
        if filter_source:
            return {"source": filter_source}
        return None

    def similarity_search(
        self, query: str, k: int, filter_source: str | None = None, filter_user_id: int | None = None
    ) -> list[tuple[Document, float]]:
        """Return the top-``k`` chunks with similarity scores in [0, 1] using Hybrid Search (Vector + BM25 RRF).

        Args:
            query: The user question.
            k: Number of chunks to retrieve.
            filter_source: Optional document source filename to filter by.
            filter_user_id: Optional user ID to isolate context search.

        Returns:
            List of ``(Document, similarity_score)`` tuples, best first.
        """
        search_filter = self._build_filter(filter_source, filter_user_id)

        # 1. Vector search with score
        try:
            vector_results = self._store.similarity_search_with_score(query, k=k, filter=search_filter)
        except Exception as exc:
            raise VectorStoreError(f"Vector similarity search failed: {exc}") from exc

        vector_ranked: list[tuple[Document, float]] = []
        for doc, distance in vector_results:
            similarity = 1.0 / (1.0 + max(distance, 0.0))
            vector_ranked.append((doc, round(similarity, 4)))

        # 2. BM25 keyword search
        # IMPORTANT: filter at the Chroma level (same `search_filter` used for
        # vector search) rather than fetching the entire collection and
        # filtering in Python. Without this, every single question would pull
        # every chunk from every user into memory just to build a keyword
        # index -- a full-collection scan on the hot path.
        bm25_ranked: list[Document] = []
        try:
            db_docs_data = self._store.get(
                where=search_filter, include=["documents", "metadatas"]
            )
            doc_texts = db_docs_data.get("documents", [])
            metadatas = db_docs_data.get("metadatas", [])

            if doc_texts:
                docs = [
                    Document(page_content=text, metadata=meta)
                    for text, meta in zip(doc_texts, metadatas)
                ]
                from langchain_community.retrievers import BM25Retriever

                bm25_retriever = BM25Retriever.from_documents(docs)
                bm25_retriever.k = k
                bm25_ranked = bm25_retriever.invoke(query)
        except Exception as exc:
            logger.warning("BM25 retrieval failed, falling back to vector search only: %s", exc)

        # 3. Reciprocal Rank Fusion (RRF)
        rrf_scores: dict[str, float] = {}
        doc_map: dict[str, tuple[Document, float]] = {}

        def get_chunk_key(doc: Document) -> str:
            meta = doc.metadata or {}
            source = meta.get("source", "unknown")
            page = meta.get("page", 0)
            idx = meta.get("chunk_index", 0)
            # Use content hash to distinguish duplicate indexing metadata.
            # NOTE: this key only needs to be stable within a single call to
            # this method (it's never persisted), so Python's per-process
            # hash randomization is not a concern here.
            content_hash = hash(doc.page_content)
            return f"{source}_{page}_{idx}_{content_hash}"

        # Vector rankings contribution
        for rank, (doc, sim) in enumerate(vector_ranked, start=1):
            key = get_chunk_key(doc)
            doc_map[key] = (doc, sim)
            rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (_RRF_K + rank)

        # BM25 rankings contribution
        for rank, doc in enumerate(bm25_ranked, start=1):
            key = get_chunk_key(doc)
            if key not in doc_map:
                doc_map[key] = (doc, _BM25_ONLY_BASELINE_SCORE)
            rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (_RRF_K + rank)

        # Sort by RRF score descending
        sorted_keys = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)
        scored = [doc_map[key] for key in sorted_keys[:k]]

        logger.info(
            "Hybrid search retrieved %d chunks for query (Vector count: %d, BM25 count: %d)",
            len(scored), len(vector_ranked), len(bm25_ranked),
        )
        return scored

    def count(self) -> int:
        """Return the total number of chunks currently stored in vector DB."""
        try:
            return self._store._collection.count()
        except Exception as exc:  # pragma: no cover - defensive
            raise VectorStoreError(f"Failed to count documents: {exc}") from exc

    def delete_document(self, filename: str, user_id: int) -> list[str]:
        """Delete all chunks associated with a specific filename and user ID.

        Returns a list of physical stored filenames (unique uuid prefix) to unlink from disk.
        """
        try:
            # Query collection to find the stored physical filenames
            result = self._store.get(
                where={"$and": [{"source": filename}, {"user_id": user_id}]},
                include=["metadatas"]
            )
            metadatas = result.get("metadatas", [])
            stored_files = {m["stored_filename"] for m in metadatas if m and "stored_filename" in m}

            # Delete vector records from ChromaDB
            self._store._collection.delete(
                where={"$and": [{"source": filename}, {"user_id": user_id}]}
            )
            logger.info("Deleted document '%s' for user %d from ChromaDB", filename, user_id)
            return list(stored_files)
        except Exception as exc:
            raise VectorStoreError(f"Failed to delete document '{filename}': {exc}") from exc

    def list_documents(self, user_id: int) -> list[str]:
        """List unique source filenames currently stored in ChromaDB for a specific user."""
        try:
            result = self._store.get(where={"user_id": user_id}, include=["metadatas"])
            metadatas = result.get("metadatas", [])
            sources = {m["source"] for m in metadatas if m and "source" in m}
            return sorted(list(sources))
        except Exception as exc:
            raise VectorStoreError(f"Failed to list documents: {exc}") from exc
            