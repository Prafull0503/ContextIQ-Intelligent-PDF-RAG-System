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
        self, query: str, k: int, filter_source: str | None = None
    ) -> list[tuple[Document, float]]:
        """Return the top-``k`` chunks with similarity scores in [0, 1] using Hybrid Search (Vector + BM25 RRF).

        Args:
            query: The user question.
            k: Number of chunks to retrieve.
            filter_source: Optional document source filename to filter by.

        Returns:
            List of ``(Document, similarity_score)`` tuples, best first.
        """
        try:
            # 1. Vector search with score
            search_filter = {"source": filter_source} if filter_source else None
            vector_results = self._store.similarity_search_with_score(query, k=k, filter=search_filter)
        except Exception as exc:
            raise VectorStoreError(f"Vector similarity search failed: {exc}") from exc

        vector_ranked: list[tuple[Document, float]] = []
        for doc, distance in vector_results:
            similarity = 1.0 / (1.0 + max(distance, 0.0))
            vector_ranked.append((doc, round(similarity, 4)))

        # 2. BM25 keyword search
        bm25_ranked: list[Document] = []
        try:
            db_docs_data = self._store.get(include=["documents", "metadatas"])
            doc_texts = db_docs_data.get("documents", [])
            metadatas = db_docs_data.get("metadatas", [])
            
            if doc_texts:
                docs = [
                    Document(page_content=text, metadata=meta)
                    for text, meta in zip(doc_texts, metadatas)
                ]
                if filter_source:
                    docs = [d for d in docs if d.metadata and d.metadata.get("source") == filter_source]
                
                if docs:
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
            # Use content hash to distinguish duplicate indexing metadata
            content_hash = hash(doc.page_content)
            return f"{source}_{page}_{idx}_{content_hash}"

        # Vector rankings contribution
        for rank, (doc, sim) in enumerate(vector_ranked, start=1):
            key = get_chunk_key(doc)
            doc_map[key] = (doc, sim)
            rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (60.0 + rank)

        # BM25 rankings contribution
        for rank, doc in enumerate(bm25_ranked, start=1):
            key = get_chunk_key(doc)
            if key not in doc_map:
                # If only found in keyword search, assign a baseline similarity score
                doc_map[key] = (doc, 0.5)
            rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (60.0 + rank)

        # Sort by RRF score descending
        sorted_keys = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)
        scored = [doc_map[key] for key in sorted_keys[:k]]

        logger.info("Hybrid search retrieved %d chunks for query (Vector count: %d, BM25 count: %d)",
                    len(scored), len(vector_ranked), len(bm25_ranked))
        return scored

    def count(self) -> int:
        """Return the number of chunks currently stored."""
        try:
            return self._store._collection.count()
        except Exception as exc:  # pragma: no cover - defensive
            raise VectorStoreError(f"Failed to count documents: {exc}") from exc

    def delete_document(self, filename: str) -> None:
        """Delete all chunks associated with a specific filename.

        Args:
            filename: The original filename of the document to delete.
        """
        try:
            # Bypass buggy LangChain wrapper and call underlying collection directly
            self._store._collection.delete(where={"source": filename})
            logger.info("Deleted document '%s' from ChromaDB", filename)
        except Exception as exc:
            raise VectorStoreError(f"Failed to delete document '{filename}': {exc}") from exc

    def list_documents(self) -> list[str]:
        """List unique source filenames currently stored in ChromaDB."""
        try:
            result = self._store.get(include=["metadatas"])
            metadatas = result.get("metadatas", [])
            sources = {m["source"] for m in metadatas if m and "source" in m}
            return sorted(list(sources))
        except Exception as exc:
            raise VectorStoreError(f"Failed to list documents: {exc}") from exc
