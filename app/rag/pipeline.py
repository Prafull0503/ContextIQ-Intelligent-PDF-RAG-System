"""RAG query pipeline (the read path).

Flow:
    question -> embed + similarity search -> top-K retrieval
             -> context injection -> LLM -> grounded answer (+ sources)

This is a custom, transparent RAG chain (rather than the now-deprecated
``RetrievalQA``) so we have full control over the prompt, the returned source
chunks, and the confidence score.
"""

from __future__ import annotations

from dataclasses import dataclass

from langchain_core.documents import Document
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.core.config import Settings
from app.core.logging_config import get_logger
from app.services.vectorstore_service import VectorStoreService
from app.utils.exceptions import LLMError, NoDocumentsError

logger = get_logger(__name__)


# The system prompt enforces strict grounding AND a minimal, to-the-point
# answer: only what was asked, nothing extra, and a fixed fallback message when
# the question is outside the PDF content.
_NOT_FOUND_MESSAGE = "Content not found in the PDF."

_SYSTEM_PROMPT = (
    "You answer questions strictly and only from the provided context, which is "
    "extracted from uploaded PDF documents.\n"
    "Rules:\n"
    "1. Use ONLY the information in the context. Never use outside knowledge or "
    "make assumptions.\n"
    "2. Answer ONLY what is asked. Be direct and minimal — do not add extra "
    "details, background, explanations, examples, or summaries that were not "
    "requested.\n"
    "3. Do NOT include source filenames, page numbers, or citations in your "
    "answer (sources are returned separately).\n"
    "4. If the answer to the question is not present in the context, reply with "
    f"EXACTLY this and nothing else: \"{_NOT_FOUND_MESSAGE}\"\n"
)

_HUMAN_PROMPT = "Context:\n{context}\n\nQuestion: {question}\n\nAnswer:"


@dataclass
class RetrievedChunk:
    """A retrieved chunk paired with its similarity score."""

    document: Document
    score: float


@dataclass
class RAGAnswer:
    """The final result of a RAG query."""

    answer: str
    chunks: list[RetrievedChunk]
    confidence: float


class RAGPipeline:
    """Custom retrieval-augmented generation chain."""

    def __init__(
        self,
        settings: Settings,
        vector_store: VectorStoreService,
        llm: BaseChatModel,
    ) -> None:
        self._settings = settings
        self._vector_store = vector_store
        self._llm = llm
        self._prompt = ChatPromptTemplate.from_messages(
            [("system", _SYSTEM_PROMPT), ("human", _HUMAN_PROMPT)]
        )
        # LangChain Expression Language chain: prompt -> llm -> string.
        self._chain = self._prompt | self._llm | StrOutputParser()

    def answer(self, question: str, top_k: int | None = None) -> RAGAnswer:
        """Answer a question from the indexed documents.

        Args:
            question: The user's natural-language question.
            top_k: Optional override for the number of chunks to retrieve.

        Returns:
            A :class:`RAGAnswer` with the answer, source chunks and confidence.

        Raises:
            NoDocumentsError: If nothing has been ingested yet.
            LLMError: If the LLM call fails.
        """
        k = top_k or self._settings.retrieval_top_k

        if self._vector_store.count() == 0:
            raise NoDocumentsError(
                "No documents have been indexed yet. Upload a PDF first."
            )

        # --- Retrieval: embedding + similarity search + top-K ---
        retrieved = self._vector_store.similarity_search(question, k=k)
        chunks = [RetrievedChunk(document=doc, score=score) for doc, score in retrieved]

        if not chunks:
            logger.info("No relevant chunks found for question.")
            return RAGAnswer(
                answer=_NOT_FOUND_MESSAGE,
                chunks=[],
                confidence=0.0,
            )

        # --- Context injection ---
        context = self._format_context(chunks)

        # --- Generation ---
        try:
            answer = self._chain.invoke({"context": context, "question": question})
        except Exception as exc:
            raise LLMError(f"LLM failed to generate an answer: {exc}") from exc

        answer = answer.strip()

        # If the question was outside the PDF content, return the fixed message
        # with no sources/confidence — the retrieved chunks aren't a real answer.
        if answer == _NOT_FOUND_MESSAGE:
            logger.info("Question not answerable from the indexed PDFs.")
            return RAGAnswer(answer=_NOT_FOUND_MESSAGE, chunks=[], confidence=0.0)

        confidence = self._confidence(chunks)
        logger.info(
            "Answered question using %d chunk(s) (confidence=%.2f)",
            len(chunks),
            confidence,
        )
        return RAGAnswer(
            answer=answer, chunks=chunks, confidence=confidence
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _format_context(chunks: list[RetrievedChunk]) -> str:
        """Render retrieved chunks into a single, source-labelled context block."""
        blocks: list[str] = []
        for i, chunk in enumerate(chunks, start=1):
            meta = chunk.document.metadata
            source = meta.get("source", "unknown")
            page = meta.get("page")
            label = f"[Source {i}: {source}"
            label += f", page {page}]" if page is not None else "]"
            blocks.append(f"{label}\n{chunk.document.page_content}")
        return "\n\n---\n\n".join(blocks)

    @staticmethod
    def _confidence(chunks: list[RetrievedChunk]) -> float:
        """Aggregate confidence from retrieval similarity.

        We blend the best score (peak relevance) with the mean of the top
        scores (overall support), which is more robust than either alone.
        """
        scores = [c.score for c in chunks]
        top = scores[: min(3, len(scores))]
        best = max(scores)
        mean_top = sum(top) / len(top)
        return round(0.5 * best + 0.5 * mean_top, 4)
