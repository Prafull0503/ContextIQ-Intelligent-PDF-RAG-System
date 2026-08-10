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

_HUMAN_PROMPT = (
    "Context:\n{context}\n\n"
    "Chat History:\n{chat_history}\n\n"
    "Question: {question}\n\n"
    "Answer:"
)

_CONDENSE_PROMPT = (
    "Given the following conversation history and a follow-up question, rephrase the follow-up "
    "question to be a standalone question (in its original language), containing all necessary context "
    "from the history. Do not answer the question, just rephrase it.\n\n"
    "Chat History:\n{chat_history}\n\n"
    "Follow-up Question: {question}\n\n"
    "Standalone Question:"
)

_WEB_SYSTEM_PROMPT = (
    "You answer questions strictly and only using the provided web search results.\n"
    "Rules:\n"
    "1. Be direct, helpful, and concise.\n"
    "2. State clearly that the information was retrieved from the web (external source), "
    "rather than the uploaded documents.\n"
    "3. Keep the tone professional.\n"
)

_WEB_HUMAN_PROMPT = "Search Results:\n{search_results}\n\nQuestion: {question}\n\nAnswer:"


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
        self._reranker = None

    def _get_reranker(self):
        """Load cross-encoder model lazily."""
        if self._reranker is None:
            logger.info("Loading Cross-Encoder reranker model (cross-encoder/ms-marco-MiniLM-L-6-v2)...")
            from sentence_transformers import CrossEncoder
            self._reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
            logger.info("Cross-Encoder reranker loaded.")
        return self._reranker

    def answer(
        self,
        question: str,
        history: list[dict] | None = None,
        top_k: int | None = None,
        selected_document: str | None = None,
        user_id: int | None = None,
    ) -> RAGAnswer:
        """Answer a question from the indexed documents.

        Args:
            question: The user's natural-language question.
            history: Previous messages in the conversation.
            top_k: Optional override for the number of chunks to retrieve.
            selected_document: Optional document source filename to filter by.
            user_id: Optional user ID to isolate context search.

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

        # --- Query condensation ---
        history_list = history or []
        standalone_question = question
        chat_history_str = ""

        if history_list:
            for msg in history_list:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                chat_history_str += f"{role.capitalize()}: {content}\n"

            try:
                condense_prompt_text = _CONDENSE_PROMPT.format(
                    chat_history=chat_history_str.strip(), question=question
                )
                logger.info("Rewriting follow-up question using chat history...")
                standalone_question = self._llm.invoke(condense_prompt_text).content.strip()
                logger.info("Rewritten question: '%s'", standalone_question)
            except Exception as exc:
                logger.warning("Query condensation failed, falling back to original question: %s", exc)
                standalone_question = question

        if not chat_history_str:
            chat_history_str = "None"

        # --- Retrieval: embedding + similarity search + top-K ---
        # Fetch more candidates to enable effective re-ranking
        initial_k = max(20, k * 3)
        retrieved = self._vector_store.similarity_search(
            standalone_question, k=initial_k, filter_source=selected_document, filter_user_id=user_id
        )
        chunks = [RetrievedChunk(document=doc, score=score) for doc, score in retrieved]

        # Flag indicating if we need to search the web
        fallback_triggered = not chunks

        if chunks:
            # --- Re-ranking using Cross-Encoder ---
            try:
                reranker = self._get_reranker()
                pairs = [[standalone_question, c.document.page_content] for c in chunks]
                rerank_scores = reranker.predict(pairs)
                
                import math
                for chunk, raw_score in zip(chunks, rerank_scores):
                    # Sigmoid function to map logit scores to [0, 1] range
                    sig_score = 1.0 / (1.0 + math.exp(-float(raw_score)))
                    chunk.score = round(sig_score, 4)
                    
                chunks = sorted(chunks, key=lambda x: x.score, reverse=True)
                chunks = chunks[:k]
                logger.info("Re-ranking complete. Retained top-%d chunks.", len(chunks))
            except Exception as exc:
                logger.warning("Re-ranking failed, falling back to original retriever rankings: %s", exc)
                chunks = chunks[:k]

            # --- Context injection ---
            context = self._format_context(chunks)

            # --- Generation ---
            try:
                answer = self._chain.invoke({
                    "context": context,
                    "chat_history": chat_history_str.strip(),
                    "question": standalone_question,
                })
            except Exception as exc:
                raise LLMError(f"LLM failed to generate an answer: {exc}") from exc

            answer = answer.strip()
            if answer == _NOT_FOUND_MESSAGE:
                fallback_triggered = True
        else:
            answer = _NOT_FOUND_MESSAGE

        if fallback_triggered:
            logger.info("Content not found in documents. Falling back to web search...")
            try:
                from langchain_community.tools import DuckDuckGoSearchRun
                search = DuckDuckGoSearchRun()
                search_results = search.run(standalone_question)

                from langchain_core.prompts import ChatPromptTemplate
                web_prompt = ChatPromptTemplate.from_messages([
                    ("system", _WEB_SYSTEM_PROMPT),
                    ("human", _WEB_HUMAN_PROMPT)
                ])
                web_chain = web_prompt | self._llm | StrOutputParser()
                web_answer = web_chain.invoke({
                    "search_results": search_results,
                    "question": standalone_question
                })
                
                logger.info("Generated answer from web search fallback.")
                return RAGAnswer(
                    answer=web_answer.strip(),
                    chunks=[],
                    confidence=0.4
                )
            except Exception as exc:
                logger.warning("Web search fallback failed: %s", exc)
                return RAGAnswer(
                    answer=_NOT_FOUND_MESSAGE,
                    chunks=[],
                    confidence=0.0
                )

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
