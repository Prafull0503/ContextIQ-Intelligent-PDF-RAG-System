"""FastAPI route definitions.

Endpoints:
    POST /auth/signup -> register a user
    POST /auth/login  -> authenticate and obtain JWT token
    POST /upload      -> ingest a document (isolated by user)
    POST /ask         -> answer a question grounded in user-specific documents
    GET  /documents   -> list user documents
    DELETE /documents -> delete user document
"""

from __future__ import annotations

import uuid
from pathlib import Path
from sqlmodel import Session, select

from fastapi import APIRouter, Depends, File, UploadFile, status, HTTPException
from fastapi.security import OAuth2PasswordBearer
from starlette.concurrency import run_in_threadpool

from app.core.logging_config import get_logger
from app.core.database import get_db
from app.models.schemas import (
    AskRequest,
    AskResponse,
    HealthResponse,
    UploadResponse,
    DocumentListResponse,
    DeleteDocumentResponse,
    SourceChunkSchema,
    User,
    UserSignup,
    UserLogin,
    TokenResponse,
    UserResponse,
)
from app.services.rag_service import RAGService, get_rag_service
from app.utils.exceptions import InvalidPDFError
from app.utils.auth import hash_password, verify_password, create_access_token, decode_access_token

logger = get_logger(__name__)

router = APIRouter()

_MAX_PDF_BYTES = 25 * 1024 * 1024  # 25 MB upload cap.

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Security dependency to fetch the logged-in user from the JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    email = decode_access_token(token)
    if email is None:
        raise credentials_exception
    
    user = db.exec(select(User).where(User.email == email)).first()
    if user is None:
        raise credentials_exception
    return user


# ---------------------------------------------------------------------------
# Auth Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/auth/signup",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["auth"],
)
async def signup(
    payload: UserSignup,
    db: Session = Depends(get_db),
) -> UserResponse:
    """Register a new user in the SQL database."""
    existing = db.exec(select(User).where(User.email == payload.email)).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )
    
    hashed = hash_password(payload.password)
    user = User(email=payload.email, hashed_password=hashed, username=payload.username)
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("Successfully registered user: %s", user.email)
    return UserResponse(id=user.id, email=user.email, username=user.username, created_at=user.created_at)


@router.post(
    "/auth/login",
    response_model=TokenResponse,
    tags=["auth"],
)
async def login(
    payload: UserLogin,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Verify user credentials and return a JWT access token."""
    user = db.exec(select(User).where(User.email == payload.email)).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = create_access_token(subject=user.email)
    logger.info("User logged in successfully: %s", user.email)
    return TokenResponse(access_token=token, username=user.username)


# ---------------------------------------------------------------------------
# Health / System
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# RAG Endpoints (Secured)
# ---------------------------------------------------------------------------

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
    current_user: User = Depends(get_current_user),
) -> UploadResponse:
    """Upload a document, ingest it, and isolate its metadata under active user_id."""
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
    logger.info("Saved upload '%s' -> %s for User %d", filename, stored_path, current_user.id)

    # --- Ingest (offloaded to a thread; passes user_id) ---
    result = await run_in_threadpool(service.ingest_pdf, stored_path, filename, current_user.id)

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
    current_user: User = Depends(get_current_user),
) -> DocumentListResponse:
    """Get the list of unique filenames currently indexed by the current user."""
    docs = await run_in_threadpool(service.list_documents, current_user.id)
    return DocumentListResponse(documents=docs)


@router.delete(
    "/documents/{filename}",
    response_model=DeleteDocumentResponse,
    tags=["ingestion"],
)
async def delete_document(
    filename: str,
    service: RAGService = Depends(get_rag_service),
    current_user: User = Depends(get_current_user),
) -> DeleteDocumentResponse:
    """Delete user's document from the vector store and its physical file on disk."""
    await run_in_threadpool(service.delete_document, filename, current_user.id)
    return DeleteDocumentResponse(
        message="Document deleted successfully",
        filename=filename,
    )


@router.post("/ask", response_model=AskResponse, tags=["query"])
async def ask(
    payload: AskRequest,
    service: RAGService = Depends(get_rag_service),
    current_user: User = Depends(get_current_user),
) -> AskResponse:
    """Answer a question grounded strictly in user's isolated documents."""
    history_dicts = [msg.model_dump() for msg in payload.history]
    result = await run_in_threadpool(
        service.ask,
        payload.question,
        history_dicts,
        payload.top_k,
        payload.selected_document,
        current_user.id,
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
