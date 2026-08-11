"""Pydantic schemas for API requests and responses, plus DB (SQLModel) tables.

These models define the public contract of the API and provide automatic
validation + OpenAPI documentation for free.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, EmailStr, Field
from sqlmodel import Field as SQLField
from sqlmodel import SQLModel


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
class HealthResponse(BaseModel):
    """Response for the ``GET /health`` endpoint."""

    status: str = Field(..., examples=["healthy"])
    llm_provider: str = Field(..., examples=["openai"])
    embedding_provider: str = Field(..., examples=["huggingface"])
    documents_indexed: int = Field(
        ..., description="Number of chunks currently stored in the vector DB."
    )


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------
class UploadResponse(BaseModel):
    """Response for the ``POST /upload-pdf`` endpoint."""

    message: str = Field(..., examples=["PDF processed successfully"])
    filename: str
    chunks_created: int = Field(
        ..., description="Number of text chunks generated and embedded."
    )
    pages: int = Field(..., description="Number of pages found in the PDF.")


class DocumentListResponse(BaseModel):
    """Response for the ``GET /documents`` endpoint."""

    documents: list[str] = Field(..., description="List of unique filenames currently indexed.")


class DeleteDocumentResponse(BaseModel):
    """Response for the ``DELETE /documents/{filename}`` endpoint."""

    message: str = Field(..., description="Status message.", examples=["Document deleted successfully."])
    filename: str = Field(..., description="The name of the deleted document.")


# ---------------------------------------------------------------------------
# Ask
# ---------------------------------------------------------------------------
class Message(BaseModel):
    """A single message in the conversation history."""

    role: str = Field(..., description="Role of the sender: 'user' or 'assistant'.", examples=["user"])
    content: str = Field(..., max_length=8_000, description="Text content of the message.")


class AskRequest(BaseModel):
    """Request body for the ``POST /ask`` endpoint."""

    question: str = Field(
        ...,
        min_length=1,
        max_length=2_000,
        description="Natural-language question to answer from the indexed PDFs.",
        examples=["What is this document about?"],
    )
    top_k: int | None = Field(
        default=None,
        gt=0,
        le=50,
        description="Override the number of chunks to retrieve for this query.",
    )
    history: list[Message] = Field(
        default_factory=list,
        max_length=50,
        description="Conversation history of previous messages (most recent last).",
    )
    selected_document: str | None = Field(
        default=None,
        description="Filter retrieval strictly to chunks belonging to this document.",
    )


class SourceChunkSchema(BaseModel):
    """Retrieved chunk citation info."""

    content: str = Field(..., description="The raw text content of the chunk.")
    source: str = Field(..., description="The name of the source document.")
    page: int | None = Field(default=None, description="The page number in the original document.")
    score: float | None = Field(default=None, description="The similarity/rerank score of this chunk.")


class AskResponse(BaseModel):
    """Response for the ``POST /ask`` endpoint."""

    answer: str
    sources: list[SourceChunkSchema] | None = Field(
        default=None, description="List of document text chunks used to generate the answer."
    )
    confidence: float | None = Field(
        default=None, description="Confidence score representing retrieval relevance."
    )


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
class ErrorResponse(BaseModel):
    """Standard error envelope."""

    detail: str


# ---------------------------------------------------------------------------
# User & Auth (DB table + API schemas)
# ---------------------------------------------------------------------------
class User(SQLModel, table=True):
    """Database model for user records."""

    id: int | None = SQLField(default=None, primary_key=True)
    email: str = SQLField(unique=True, index=True, nullable=False)
    username: str = SQLField(default="", nullable=False)
    hashed_password: str = SQLField(nullable=False)
    created_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))


class UserSignup(BaseModel):
    """Schema for registering a new user."""

    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    username: str = Field(..., min_length=1, max_length=64)


class UserLogin(BaseModel):
    """Schema for authenticating a user."""

    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class TokenResponse(BaseModel):
    """Response containing JWT access token."""

    access_token: str
    token_type: str = "bearer"
    username: str = ""


class UserResponse(BaseModel):
    """Public user response schema."""

    id: int
    email: str
    username: str
    created_at: datetime
    