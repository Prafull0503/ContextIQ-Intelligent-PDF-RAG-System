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
    content: str = Field(..., description="Text content of the message.")


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
    history: list[Message] = Field(
        default_factory=list,
        description="Conversation history of previous messages."
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
