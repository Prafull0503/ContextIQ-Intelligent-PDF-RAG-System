"""Domain-specific exceptions.

These are raised by the service layer and translated into HTTP responses by a
single exception handler registered on the FastAPI app. Keeping HTTP concerns
out of the services keeps the business logic reusable and testable.
"""

from __future__ import annotations


class RAGError(Exception):
    """Base class for all application errors.

    Attributes:
        message: Human-readable error message.
        status_code: HTTP status code the API layer should return.
    """

    status_code: int = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidDocumentError(RAGError):
    """Raised when a file is not a valid / readable document."""

    status_code = 400


class EmptyDocumentError(RAGError):
    """Raised when a document contains no extractable text."""

    status_code = 422


# Backwards compatibility aliases
InvalidPDFError = InvalidDocumentError
EmptyPDFError = EmptyDocumentError


class MissingAPIKeyError(RAGError):
    """Raised when the configured provider is missing its API key."""

    status_code = 500


class VectorStoreError(RAGError):
    """Raised on vector database failures."""

    status_code = 500


class LLMError(RAGError):
    """Raised when the LLM provider fails to generate an answer."""

    status_code = 502


class NoDocumentsError(RAGError):
    """Raised when a question is asked but no documents have been indexed."""

    status_code = 409
