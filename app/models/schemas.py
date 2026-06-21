"""Pydantic schemas for API requests and responses.

These models define the public contract of the API and provide automatic
validation + OpenAPI documentation for free.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


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


# ---------------------------------------------------------------------------
# Ask
# ---------------------------------------------------------------------------
class AskRequest(BaseModel):
    """Request body for the ``POST /ask`` endpoint."""

    question: str = Field(
        ...,
        min_length=1,
        description="Natural-language question to answer from the indexed PDFs.",
        examples=["What is this document about?"],
    )
    top_k: int | None = Field(
        default=None,
        gt=0,
        le=50,
        description="Override the number of chunks to retrieve for this query.",
    )


class AskResponse(BaseModel):
    """Response for the ``POST /ask`` endpoint.

    Only the final answer is returned — retrieved source chunks and the
    confidence score are used internally but intentionally not exposed.
    """

    answer: str


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
class ErrorResponse(BaseModel):
    """Standard error envelope."""

    detail: str
