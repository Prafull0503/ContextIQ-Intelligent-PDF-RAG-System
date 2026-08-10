"""FastAPI route definitions.

Endpoints:
    POST /upload-pdf  -> ingest a PDF into the vector store
    POST /ask         -> answer a question from indexed PDFs
    GET  /health      -> liveness + index status

The CPU/IO-bound work (PDF parsing, embedding, LLM calls) is synchronous, so
the async endpoints offload it to a worker thread via ``run_in_threadpool``.
This keeps the event loop responsive and the endpoints genuinely async.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile, status
from starlette.concurrency import run_in_threadpool

from app.core.logging_config import get_logger
from app.models.schemas import (
    AskRequest,
    AskResponse,
    HealthResponse,
    UploadResponse,
    DocumentListResponse,
    DeleteDocumentResponse,
    SourceChunkSchema,
)
from app.services.rag_service import RAGService, get_rag_service
from app.utils.exceptions import InvalidPDFError

logger = get_logger(__name__)

router = APIRouter()

_MAX_PDF_BYTES = 25 * 1024 * 1024  # 25 MB upload cap.


@router.get("/health", response_model=HealthResponse, tags=["system"])
async def health(
    service: RAGService = Depends(get_rag_service),
) -> HealthResponse:
    """Liveness probe plus a quick view of the index state."""
    return HealthResponse(
        status="healthy",
        llm_provider=service.settings.llm_provider.value,
        embedding_provider=service.settings.embedding_provider.value,
        documents_indexed=await run_in_threadpool(service.document_count),
    )


@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["ingestion"],
)
@router.post(
    "/upload-pdf",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["ingestion"],
    include_in_schema=False,
)
async def upload_file(
    file: UploadFile = File(..., description="A document to ingest."),
    service: RAGService = Depends(get_rag_service),
) -> UploadResponse:
    """Upload a document, ingest it, and persist its embeddings to ChromaDB."""
    filename = file.filename or "uploaded.pdf"

    # --- Basic validation before doing any expensive work ---
    allowed_exts = {".pdf", ".docx", ".txt", ".csv"}
    if not any(filename.lower().endswith(ext) for ext in allowed_exts):
        raise InvalidPDFError("Only .pdf, .docx, .txt, and .csv files are accepted.")

    allowed_mimes = {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain",
        "text/csv",
        "application/csv",
        "application/octet-stream",
    }
    content_type = (file.content_type or "").lower()
    if content_type and content_type not in allowed_mimes:
        raise InvalidPDFError(f"Unexpected content type: {file.content_type}")

    contents = await file.read()
    if not contents:
        raise InvalidPDFError("The uploaded file is empty.")
    if len(contents) > _MAX_PDF_BYTES:
        raise InvalidPDFError("File exceeds the 25 MB size limit.")

    # --- Persist the upload to disk (unique name avoids collisions) ---
    upload_dir: Path = service.settings.pdf_upload_dir_resolved
    stored_path = upload_dir / f"{uuid.uuid4().hex}_{filename}"
    await run_in_threadpool(stored_path.write_bytes, contents)
    logger.info("Saved upload '%s' -> %s", filename, stored_path)

    # --- Ingest (offloaded to a thread; it's CPU/IO bound) ---
    result = await run_in_threadpool(service.ingest_pdf, stored_path, filename)

    return UploadResponse(
        message="Document processed successfully",
        filename=result.filename,
        chunks_created=result.chunks_created,
        pages=result.pages,
    )


@router.get(
    "/documents",
    response_model=DocumentListResponse,
    tags=["ingestion"],
)
async def list_documents(
    service: RAGService = Depends(get_rag_service),
) -> DocumentListResponse:
    """Get the list of unique filenames currently indexed in the vector store."""
    docs = await run_in_threadpool(service.list_documents)
    return DocumentListResponse(documents=docs)


@router.delete(
    "/documents/{filename}",
    response_model=DeleteDocumentResponse,
    tags=["ingestion"],
)
async def delete_document(
    filename: str,
    service: RAGService = Depends(get_rag_service),
) -> DeleteDocumentResponse:
    """Delete a document from the vector store and its physical file on disk."""
    await run_in_threadpool(service.delete_document, filename)
    return DeleteDocumentResponse(
        message="Document deleted successfully",
        filename=filename,
    )


@router.post("/ask", response_model=AskResponse, tags=["query"])
async def ask(
    payload: AskRequest,
    service: RAGService = Depends(get_rag_service),
) -> AskResponse:
    """Answer a question grounded in the uploaded document content."""
    history_dicts = [msg.model_dump() for msg in payload.history]
    result = await run_in_threadpool(
        service.ask, payload.question, history_dicts, payload.top_k, payload.selected_document
    )
    
    sources = []
    if result.chunks:
        for chunk in result.chunks:
            meta = chunk.document.metadata or {}
            sources.append(
                SourceChunkSchema(
                    content=chunk.document.page_content,
                    source=meta.get("source", "unknown"),
                    page=meta.get("page"),
                    score=chunk.score,
                )
            )
            
    return AskResponse(
        answer=result.answer,
        sources=sources if sources else None,
        confidence=result.confidence,
    )
