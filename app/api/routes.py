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
    "/upload-pdf",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["ingestion"],
)
async def upload_pdf(
    file: UploadFile = File(..., description="A PDF document to ingest."),
    service: RAGService = Depends(get_rag_service),
) -> UploadResponse:
    """Upload a PDF, ingest it, and persist its embeddings to ChromaDB."""
    filename = file.filename or "uploaded.pdf"

    # --- Basic validation before doing any expensive work ---
    if not filename.lower().endswith(".pdf"):
        raise InvalidPDFError("Only .pdf files are accepted.")
    if (file.content_type or "").lower() not in {
        "application/pdf",
        "application/octet-stream",
    }:
        raise InvalidPDFError(f"Unexpected content type: {file.content_type}")

    contents = await file.read()
    if not contents:
        raise InvalidPDFError("The uploaded file is empty.")
    if len(contents) > _MAX_PDF_BYTES:
        raise InvalidPDFError("PDF exceeds the 25 MB size limit.")

    # --- Persist the upload to disk (unique name avoids collisions) ---
    upload_dir: Path = service.settings.pdf_upload_dir_resolved
    stored_path = upload_dir / f"{uuid.uuid4().hex}_{filename}"
    await run_in_threadpool(stored_path.write_bytes, contents)
    logger.info("Saved upload '%s' -> %s", filename, stored_path)

    # --- Ingest (offloaded to a thread; it's CPU/IO bound) ---
    result = await run_in_threadpool(service.ingest_pdf, stored_path, filename)

    return UploadResponse(
        message="PDF processed successfully",
        filename=result.filename,
        chunks_created=result.chunks_created,
        pages=result.pages,
    )


@router.post("/ask", response_model=AskResponse, tags=["query"])
async def ask(
    payload: AskRequest,
    service: RAGService = Depends(get_rag_service),
) -> AskResponse:
    """Answer a question grounded in the uploaded PDF content."""
    result = await run_in_threadpool(service.ask, payload.question, payload.top_k)
    return AskResponse(answer=result.answer)
