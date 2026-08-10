"""PDF ingestion pipeline (the write path).

Pipeline:
    load PDF -> clean text -> chunk -> embed -> store in ChromaDB (persisted)

The :class:`IngestionPipeline` orchestrates these steps. Embedding + storage
are delegated to :class:`~app.services.vectorstore_service.VectorStoreService`,
so this module focuses on turning a PDF file into clean, chunked, metadata-rich
:class:`~langchain_core.documents.Document` objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import Settings
from app.core.logging_config import get_logger
from app.services.vectorstore_service import VectorStoreService
from app.utils.exceptions import EmptyDocumentError, InvalidDocumentError
from app.utils.text_cleaning import clean_text

logger = get_logger(__name__)


@dataclass
class IngestionResult:
    """Outcome of ingesting a single document."""

    filename: str
    pages: int
    chunks_created: int


class IngestionPipeline:
    """Loads, cleans, chunks, embeds and stores document content."""

    def __init__(
        self, settings: Settings, vector_store: VectorStoreService
    ) -> None:
        self._settings = settings
        self._vector_store = vector_store
        # RecursiveCharacterTextSplitter respects natural boundaries
        # (paragraphs -> lines -> words) for cleaner, more coherent chunks.
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
            length_function=len,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def ingest(self, pdf_path: Path, original_filename: str) -> IngestionResult:
        """Run the full ingestion pipeline for one document.

        Args:
            pdf_path: Path to the document file on disk.
            original_filename: The name to record as the chunk source.

        Returns:
            An :class:`IngestionResult` summarising what was stored.

        Raises:
            InvalidDocumentError: If the file cannot be parsed.
            EmptyDocumentError: If no usable text could be extracted.
        """
        logger.info("Ingestion started for '%s'", original_filename)

        pages = self._load(pdf_path, original_filename)
        cleaned_pages = self._clean(pages, original_filename)
        chunks = self._chunk(cleaned_pages, original_filename)

        stored = self._vector_store.add_documents(chunks)
        logger.info(
            "Ingestion finished for '%s': %d page/section(s), %d chunk(s) stored",
            original_filename,
            len(pages),
            stored,
        )
        return IngestionResult(
            filename=original_filename,
            pages=len(pages),
            chunks_created=stored,
        )

    # ------------------------------------------------------------------
    # Pipeline steps
    # ------------------------------------------------------------------
    def _load(self, pdf_path: Path, filename: str) -> list[Document]:
        """Step 1: Load the document into per-page/per-section documents."""
        ext = pdf_path.suffix.lower()
        try:
            if ext == ".pdf":
                documents = PyPDFLoader(str(pdf_path)).load()
            elif ext == ".docx":
                from langchain_community.document_loaders import Docx2txtLoader
                documents = Docx2txtLoader(str(pdf_path)).load()
            elif ext == ".txt":
                from langchain_community.document_loaders import TextLoader
                documents = TextLoader(str(pdf_path), encoding="utf-8").load()
            elif ext == ".csv":
                from langchain_community.document_loaders import CSVLoader
                documents = CSVLoader(str(pdf_path)).load()
            else:
                raise ValueError(f"Unsupported file extension: {ext}")
        except Exception as exc:
            raise InvalidDocumentError(
                f"'{filename}' could not be read as a valid document: {exc}"
            ) from exc

        if not documents:
            raise EmptyDocumentError(f"'{filename}' contains no content.")
        logger.info("Loaded %d page/section(s) from '%s'", len(documents), filename)
        return documents

    def _clean(self, pages: list[Document], filename: str) -> list[Document]:
        """Step 2: Clean each page's text; drop pages with no content."""
        cleaned: list[Document] = []
        for page in pages:
            text = clean_text(page.page_content)
            if not text:
                continue
            page.page_content = text
            cleaned.append(page)

        if not cleaned:
            raise EmptyPDFError(
                f"'{filename}' has no extractable text (it may be a scanned "
                "image-only PDF that requires OCR)."
            )
        return cleaned

    def _chunk(self, pages: list[Document], filename: str) -> list[Document]:
        """Step 3: Split pages into overlapping chunks with rich metadata."""
        chunks = self._splitter.split_documents(pages)

        # Attach consistent source-tracking metadata to every chunk.
        for index, chunk in enumerate(chunks):
            page_number = chunk.metadata.get("page")
            meta = {
                "source": filename,
                "chunk_index": index,
            }
            if page_number is not None:
                meta["page"] = page_number
            chunk.metadata = meta

        logger.info("Created %d chunk(s) for '%s'", len(chunks), filename)
        return chunks
